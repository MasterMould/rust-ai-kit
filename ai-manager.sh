#!/bin/bash
# AI Management Dashboard for Ubuntu (Rust-Stack)

# Configuration Variables
INSTALL_DIR="$HOME/ai_stack"
MODEL_PATH="$INSTALL_DIR/models/llama-3.2-1b.gguf"
MEMU_DIR="$INSTALL_DIR/memu"
ENGINE_PORT=8080
UI_INSTALLER="https://raw.githubusercontent.com/Mintplex-Labs/anything-llm/desktop/linux_installer.sh"

# Text Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_menu() {
    clear
    echo -e "${BLUE}========================================"
    echo -e "   🤖 RUST-AI STACK MANAGER (UBUNTU)"
    echo -e "========================================${NC}"
    echo "1) Full Automated Install "
    echo "2) Start AI Stack (Manual)"
    echo "3) Stop AI Stack"
    echo "4) Enable Auto-Start on Boot (Systemd)"
    echo "5) Disable Auto-Start"
    echo "6) Check Status"
    echo "----------------------------------------"
    echo "7) Setup Web Search (Install SearXNG)"
    echo "8) Exit"
    echo -n "Select an option: "
}

install_stack() {
    echo -e "${BLUE}Starting installation...${NC}"
    mkdir -p "$INSTALL_DIR/models"
    
    # 1. Install Dependencies
    sudo apt update && sudo apt install -y build-essential git cmake curl libssl-dev pkg-config libwebkit2gtk-4.0-dev
    
    # 2. Install Rust
    if ! command -v cargo &> /dev/null; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
        source "$HOME/.cargo/env"
    fi

    # 3. Setup LlamaEdge
    curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh | bash
    source "$HOME/.wasmedge/env"
    curl -L -o "$INSTALL_DIR/llama-api-server.wasm" https://github.com/LlamaEdge/LlamaEdge/releases/latest/download/llama-api-server.wasm
    curl -L -o "$MODEL_PATH" https://huggingface.co/second-state/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q5_K_M.gguf

    # 4. Build MemU (Rust version)
    git clone https://github.com/NevaMind-AI/memU "$MEMU_DIR"
    cd "$MEMU_DIR" && cargo build --release
    
    # 5. Install AnythingLLM (UI)
    curl -fsSL "$UI_INSTALLER" | bash
    
    echo -e "${GREEN}Installation Complete!${NC}"
    read -p "Press enter to return to menu..."
}

setup_web_search() {
    echo "🌐 Setting up SearXNG for private web search..."
    # We use Docker for SearXNG as it's the most stable way to run it on Ubuntu
    if ! command -v docker &> /dev/null; then
        sudo apt install -y docker.io docker-compose
    fi
    
    # Run SearXNG
    docker run -d -p 8081:8080 --name searxng \
        -e "SEARXNG_SETTINGS_URL=https://raw.githubusercontent.com/searxng/searxng/master/utils/brand/searxng-settings.yml" \
        searxng/searxng:latest
        
    echo -e "\033[0;32m✅ SearXNG is live at $SEARXNG_URL\033[0m"
    echo "To connect AnythingLLM:"
    echo "1. Open AnythingLLM > Workspace Settings > Agent Configuration."
    echo "2. Select 'SearXNG' as the search provider."
    echo "3. Enter Base URL: http://localhost:8081"
    read -p "Press enter to continue..."
}

setup_systemd() {
    echo "Creating systemd user services..."
    mkdir -p "$HOME/.config/systemd/user/"

    # LlamaEdge Service
    cat <<EOF > "$HOME/.config/systemd/user/llamaedge.service"
[Unit]
Description=LlamaEdge Engine
After=network.target

[Service]
ExecStart=$(which wasmedge) --dir .:. --nn-preload default:GGML:AUTO:$MODEL_PATH $INSTALL_DIR/llama-api-server.wasm -p llama-3-chat --port $ENGINE_PORT
Restart=always

[Install]
WantedBy=default.target
EOF

    # MemU Service
    cat <<EOF > "$HOME/.config/systemd/user/memu.service"
[Unit]
Description=MemU Persistent Memory
After=llamaedge.service

[Service]
WorkingDirectory=$MEMU_DIR
ExecStart=$MEMU_DIR/target/release/memu --api-url http://localhost:$ENGINE_PORT
Restart=always

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable llamaedge.service memu.service
    loginctl enable-linger $USER
    echo -e "${GREEN}Auto-start enabled! AI will run in background on boot.${NC}"
    read -p "Press enter..."
}

# --- Main Loop ---
while true; do
    show_menu
    read opt
    case $opt in
        1) install_stack ;;
        2) systemctl --user start llamaedge.service memu.service && echo "Stack started!" ;;
        3) systemctl --user stop llamaedge.service memu.service && echo "Stack stopped!" ;;
        4) setup_systemd ;;
        5) systemctl --user disable llamaedge.service memu.service && echo "Auto-start disabled." ;;
        6) systemctl --user status llamaedge.service memu.service ;;
        7) setup_web_search ;;
        8) exit 0 ;;
        *) echo "Invalid option." ;;
    esac
done
