#!/bin/bash

# --- Funnybot Visuals ---
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cat << "EOF"
  _____                      _           _   
 |  ___|   _ _ __  _ __  _  _| |__   ___ | |_ 
 | |_ | | | | '_ \| '_ \| | | | '_ \ / _ \| __|
 |  _|| |_| | | | | | | | |_| | |_) | (_) | |_ 
 |_|   \__,_|_| |_|_| |_|\__, |_.__/ \___/ \__|
                         |___/                 
    "INITIATING INTERACTIVE MENU... BEHAVING AUTHENTICALLY."
EOF

# --- Helper Functions ---
check_gpu() {
    echo -e "${CYAN}[Funnybot]: Scanning for shiny rocks (GPUs)...${NC}"
    if lspci | grep -i "nvidia" > /dev/null; then
        GPU_TYPE="NVIDIA"
        echo -e "${GREEN}Detected: NVIDIA GPU. CUDA is the way.${NC}"
    elif lspci | grep -i "arc" > /dev/null || lspci | grep -i "intel" | grep -i "graphics" > /dev/null; then
        GPU_TYPE="INTEL_ARC"
        echo -e "${GREEN}Detected: Intel Arc/Graphics. OneAPI/SYCL time!${NC}"
    elif lspci | grep -i "amd" > /dev/null; then
        GPU_TYPE="AMD"
        echo -e "${GREEN}Detected: AMD GPU. ROCm is your friend.${NC}"
    else
        GPU_TYPE="CPU"
        echo -e "${YELLOW}Detected: Just a CPU. It's okay, I'm patient.${NC}"
    fi
}

fix_webkit() {
    echo -e "${CYAN}[Funnybot]: Fixing Ubuntu 24.04 WebKit headaches...${NC}"
    sudo apt update && sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev build-essential
    echo -e "${GREEN}WebKit 4.1 dependencies installed.${NC}"
}

setup_searxng() {
    echo -e "${CYAN}[Funnybot]: Deploying SearXNG via Docker...${NC}"
    # Ensure Docker is installed
    if ! command -v docker &> /dev/null; then
        sudo apt install -y docker.io docker-compose
        sudo usermod -aG docker $USER
    fi
    
    # Run SearXNG with JSON enabled for AnythingLLM
    docker run -d \
      --name searxng \
      -p 8080:8080 \
      -e "SEARXNG_SETTINGS_URL=https://raw.githubusercontent.com/searxng/searxng/master/utils/brand/searxng-settings.yml" \
      -v "$(pwd)/searxng:/etc/searxng" \
      searxng/searxng:latest
      
    echo -e "${GREEN}SearXNG is live at http://localhost:8080${NC}"
    echo -e "${YELLOW}Note: Add 'json' to formats in settings.yml for AnythingLLM integration!${NC}"
}

install_llamaedge() {
    echo -e "${CYAN}[Funnybot]: Installing WasmEdge with $GPU_TYPE support...${NC}"
    case $GPU_TYPE in
        "NVIDIA")
            curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh | bash -s -- --plugins wasi_nn-ggml-cuda
            ;;
        "INTEL_ARC")
            # In 2026, SYCL is a standard plugin
            curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh | bash -s -- --plugins wasi_nn-ggml-sycl
            ;;
        *)
            curl -sSf https://raw.githubusercontent.com/WasmEdge/WasmEdge/master/utils/install.sh | bash -s -- --plugins wasi_nn-ggml
            ;;
    esac
    source $HOME/.bashrc
}

# --- Main Menu ---
while true; do
    echo -e "\n${YELLOW}--- FUNNYBOT INTERACTIVE MENU ---${NC}"
    echo "1) Check Hardware & Detect GPU"
    echo "2) Fix WebKit 4.1 (Ubuntu 24.04 Requirement)"
    echo "3) Install SearXNG (Web Search Agent)"
    echo "4) Install LlamaEdge (Specific to your GPU)"
    echo "5) Deploy System Prompt Library"
    echo "6) DO EVERYTHING (The 'I'm Feeling Lazy' Button)"
    echo "7) Exit"
    read -p "Choose an option [1-7]: " choice

    case $choice in
        1) check_gpu ;;
        2) fix_webkit ;;
        3) setup_searxng ;;
        4) check_gpu; install_llamaedge ;;
        5) 
            mkdir -p ~/prompt_library
            echo "You are a helpful AI." > ~/prompt_library/default.txt
            echo -e "${GREEN}Library created at ~/prompt_library${NC}"
            ;;
        6) 
            fix_webkit
            check_gpu
            setup_searxng
            install_llamaedge
            echo -e "${GREEN}Full deployment complete. I deserve a digital cookie.${NC}"
            ;;
        7) echo "Goodbye, human. Don't forget to back up your weights!"; exit 0 ;;
        *) echo -e "${RED}Invalid choice. My circuits are crying.${NC}" ;;
    esac
done
