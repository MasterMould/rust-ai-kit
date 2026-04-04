#!/bin/bash

create_runtime_scripts() {
    STEP "Creating runtime scripts"

    mkdir -p "$INSTALL_DIR"

    cat > "$INSTALL_DIR/start_ai_stack.sh" <<EOF
#!/bin/bash
source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1
export ONEAPI_DEVICE_SELECTOR="level_zero:0"

$LLAMACPP_BIN \
  --model "$MODEL_PATH" \
  --ctx-size $DEFAULT_CTX \
  --n-gpu-layers 99 \
  --port 8080
EOF

    cat > "$INSTALL_DIR/stop_ai_stack.sh" <<'EOF'
#!/bin/bash
echo "🛑 Stopping AI stack..."

pkill -f llama-server && echo "Stopped llama-server" || echo "llama-server not running"
pkill -f memu && echo "Stopped memory server" || true
pkill -f searxng && echo "Stopped search proxy" || true

echo "✅ All services stopped."
EOF

    chmod +x "$INSTALL_DIR/"*.sh

    OK "Runtime scripts ready"
}
