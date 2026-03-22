#!/bin/bash
# run-desktop.sh — Start wrapper for the LLM Factory .desktop icon.
# Opens a terminal, runs launch.sh, closes after 10 seconds.

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
LAUNCH="$SCRIPT_DIR/launch.sh"

if [[ ! -f "$LAUNCH" ]]; then
    command -v notify-send >/dev/null 2>&1 && \
        notify-send "rust-ai-kit ❌" "launch.sh not found in $SCRIPT_DIR" || true
    exit 1
fi

CMD="bash \"$LAUNCH\"; echo ''; echo '  Done — closing in 10 seconds...'; sleep 10"

if   command -v gnome-terminal  >/dev/null 2>&1; then
    exec gnome-terminal  --title="🦀 rust-ai-kit — Starting" -- bash -c "$CMD"
elif command -v xfce4-terminal  >/dev/null 2>&1; then
    exec xfce4-terminal  --title="🦀 rust-ai-kit — Starting" -x bash -c "$CMD"
elif command -v xterm            >/dev/null 2>&1; then
    exec xterm           -title  "rust-ai-kit — Starting"    -e  bash -c "$CMD"
else
    exec bash "$LAUNCH"
fi
