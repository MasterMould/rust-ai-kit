#!/bin/bash
# ================================================================
#  stop-server.sh
#  Stops llama-server, search proxy, and memory server.
#  Can be run from a terminal, a .desktop icon, or the Makefile.
#  Optionally opens a brief terminal window to show the result
#  (set SHOW_WINDOW=1 for desktop-icon invocations).
# ================================================================

INSTALL_DIR="$HOME/ai_stack"
PID_FILE="$INSTALL_DIR/.pids"

G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' C='\033[0;36m' N='\033[0m'
ok()   { echo -e "${G}  ✅  $*${N}"; }
warn() { echo -e "${Y}  ⚠   $*${N}"; }
err()  { echo -e "${R}  ✗   $*${N}"; }
sep()  { echo -e "${C}  ────────────────────────────────────────────${N}"; }

_stop() {
    echo ""
    echo -e "${C}  🛑  Stopping rust-ai-kit stack…${N}"
    sep

    # 1. Kill by PID file
    if [[ -f "$PID_FILE" ]]; then
        while IFS= read -r pid; do
            [[ -z "$pid" ]] && continue
            if kill -0 "$pid" 2>/dev/null; then
                kill -15 "$pid" 2>/dev/null || true
                ok "Sent SIGTERM to PID $pid"
            fi
        done < "$PID_FILE"
        rm -f "$PID_FILE"
    fi

    # 2. pkill by process name (catches any survivors)
    local stopped_any=false
    for pattern in "llama-server" "search_proxy.py" "memory_server.py"; do
        if pkill -f "$pattern" 2>/dev/null; then
            ok "Stopped: $pattern"
            stopped_any=true
        fi
    done

    # 3. systemd unit (if enabled)
    if systemctl --user is-active --quiet llamaedge.service 2>/dev/null; then
        systemctl --user stop llamaedge.service 2>/dev/null
        ok "Stopped: llamaedge.service"
        stopped_any=true
    fi

    # 4. Free the engine port (belt + braces)
    local stale
    stale=$(lsof -ti ":8080" 2>/dev/null | head -1)
    if [[ -n "$stale" ]]; then
        kill -9 "$stale" 2>/dev/null || true
        ok "Released port 8080 (PID $stale)"
    fi

    sep

    # Final status
    sleep 1
    if curl -sf -H "Authorization: Bearer local" \
            http://localhost:8080/v1/models >/dev/null 2>&1; then
        warn "Engine still responding on :8080 — may need a moment to shut down."
    else
        ok "Engine offline."
    fi

    # Desktop notification
    command -v notify-send >/dev/null 2>&1 && \
        notify-send "🦀 rust-ai-kit" "Server stopped." --icon=utilities-terminal 2>/dev/null || true

    echo ""
}

# ── Main ─────────────────────────────────────────────────────────
if [[ "${SHOW_WINDOW:-0}" == "1" ]]; then
    # Called from a .desktop icon — run inside a brief terminal window
    SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
    INNER="bash \"$SCRIPT_DIR/stop-server.sh\"; echo ''; read -rp \"  Press Enter to close…\" _"

    if command -v gnome-terminal >/dev/null 2>&1; then
        exec gnome-terminal --title="🦀 Stop Server" --geometry=80x20 \
            -- bash -c "$INNER"
    elif command -v xfce4-terminal >/dev/null 2>&1; then
        exec xfce4-terminal --title="🦀 Stop Server" --geometry=80x20 \
            --command="bash -c '$INNER'"
    elif command -v xterm >/dev/null 2>&1; then
        exec xterm -title "Stop Server" -geometry 80x20 \
            -e bash -c "$INNER"
    fi
fi

# Normal (non-windowed) execution
_stop
