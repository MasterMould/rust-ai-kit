write_scripts() {
    INSTALL_DIR="$HOME/ai_stack"
    BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
    LOG="$INSTALL_DIR/engine.log"
    PID_FILE="$INSTALL_DIR/.engine.pid"

    mkdir -p "$INSTALL_DIR"

    # ── START SCRIPT ─────────────────────────────
    cat > "$INSTALL_DIR/start_ai_stack.sh" <<EOF
#!/bin/bash
mkdir -p "$INSTALL_DIR"
nohup "$BIN" --port 8080 > "$LOG" 2>&1 &
echo \$! > "$PID_FILE"
echo "🚀 AI stack started (PID \$(cat $PID_FILE))"
EOF

    # ── STOP SCRIPT ─────────────────────────────
    cat > "$INSTALL_DIR/stop_ai_stack.sh" <<EOF
#!/bin/bash
PID_FILE="$PID_FILE"

if [[ -f "\$PID_FILE" ]]; then
    PID=\$(cat "\$PID_FILE")
    if kill -0 "\$PID" 2>/dev/null; then
        kill "\$PID"
        echo "🛑 Stopped AI stack (PID \$PID)"
    else
        echo "⚠️ Process not running"
    fi
    rm -f "\$PID_FILE"
else
    echo "⚠️ No PID file found"
fi
EOF

    chmod +x "$INSTALL_DIR/start_ai_stack.sh"
    chmod +x "$INSTALL_DIR/stop_ai_stack.sh"
}
