#!/bin/bash
# stack-manager-desktop.sh — Opens ai_stack_manager.sh in a terminal.
# The manager is fully interactive so the terminal stays open until the
# user exits (option 0).

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
MANAGER="$SCRIPT_DIR/ai_stack_manager.sh"

if [[ ! -f "$MANAGER" ]]; then
    command -v notify-send >/dev/null 2>&1 && \
        notify-send "rust-ai-kit ❌" "ai_stack_manager.sh not found in $SCRIPT_DIR" || true
    exit 1
fi

chmod +x "$MANAGER"

# Keep terminal open until user exits the manager (option 0 / Ctrl-C)
CMD="bash \"$MANAGER\"; echo ''; echo '  Manager closed.'; sleep 2"

if   command -v gnome-terminal  >/dev/null 2>&1; then
    exec gnome-terminal  --title="🦀 rust-ai-kit — Stack Manager" -- bash -c "$CMD"
elif command -v xfce4-terminal  >/dev/null 2>&1; then
    exec xfce4-terminal  --title="🦀 rust-ai-kit — Stack Manager" -x bash -c "$CMD"
elif command -v xterm            >/dev/null 2>&1; then
    exec xterm           -title  "rust-ai-kit — Stack Manager"    -e  bash -c "$CMD"
else
    exec bash "$MANAGER"
fi
