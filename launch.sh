#!/bin/bash
# ================================================================
#  rust-ai-kit  ·  launch.sh
#  Fully non-interactive: detects problems, applies fixes, starts
#  everything, opens browser.  No terminal interaction required.
# ================================================================
# NO set -euo pipefail — must survive non-zero from health checks.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/ai_stack"
MODEL_DIR="$INSTALL_DIR/models"
MODEL_CONFIG="$INSTALL_DIR/.active_model"
LLAMACPP_BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
LOG_DIR="$INSTALL_DIR/logs"
PID_FILE="$INSTALL_DIR/.pids"
MEM_DIR="$INSTALL_DIR/memory_server"
PROXY_DIR="$INSTALL_DIR/search_proxy"

VENV="$SCRIPT_DIR/venv"
PYTHON="$VENV/bin/python3"
STREAMLIT="$VENV/bin/streamlit"
APP="$SCRIPT_DIR/llm_factory_rustaikit.py"
APP_LOG="$SCRIPT_DIR/logs/streamlit.log"
PATCH_SCRIPT="$SCRIPT_DIR/patch_core.py"

ENGINE_PORT=8080
STREAMLIT_PORT=8501

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/logs" 2>/dev/null

# ── Colours ────────────────────────────────────────────────────────
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' C='\033[0;36m' W='\033[1m' N='\033[0m'
ok()   { echo -e "${G}  ✅  $*${N}"; }
info() { echo -e "${C}  ℹ️   $*${N}"; }
warn() { echo -e "${Y}  ⚠️   $*${N}"; }
err()  { echo -e "${R}  ❌  $*${N}"; }
fix()  { echo -e "${W}  🔧  $*${N}"; }
sep()  { echo -e "${C}  ────────────────────────────────────────────${N}"; }

_notify() {
    command -v notify-send >/dev/null 2>&1 \
        && notify-send "🦀 rust-ai-kit" "$1" --icon=utilities-terminal 2>/dev/null \
        || true
}

echo ""
echo -e "${C}${W}  ╔══════════════════════════════════════════════╗"
echo -e "  ║   🦀  rust-ai-kit  —  Starting up           ║"
echo -e "  ╚══════════════════════════════════════════════╝${N}"
echo ""

# ================================================================
#  STEP 1 — Python import patches (runs patch_core.py silently)
# ================================================================
if [[ -f "$PATCH_SCRIPT" ]] && [[ -f "$PYTHON" ]]; then
    info "Checking core/ui imports..."
    PATCH_OUT=$("$PYTHON" "$PATCH_SCRIPT" 2>&1)
    PATCH_EXIT=$?
    # Show output only if something was patched or there was a problem
    if echo "$PATCH_OUT" | grep -qE "Fixed:|⚠️|❌"; then
        echo "$PATCH_OUT"
    else
        ok "Imports OK"
    fi
fi

# ================================================================
#  STEP 2 — Intel oneAPI environment
# ================================================================
info "Loading Intel oneAPI environment..."
if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
    source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true
    ok "oneAPI loaded"
else
    warn "oneAPI not found — SYCL/GPU acceleration unavailable"
fi
export ONEAPI_DEVICE_SELECTOR="level_zero:0"
export SYCL_DEVICE_FILTER="level_zero:gpu"
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env" 2>/dev/null || true

# ================================================================
#  STEP 3 — Auto-fix GPU render group (no logout needed via newgrp)
# ================================================================
_fix_render_group() {
    # Add user to render+video groups non-interactively.
    # Uses `newgrp` trick to activate membership in this shell session
    # without requiring a full logout — works for the current process tree.
    local changed=false

    if ! groups | grep -qw "render"; then
        warn "User not in 'render' group — adding now..."
        sudo usermod -aG render "$USER" 2>/dev/null && {
            fix "Added to 'render' group"
            changed=true
        } || warn "Could not add to render group (sudo required)"
    fi

    if ! groups | grep -qw "video"; then
        sudo usermod -aG video "$USER" 2>/dev/null && {
            fix "Added to 'video' group"
            changed=true
        } || true
    fi

    # Activate groups in current session without logout
    if $changed; then
        fix "Activating group membership in current session..."
        # Re-exec this script under newgrp render so GPU is visible
        # immediately without a full logout.
        if [[ -z "${_REEXECED_WITH_RENDER:-}" ]]; then
            export _REEXECED_WITH_RENDER=1
            exec newgrp render "$0" "$@" 2>/dev/null || {
                warn "newgrp re-exec failed — a logout/login will fully activate GPU"
                warn "Continuing with CPU fallback for this session"
            }
        fi
    fi
}

# ================================================================
#  STEP 4 — Auto-fix missing libze-intel-gpu1
# ================================================================
_fix_libze() {
    if ! dpkg -l libze-intel-gpu1 2>/dev/null | grep -q "^ii"; then
        warn "libze-intel-gpu1 missing — installing now..."
        sudo apt-get install -y libze-intel-gpu1 >/dev/null 2>&1 && {
            fix "Installed libze-intel-gpu1"
        } || {
            warn "apt-get install failed — check sudo permissions"
        }
    fi
}

# ================================================================
#  STEP 5 — GPU preflight + auto-fix
# ================================================================
info "Checking GPU visibility..."
GPU_LAYERS=0

_check_gpu() {
    command -v clinfo >/dev/null 2>&1 && \
        clinfo -l 2>/dev/null | grep -qi "intel"
}

if _check_gpu; then
    GPU_LAYERS=99
    ok "Intel Arc A770 visible — GPU acceleration enabled (99 layers)"
else
    warn "GPU not visible — attempting auto-fix..."
    _fix_libze
    _fix_render_group "$@"

    # Re-check after fixes
    if _check_gpu; then
        GPU_LAYERS=99
        ok "GPU now visible after fix — GPU acceleration enabled"
    else
        warn "GPU still not visible — using CPU fallback"
        warn "A logout/login may be required if render group was just added"
    fi
fi

# ================================================================
#  STEP 6 — Engine startup
# ================================================================
engine_alive() {
    curl -sf -H "Authorization: Bearer local" \
        "http://localhost:${ENGINE_PORT}/v1/models" >/dev/null 2>&1
}

_show_log_tail() {
    local n="${1:-20}"
    [[ -f "$LOG_DIR/engine.log" ]] || return
    sep
    echo -e "${Y}  Last ${n} lines of engine.log:${N}"
    sep
    tail -n "$n" "$LOG_DIR/engine.log" | sed 's/^/    /'
    sep
}

_diagnose_and_fix_engine() {
    local log="$LOG_DIR/engine.log"
    [[ -f "$log" ]] || { warn "engine.log not found"; return 1; }

    local fixed_something=false

    # ── SYCL / level-zero ────────────────────────────────────────────────────
    if grep -qi "no device of requested type\|level_zero\|ze_result_error\|cl_invalid" "$log" 2>/dev/null; then
        warn "SYCL / level-zero GPU error detected"
        _fix_libze
        _fix_render_group "$@"
        fixed_something=true
    fi

    # ── Port conflict ─────────────────────────────────────────────────────────
    if grep -qi "address already in use\|bind.*failed" "$log" 2>/dev/null; then
        local stale
        stale=$(lsof -ti ":${ENGINE_PORT}" 2>/dev/null | head -1)
        if [[ -n "$stale" ]]; then
            warn "Port ${ENGINE_PORT} still in use (PID $stale) — killing..."
            kill -9 "$stale" 2>/dev/null || true
            sleep 1
            fix "Killed stale process on :${ENGINE_PORT}"
            fixed_something=true
        fi
    fi

    # ── Model file ────────────────────────────────────────────────────────────
    if grep -qi "failed to load\|invalid model\|no such file\|gguf" "$log" 2>/dev/null; then
        warn "Model load failure detected"
        # Try to find another model and switch to it
        local alt
        alt=$(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" 2>/dev/null | sort | head -1)
        if [[ -n "$alt" ]]; then
            echo "$alt" > "$MODEL_CONFIG"
            fix "Switched active model to: $(basename "$alt")"
            fixed_something=true
        else
            err "No .gguf models found in $MODEL_DIR"
            err "Download one: ./ai_stack_manager.sh  →  option 14"
        fi
    fi

    $fixed_something
}

_start_engine_once() {
    # Resolve model
    local model_path=""
    [[ -f "$MODEL_CONFIG" ]] && model_path=$(cat "$MODEL_CONFIG" | tr -d '[:space:]')
    if [[ -z "$model_path" ]] || [[ ! -f "$model_path" ]]; then
        model_path=$(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" 2>/dev/null | sort | head -1)
        [[ -n "$model_path" ]] && echo "$model_path" > "$MODEL_CONFIG"
    fi

    if [[ ! -f "$LLAMACPP_BIN" ]]; then
        err "llama-server not found: $LLAMACPP_BIN"
        err "Run: ./ai_stack_manager.sh  →  option 1"
        return 2  # fatal — no point retrying
    fi
    if [[ -z "$model_path" ]] || [[ ! -f "$model_path" ]]; then
        err "No model found in $MODEL_DIR"
        err "Run: ./ai_stack_manager.sh  →  option 14"
        return 2  # fatal
    fi

    # Kill anything on the port first
    local stale
    stale=$(lsof -ti ":${ENGINE_PORT}" 2>/dev/null | head -1)
    [[ -n "$stale" ]] && { kill -9 "$stale" 2>/dev/null || true; sleep 1; }

    # Rotate log
    [[ -f "$LOG_DIR/engine.log" ]] && \
        mv "$LOG_DIR/engine.log" "$LOG_DIR/engine.log.prev" 2>/dev/null || true

    info "Starting llama-server: $(basename "$model_path")"
    info "GPU layers: $GPU_LAYERS"

    ONEAPI_DEVICE_SELECTOR="level_zero:0" \
    SYCL_DEVICE_FILTER="level_zero:gpu" \
    "$LLAMACPP_BIN" \
        --model        "$model_path" \
        --ctx-size     8192 \
        --n-gpu-layers "$GPU_LAYERS" \
        --port         "$ENGINE_PORT" \
        --host         0.0.0.0 \
        --api-key      local \
        >> "$LOG_DIR/engine.log" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"
    info "Engine PID $pid — polling API (up to 90s)..."

    for i in $(seq 1 90); do
        sleep 1
        printf "\r  ${C}  Waiting… %2ds${N}" "$i"

        if ! kill -0 "$pid" 2>/dev/null; then
            echo ""
            err "Engine process exited after ${i}s"
            _show_log_tail 25
            return 1  # retriable
        fi

        if engine_alive; then
            echo ""
            ok "Engine API live after ${i}s"
            return 0
        fi
    done

    echo ""
    err "Engine did not respond after 90s"
    _show_log_tail 25
    kill "$pid" 2>/dev/null || true
    return 1  # retriable
}

# ── Engine: start with auto-retry after diagnosis ─────────────────────────────
ENGINE_OK=false

if engine_alive; then
    ok "Engine already running on :${ENGINE_PORT}"
    ENGINE_OK=true
else
    _notify "Starting AI stack…"
    echo ""
    info "Starting engine..."

    for attempt in 1 2 3; do
        _start_engine_once
        RC=$?

        if [[ $RC -eq 0 ]]; then
            ENGINE_OK=true
            break
        elif [[ $RC -eq 2 ]]; then
            # Fatal (binary/model missing) — no point retrying
            break
        fi

        # Attempt failed — diagnose and auto-fix before retry
        warn "Attempt $attempt failed — running auto-diagnosis..."
        if _diagnose_and_fix_engine; then
            fix "Fixes applied — retrying..."
            sleep 2
        else
            warn "No auto-fix available for this failure"
            # Still retry in case it was a transient issue (e.g. GPU warmup)
            if [[ $attempt -lt 3 ]]; then
                warn "Retrying anyway (attempt $((attempt+1)) of 3)..."
                sleep 3
            fi
        fi
    done
fi

if ! $ENGINE_OK; then
    err "Engine failed after 3 attempts."
    warn "Streamlit will still launch — use the 🦀 Stack tab to retry."
    _notify "Engine failed — use Stack tab in browser to retry"
fi

# ================================================================
#  STEP 7 — Memory server + search proxy
# ================================================================
if $ENGINE_OK; then
    MEM_LAUNCH="$MEM_DIR/start_memory_server.sh"
    if [[ -f "$MEM_LAUNCH" ]] && ! curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        info "Starting memory server..."
        LLAMA_API_KEY=local \
        LLAMA_BASE_URL="http://localhost:${ENGINE_PORT}/v1" \
        LLAMA_MODEL=llama \
        bash "$MEM_LAUNCH" >> "$LOG_DIR/memory.log" 2>&1 &
        sleep 3
        kill -0 $! 2>/dev/null && ok "Memory server → http://localhost:8000" \
                                || warn "Memory server exited — see memory.log"
    fi

    PROXY_LAUNCH="$PROXY_DIR/start_search_proxy.sh"
    if [[ -f "$PROXY_LAUNCH" ]] && ! curl -sf http://localhost:8090/health >/dev/null 2>&1; then
        info "Starting search proxy..."
        bash "$PROXY_LAUNCH" >> "$LOG_DIR/proxy.log" 2>&1 &
        sleep 2
        kill -0 $! 2>/dev/null && ok "Search proxy → http://localhost:8090" \
                                || warn "Search proxy exited — see proxy.log"
    fi
fi

# ================================================================
#  STEP 8 — Streamlit
# ================================================================
streamlit_alive() {
    curl -sf "http://localhost:${STREAMLIT_PORT}" >/dev/null 2>&1
}

echo ""
if streamlit_alive; then
    ok "Streamlit already running on :${STREAMLIT_PORT}"
else
    if [[ ! -f "$STREAMLIT" ]]; then
        err "Streamlit not found: $STREAMLIT"
        err "Run:  make setup"
        exit 1
    fi

    info "Starting Streamlit on :${STREAMLIT_PORT}..."
    mkdir -p "$(dirname "$APP_LOG")"
    [[ -f "$APP_LOG" ]] && mv "$APP_LOG" "${APP_LOG}.prev" 2>/dev/null || true

    nohup "$STREAMLIT" run "$APP" \
        --server.port        "$STREAMLIT_PORT" \
        --server.headless    true \
        --server.address     0.0.0.0 \
        >> "$APP_LOG" 2>&1 &

    ST_PID=$!
    echo "$ST_PID" > "$SCRIPT_DIR/logs/.streamlit_pid"
    info "Streamlit PID $ST_PID — waiting..."

    for i in $(seq 1 30); do
        sleep 1
        printf "\r  ${C}  Waiting… %2ds${N}" "$i"
        if streamlit_alive; then
            echo ""
            ok "Streamlit live after ${i}s"
            break
        fi
        if ! kill -0 "$ST_PID" 2>/dev/null; then
            echo ""
            err "Streamlit crashed. Last log:"
            tail -20 "$APP_LOG" 2>/dev/null | sed 's/^/    /' || true
            err "Run:  make setup   (missing dependency likely)"
            exit 1
        fi
    done
    echo ""
fi

# ================================================================
#  STEP 9 — Open browser
# ================================================================
URL="http://localhost:${STREAMLIT_PORT}"
_notify "LLM Factory ready → $URL"
xdg-open "$URL" 2>/dev/null &

# ── Final status summary ───────────────────────────────────────────────────
echo ""
sep
engine_alive \
    && echo -e "  ${G}🟢 Engine    :${ENGINE_PORT}${N}" \
    || echo -e "  ${R}🔴 Engine    :${ENGINE_PORT}  ← use Stack tab → ▶️ Start engine${N}"
curl -sf http://localhost:8000/health >/dev/null 2>&1 \
    && echo -e "  ${G}🟢 Memory    :8000${N}" \
    || echo -e "  ${Y}⚪ Memory    :8000${N}"
curl -sf http://localhost:8090/health >/dev/null 2>&1 \
    && echo -e "  ${G}🟢 Proxy     :8090${N}" \
    || echo -e "  ${Y}⚪ Proxy     :8090${N}"
streamlit_alive \
    && echo -e "  ${G}🟢 Streamlit  →  ${C}${URL}${N}" \
    || echo -e "  ${R}🔴 Streamlit :${STREAMLIT_PORT}${N}"
sep
echo ""
sleep 5
exit