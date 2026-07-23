#!/bin/bash
# ================================================================
#  rust-ai-kit  ·  launch.sh
#  Fully non-interactive: detects problems, applies fixes, starts
#  everything, opens browser.  No terminal interaction required.
#
#  All background services are started with `nohup setsid` so they
#  survive terminal window close (SIGHUP) without exception.
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

ENABLE_WEBUI="${ENABLE_WEBUI:-0}"

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
#  STEP 3 — Auto-fix GPU render group
# ================================================================
_fix_render_group() {
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

    if $changed; then
        fix "Activating group membership in current session..."
        if [[ -z "${_REEXECED_WITH_RENDER:-}" ]]; then
            export _REEXECED_WITH_RENDER=1
            exec newgrp render "$0" "$@" 2>/dev/null || {
                warn "newgrp re-exec failed — logout/login will fully activate GPU"
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

    if grep -qi "no device of requested type\|level_zero\|ze_result_error\|cl_invalid" "$log" 2>/dev/null; then
        warn "SYCL / level-zero GPU error detected"
        _fix_libze
        _fix_render_group "$@"
        fixed_something=true
    fi

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

    if grep -qi "failed to load\|invalid model\|no such file\|gguf" "$log" 2>/dev/null; then
        warn "Model load failure detected"
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
    local model_path=""
    [[ -f "$MODEL_CONFIG" ]] && model_path=$(cat "$MODEL_CONFIG" | tr -d '[:space:]')
    if [[ -z "$model_path" ]] || [[ ! -f "$model_path" ]]; then
        model_path=$(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" 2>/dev/null | sort | head -1)
        [[ -n "$model_path" ]] && echo "$model_path" > "$MODEL_CONFIG"
    fi

    if [[ ! -f "$LLAMACPP_BIN" ]]; then
        err "llama-server not found: $LLAMACPP_BIN"
        err "Run: ./ai_stack_manager.sh  →  option 1"
        return 2
    fi
    if [[ -z "$model_path" ]] || [[ ! -f "$model_path" ]]; then
        err "No model found in $MODEL_DIR"
        err "Run: ./ai_stack_manager.sh  →  option 14"
        return 2
    fi

    # Kill anything already on the port
    local stale
    stale=$(lsof -ti ":${ENGINE_PORT}" 2>/dev/null | head -1)
    [[ -n "$stale" ]] && { kill -9 "$stale" 2>/dev/null || true; sleep 1; }

    # Rotate log so failure output is clean
    [[ -f "$LOG_DIR/engine.log" ]] && \
        mv "$LOG_DIR/engine.log" "$LOG_DIR/engine.log.prev" 2>/dev/null || true

    info "Starting llama-server: $(basename "$model_path")"
    info "GPU layers: $GPU_LAYERS"

    # nohup + setsid: process survives terminal close (SIGHUP)
    # setsid creates a new session with no controlling terminal
    # nohup explicitly ignores SIGHUP as a belt-and-braces measure
    ONEAPI_DEVICE_SELECTOR="level_zero:0" \
    SYCL_DEVICE_FILTER="level_zero:gpu" \
    nohup setsid "$LLAMACPP_BIN" \
        --model        "$model_path" \
        --ctx-size     8192 \
        --n-gpu-layers "$GPU_LAYERS" \
        --port         "$ENGINE_PORT" \
        --host         127.0.0.1 \
        --api-key      local \
        >> "$LOG_DIR/engine.log" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"
    info "Engine PID $pid — polling API (up to 90s)..."

    for i in $(seq 1 90); do
        sleep 1
        printf "\r  ${C}  Waiting… %2ds${N}" "$i"

        # setsid means kill -0 on the wrapper PID may not track the child,
        # so we check the port directly and trust engine.log for crash detection
        if engine_alive; then
            echo ""
            ok "Engine API live after ${i}s"
            return 0
        fi

        # Check log for early fatal errors (no point waiting 90s)
        if [[ -f "$LOG_DIR/engine.log" ]] && (( i > 5 )); then
            if grep -qi "error\|failed\|abort\|fatal" "$LOG_DIR/engine.log" 2>/dev/null; then
                # Only bail if the process also isn't alive
                if ! kill -0 "$pid" 2>/dev/null && ! pgrep -f "llama-server" >/dev/null 2>&1; then
                    echo ""
                    err "Engine process crashed after ${i}s"
                    _show_log_tail 25
                    return 1
                fi
            fi
        fi
    done

    echo ""
    err "Engine did not respond after 90s"
    _show_log_tail 25
    return 1
}

# ── Engine: start with auto-retry ────────────────────────────────────────────
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
            break  # fatal — binary or model missing
        fi

        warn "Attempt $attempt failed — running auto-diagnosis..."
        if _diagnose_and_fix_engine; then
            fix "Fixes applied — retrying..."
            sleep 2
        else
            warn "No auto-fix found"
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
#  Both use nohup + setsid so they survive terminal close.
# ================================================================
if $ENGINE_OK; then
    MEM_LAUNCH="$MEM_DIR/start_memory_server.sh"
    if [[ -f "$MEM_LAUNCH" ]] && ! curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        info "Starting memory server..."
        LLAMA_API_KEY=local \
        LLAMA_BASE_URL="http://localhost:${ENGINE_PORT}/v1" \
        LLAMA_MODEL=llama \
        nohup setsid bash "$MEM_LAUNCH" >> "$LOG_DIR/memory.log" 2>&1 &
        sleep 3
        if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
            ok "Memory server → http://localhost:8000"
        else
            warn "Memory server may still be starting — check memory.log if needed"
        fi
    fi

    PROXY_LAUNCH="$PROXY_DIR/start_search_proxy.sh"
    if [[ -f "$PROXY_LAUNCH" ]] && ! curl -sf http://localhost:8090/health >/dev/null 2>&1; then
        info "Starting search proxy..."
        nohup setsid bash "$PROXY_LAUNCH" >> "$LOG_DIR/proxy.log" 2>&1 &
        sleep 2
        if curl -sf http://localhost:8090/health >/dev/null 2>&1; then
            ok "Search proxy → http://localhost:8090"
        else
            warn "Search proxy may still be starting — check proxy.log if needed"
        fi
    fi
fi

# ================================================================
#  STEP 8 — Streamlit (optional WebUI)
#  nohup + setsid: survives terminal close.
# ================================================================
if [[ "$ENABLE_WEBUI" == "1" ]]; then
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

    nohup setsid "$STREAMLIT" run "$APP" \
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
        # Check log for crash
        if [[ -f "$APP_LOG" ]] && (( i > 5 )); then
            if grep -qi "error\|traceback\|exception" "$APP_LOG" 2>/dev/null; then
                if ! pgrep -f "streamlit run" >/dev/null 2>&1; then
                    echo ""
                    err "Streamlit crashed. Last log:"
                    tail -20 "$APP_LOG" 2>/dev/null | sed 's/^/    /' || true
                    err "Run:  make setup   (missing dependency likely)"
                    exit 1
                fi
            fi
        fi
    done
    echo ""
fi
fi

# ================================================================
#  STEP 9 — Open browser (optional WebUI)
# ================================================================
if [[ "$ENABLE_WEBUI" == "1" ]]; then
    URL="http://localhost:${STREAMLIT_PORT}"
    streamlit_alive \
        && echo -e "  ${G}🟢 Streamlit  →  ${C}${URL}${N}" \
        || echo -e "  ${R}🔴 Streamlit :${STREAMLIT_PORT}${N}"
else
    echo -e "  ${Y}⚪ WebUI disabled (use launch.sh --webui to enable)${N}"
    sleep 5
fi
# ── Final status summary ──────────────────────────────────────────
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
if [[ "$ENABLE_WEBUI" == "1" ]]; then
streamlit_alive \
    && echo -e "  ${G}🟢 Streamlit  →  ${C}${URL}${N}" \
    || echo -e "  ${R}🔴 Streamlit :${STREAMLIT_PORT}${N}"
else
    echo -e "  ${Y}⚪ WebUI disabled (use launch.sh --webui to enable)${N}"
fi    
sep
sleep 5
echo ""
