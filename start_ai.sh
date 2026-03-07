#!/bin/bash

# Configuration
MODEL_PATH="$HOME/models/llama-3.2-1b.gguf"
MEMU_PATH="$HOME/memu"

echo "🤖 Initializing Rust-AI Stack..."

# 1. Start LlamaEdge (The Engine)
# Running on port 8080 as an OpenAI-compatible API
wasmedge --dir .:. \
  wasmedge-ggml-llama-interactive.wasm \
  --model $MODEL_PATH \
  --ctx-size 4096 \
  --n_gpu_layers 999 \
  --port 8080 > ~/llama_engine.log 2>&1 &
ENGINE_PID=$!
echo "✅ LlamaEdge Engine started (PID: $ENGINE_PID)"

# 2. Wait for Engine to be ready
sleep 5

# 3. Start MemU (The Memory Layer)
cd $MEMU_PATH
./target/release/memu --api-url http://localhost:8080 > ~/memu_service.log 2>&1 &
MEMU_PID=$!
echo "✅ MemU Memory Layer started (PID: $MEMU_PID)"

# 4. Launch AnythingLLM (The UI)
# Assuming AnythingLLM is installed as an AppImage or in PATH
if command -v anythingllm &> /dev/null; then
    anythingllm &
    echo "✅ UI Launched."
else
    echo "⚠️ AnythingLLM not found in PATH. Please launch it manually."
fi

echo "------------------------------------------------"
echo "🚀 System is LIVE. Close this terminal to hide logs."
echo "To stop everything later, run: kill $ENGINE_PID $MEMU_PID"
