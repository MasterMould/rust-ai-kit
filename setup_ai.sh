#!/bin/bash
# AI Setup Script for Ubuntu (Llama.cpp + MemU + Rust Stack)

set -e

echo "🚀 Starting Rust-AI Stack Installation..."

# 1. Update and Install System Dependencies
sudo apt update && sudo apt install -y \
    libwebkit2gtk-4.0-dev build-essential git cmake curl libssl-dev pkg-config wget libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev

# 2. Install Rust
if ! command -v cargo &> /dev/null; then
    echo "🦀 Installing Rust..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source $HOME/.cargo/env
else
    echo "🦀 Rust is already installed."
fi

# 3. Setup LlamaEdge (Rust-native LLM Engine)
echo "🦙 Setting up LlamaEdge..."
curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh | bash
source $HOME/.wasmedge/env
# Download a lightweight model for initial testing (Llama 3.2 1B)
mkdir -p ~/models
curl -L -o ~/models/llama-3.2-1b.gguf https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf

# 4. Setup MemU (Rust Memory Layer)
echo "🧠 Installing MemU Memory Layer..."
git clone https://github.com/NevaMind-AI/memU.git ~/memu
cd ~/memu
cargo build --release
echo "✅ MemU built successfully."

# 5. Install UI (Llama-UI - Tauri/Rust based)
echo "🖥️ Setting up Llama-UI..."
# We use a pre-built AppImage for convenience, or build from source
# For novice ease, we will pull the latest Tauri-based release
# Replace URL with the latest stable version link
# curl -L -o ~/LlamaUI.AppImage [URL_TO_TAURI_APPIMAGE]
# chmod +x ~/LlamaUI.AppImage

echo "------------------------------------------------"
echo "🎉 Installation Complete!"
echo "To start the system:"
echo "1. Run the Engine: llama-server -m ~/models/llama-3.2-1b.gguf"
echo "2. Run MemU: cd ~/memu && ./target/release/memu"
echo "3. Open your UI to interact."
