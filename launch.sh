#!/bin/bash
# ================================================================
#  rust-ai-kit  ·  Launch everything
#  Handles the startup race condition:
#    1. Start the AI stack (engine + memory + proxy) if not running
#    2. Wait until the engine API responds (up to 90s)
#    3. Start Streamlit if not already running
#    4. Wait until Streamlit responds (up to 30s)
#    5. Open the browser
#
#  Safe to run multiple times — idempotent. If everything is already
#  up it just opens the browser.
# ================================================================

set -euo pipefail

# ── Paths (match ai_stack_manager.sh exactly) ─────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/ai_stack"
LOG_DIR="$INSTALL_DIR/logs"
VENV="$SCRIPT_DIR/venv"
STREAMLIT="$VENV/bin/streamlit"
APP="$SCRIPT_DIR/llm_factory_rustaikit.py"
APP_LOG="$SCRIPT_DIR/logs/streamlit.log"
ENGINE_PORT=8080
PROXY_PORT=8090
STREAMLIT_PORT=8501

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/logs"

# ── Colours ────────────────────────────────────────────────────────
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' C='\033[0;36m' N='\033[0m'
ok()   { echo -e "${G}  ✅  $*${N}"; }
info() { echo -e "${C}  ℹ️   $*${N}"; }
warn() { echo -e "${Y}  ⚠️   $*${N}"; }
err()  { echo -e "${R}  ❌  $*${N}"; }

# Notify desktop if notify-send is available
_notify() {
    command -v notify-send &>/dev/null && \
        notify-send "🦀 rust-ai-kit" "$1" --icon=utilities-terminal 2>/dev/null || true
}

echo ""
echo -e "${C}  ╔══════════════════════════════════════════════╗"
echo -e "  ║   🦀  rust-ai-kit  —  Starting up           ║"
echo -e "  ╚══════════════════════════════════════════════╝${N}"
echo ""

# ================================================================
#  1. Source Intel oneAPI environment (same as _source_envs in manager)
# ================================================================
if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
    # shellcheck disable=SC1091
    source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true
fi
export ONEAPI_DEVICE_SELECTOR="level_zero:0"
export SYCL_DEVICE_FILTER="level_zero:gpu"
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env" 2>/dev/null || true

# ================================================================
#  2. Start AI stack if not already running
# ================================================================
engine_alive() {
    curl -sf \
         -H "Authorization: Bearer local" \
         "http://localhost:${ENGINE_PORT}/v1/models" &>/dev/null
}

if engine_alive; then
    ok "Engine already running on :${ENGINE_PORT}"
else
    info "Starting AI stack via ai_stack_manager.sh …"
    _notify "Starting AI stack…"

    MANAGER="$SCRIPT_DIR/ai_stack_manager.sh"
    if [[ ! -f "$MANAGER" ]]; then
        MANAGER="$HOME/rust-ai-kit/ai_stack_manager.sh"
    fi

    if [[ -f "$MANAGER" ]]; then
        # Send option 2 (Start) non-interactively
        echo "2" | bash "$MANAGER" >> "$LOG_DIR/launch.log" 2>&1 &
        MANAGER_PID=$!

        info "Waiting for engine API on :${ENGINE_PORT} (up to 90s) …"
        for i in $(seq 1 90); do
            sleep 1
            printf "\r  ${C}  Waiting… %2ds${N}" "$i"
            if engine_alive; then
                echo ""
                ok "Engine API live after ${i}s"
                break
            fi
            if (( i == 90 )); then
                echo ""
                err "Engine did not respond after 90s"
                warn "Check: tail -f $LOG_DIR/engine.log"
                _notify "Engine failed to start — check engine.log"
                # Don't exit — Streamlit can still start and show the error
            fi
        done
    else
        warn "ai_stack_manager.sh not found — skipping stack start"
        warn "Start the stack manually, then re-run this script"
    fi
fi

# ================================================================
#  3. Start Streamlit if not already running
# ================================================================
streamlit_alive() {
    curl -sf "http://localhost:${STREAMLIT_PORT}" &>/dev/null
}

if streamlit_alive; then
    ok "Streamlit already running on :${STREAMLIT_PORT}"
else
    if [[ ! -f "$STREAMLIT" ]]; then
        err "Streamlit not found at $STREAMLIT"
        err "Run:  make setup"
        read -rp "Press Enter to close…"
        exit 1
    fi

    if [[ ! -f "$APP" ]]; then
        err "App not found at $APP"
        read -rp "Press Enter to close…"
        exit 1
    fi

    info "Starting Streamlit on :${STREAMLIT_PORT} …"
    _notify "Starting Streamlit UI…"

    nohup "$STREAMLIT" run "$APP" \
        --server.port "$STREAMLIT_PORT" \
        --server.headless true \
        --server.address 0.0.0.0 \
        >> "$APP_LOG" 2>&1 &

    STREAMLIT_PID=$!
    echo "$STREAMLIT_PID" >> "$SCRIPT_DIR/logs/.streamlit_pid"

    info "Waiting for Streamlit on :${STREAMLIT_PORT} (up to 30s) …"
    for i in $(seq 1 30); do
        sleep 1
        printf "\r  ${C}  Waiting… %2ds${N}" "$i"
        if streamlit_alive; then
            echo ""
            ok "Streamlit live after ${i}s (PID $STREAMLIT_PID)"
            break
        fi
        if (( i == 30 )); then
            echo ""
            warn "Streamlit taking longer than expected — opening browser anyway"
            warn "Check: tail -f $APP_LOG"
        fi
    done
fi

# ================================================================
#  4. Open browser
# ================================================================
URL="http://localhost:${STREAMLIT_PORT}"
info "Opening $URL …"
_notify "LLM Factory ready → $URL"

if command -v xdg-open &>/dev/null; then
    xdg-open "$URL" &>/dev/null &
elif command -v firefox &>/dev/null; then
    firefox "$URL" &>/dev/null &
elif command -v chromium-browser &>/dev/null; then
    chromium-browser "$URL" &>/dev/null &
elif command -v google-chrome &>/dev/null; then
    google-chrome "$URL" &>/dev/null &
fi

echo ""
ok "All done!"
echo -e "  Browser: ${C}$URL${N}"
echo -e "  Engine:  ${C}http://localhost:${ENGINE_PORT}${N}"
echo -e "  Proxy:   ${C}http://localhost:${PROXY_PORT}${N}"
echo ""
echo "  This window will close in 5 seconds…"
sleep 5
