#!/bin/bash
# run-desktop.sh — launched by the .desktop icon.
# Opens a terminal window, runs launch.sh, then closes it after 10 seconds.
# This script contains all the shell logic so the .desktop Exec stays clean.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCH="$SCRIPT_DIR/launch.sh"

# The inner command passed to the terminal emulator.
# launch.sh runs, then a 10-second countdown is shown before the window closes.
INNER="bash -c '\"$LAUNCH\"; echo \"\"; echo \"  Closing in 10 seconds...\"; sleep 10'"

if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal \
        --title="🦀 rust-ai-kit Startup" \
        -- bash -c "\"$LAUNCH\"; echo ''; echo '  Closing in 10 seconds...'; sleep 10"
elif command -v xfce4-terminal >/dev/null 2>&1; then
    xfce4-terminal \
        --title="🦀 rust-ai-kit Startup" \
        --command="bash -c '\"$LAUNCH\"; echo \"\"; echo \"  Closing in 10 seconds...\"; sleep 10'"
elif command -v xterm >/dev/null 2>&1; then
    xterm \
        -title "rust-ai-kit Startup" \
        -e bash -c "\"$LAUNCH\"; echo ''; echo '  Closing in 10 seconds...'; sleep 10"
else
    # No terminal found — run headlessly, browser will open via xdg-open
    bash "$LAUNCH"
fi
