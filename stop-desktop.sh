#!/bin/bash
# stop-desktop.sh — Stop wrapper for the "Stop Stack" .desktop icon.
# Kills llama-server, memory server, search proxy, and Streamlit.
# Shows results then closes the terminal after 5 seconds.

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
INSTALL_DIR="$HOME/ai_stack"
PID_FILE="$INSTALL_DIR/.pids"
STPID_FILE="$SCRIPT_DIR/logs/.streamlit_pid"

# ── Colours ────────────────────────────────────────────────────────
G='\033[0;32m' R='\033[0;31m' C='\033[0;36m' W='\033[1m' N='\033[0m'
ok()  { echo -e "${G}  ✅  $*${N}"; }
nope(){ echo -e "  ○   $* (not running)"; }

do_stop() {
    echo ""
    echo -e "${C}${W}  ╔══════════════════════════════════════════════╗"
    echo -e "  ║   🦀  rust-ai-kit  —  Stopping              ║"
    echo -e "  ╚══════════════════════════════════════════════╝${N}"
    echo ""

    # ── Systemd service ────────────────────────────────────────────
    if systemctl --user is-active llamaedge.service >/dev/null 2>&1; then
        systemctl --user stop llamaedge.service 2>/dev/null
        ok "Stopped llamaedge.service"
    fi

    # ── PID file ───────────────────────────────────────────────────
    if [[ -f "$PID_FILE" ]]; then
        while read -r pid; do
            [[ "$pid" =~ ^[0-9]+$ ]] || continue
            kill "$pid" 2>/dev/null && ok "Killed PID $pid (engine)"
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi

    # ── pkill by name ──────────────────────────────────────────────
    for svc in "llama-server" "search_proxy.py" "memory_server.py"; do
        if pkill -f "$svc" 2>/dev/null; then
            ok "Stopped $svc"
        else
            nope "$svc"
        fi
    done

    # ── Streamlit ──────────────────────────────────────────────────
    if [[ -f "$STPID_FILE" ]]; then
        STPID=$(cat "$STPID_FILE" 2>/dev/null)
        if [[ "$STPID" =~ ^[0-9]+$ ]]; then
            kill "$STPID" 2>/dev/null && ok "Stopped Streamlit (PID $STPID)"
        fi
        rm -f "$STPID_FILE"
    fi
    pkill -f "streamlit run" 2>/dev/null && ok "Stopped remaining Streamlit processes" || true

    echo ""
    echo -e "${G}  All services stopped.${N}"
    echo "  Closing in 5 seconds..."
    sleep 5
}

# ── Export function so bash -c can call it in the terminal ─────────
export -f do_stop
export INSTALL_DIR PID_FILE STPID_FILE G R C W N

CMD="do_stop"

if   command -v gnome-terminal  >/dev/null 2>&1; then
    exec gnome-terminal  --title="🦀 rust-ai-kit — Stopping" -- bash -c "do_stop"
elif command -v xfce4-terminal  >/dev/null 2>&1; then
    exec xfce4-terminal  --title="🦀 rust-ai-kit — Stopping" -x bash -c "do_stop"
elif command -v xterm            >/dev/null 2>&1; then
    exec xterm           -title  "rust-ai-kit — Stopping"    -e  bash -c "do_stop"
else
    do_stop
fi
