#!/bin/bash
# run-desktop.sh — launched by the .desktop icon.
# Finds itself via readlink so it works regardless of cwd or how it was invoked.

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
LAUNCH="$SCRIPT_DIR/launch.sh"

if [[ ! -f "$LAUNCH" ]]; then
    notify-send "rust-ai-kit" "launch.sh not found in $SCRIPT_DIR" 2>/dev/null || true
    exit 1
fi

INNER="\"$LAUNCH\"; echo ''; echo '  Done — closing in 10 seconds...'; sleep 10"

if command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal --title="🦀 rust-ai-kit" -- bash -c "$INNER"
elif command -v xfce4-terminal >/dev/null 2>&1; then
    exec xfce4-terminal --title="🦀 rust-ai-kit" -e "bash -c '$INNER'"
elif command -v xterm >/dev/null 2>&1; then
    exec xterm -title "rust-ai-kit" -e bash -c "$INNER"
else
    # No terminal — run headlessly (browser still opens via xdg-open in launch.sh)
    exec bash "$LAUNCH"
fi
