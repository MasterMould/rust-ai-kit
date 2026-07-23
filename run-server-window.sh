#!/bin/bash
# ================================================================
#  run-server-window.sh
#  Opens a terminal window running server-window.sh.
#  Called by the .desktop icon, Makefile, and the Streamlit UI.
#  Tries terminals in order: gnome-terminal → xfce4-terminal →
#  konsole → mate-terminal → xterm → (headless fallback)
# ================================================================
SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
INNER="$SCRIPT_DIR/server-window.sh"

if [[ ! -f "$INNER" ]]; then
    notify-send "rust-ai-kit" "server-window.sh not found in $SCRIPT_DIR" 2>/dev/null || true
    echo "ERROR: server-window.sh not found at $INNER" >&2
    exit 1
fi

TITLE="🦀 rust-ai-kit — llama-server"

if command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal \
        --title="$TITLE" \
        --geometry=120x40 \
        -- bash "$INNER"

elif command -v xfce4-terminal >/dev/null 2>&1; then
    exec xfce4-terminal \
        --title="$TITLE" \
        --geometry=120x40 \
        --command="bash \"$INNER\""

elif command -v konsole >/dev/null 2>&1; then
    exec konsole \
        --title "$TITLE" \
        -e bash "$INNER"

elif command -v mate-terminal >/dev/null 2>&1; then
    exec mate-terminal \
        --title="$TITLE" \
        --geometry=120x40 \
        -e "bash \"$INNER\""

elif command -v xterm >/dev/null 2>&1; then
    exec xterm \
        -title "$TITLE" \
        -geometry 120x40 \
        -fa "Monospace" -fs 11 \
        -bg "#1e1e2e" -fg "#cdd6f4" \
        -e bash "$INNER"

else
    # No GUI terminal — run headlessly and open browser
    notify-send "rust-ai-kit" \
        "No terminal emulator found. Starting server in background." 2>/dev/null || true
    nohup bash "$INNER" >> "$SCRIPT_DIR/logs/engine.log" 2>&1 &
fi
