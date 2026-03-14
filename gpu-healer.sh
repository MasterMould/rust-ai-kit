#!/bin/bash

# --- CONFIG ---
COMMAND_NAME="gpu-fix"
SCRIPT_PATH=$(readlink -f "$0")
INTEL_KEY_URL="https://repositories.intel.com/gpu/intel-graphics.key"
INTEL_REPO_LINE="deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu noble/lts/2350 unified"

# --- UI COLORS ---
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

# --- 1. SMART SETUP ---
if [[ ! -L "/usr/local/bin/$COMMAND_NAME" ]]; then
    echo -e "${CYAN}First run: Enable global command '$COMMAND_NAME'? (y/n)${NC}"
    read -n 1 -r; echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo ln -sf "$SCRIPT_PATH" "/usr/local/bin/$COMMAND_NAME"
        sudo chmod +x "$SCRIPT_PATH"
        echo -e "${GREEN}Global command enabled. Use '$COMMAND_NAME' anywhere.${NC}"
    fi
fi

# --- 2. THE DIAGNOSTIC ENGINE ---
diagnose_system() {
    echo -e "${CYAN}--- Diagnostic Report ---${NC}"
    
    # Check GPG Key
    if [ ! -f /usr/share/keyrings/intel-graphics.gpg ]; then
        echo -e "[${RED}FAIL${NC}] Intel GPG Key missing."
    else
        echo -e "[${GREEN} OK ${NC}] Intel GPG Key present."
    fi

    # Check for Duplicate Files
    DUPES=$(ls /etc/apt/sources.list.d/intel-* 2>/dev/null | wc -l)
    if [ "$DUPES" -gt 1 ]; then
        echo -e "[${YELLOW}WARN${NC}] Multiple Intel repo files found ($DUPES). This causes warnings."
    fi

    # Check if GPU is initialized
    if ! lspci -k | grep -A 3 "VGA" | grep -qi "i915\|xe"; then
        echo -e "[${RED}FAIL${NC}] No Intel Kernel Driver (i915/xe) bound to GPU."
    fi

    # Check Runtimes for Rust/AI
    if ! ldconfig -p | grep -q "libze_intel"; then
        echo -e "[${YELLOW}WARN${NC}] Level Zero runtime (required for AI) not found."
    fi
}

# --- 3. THE MENU ---
while true; do
    echo -e "\n${CYAN}Intel Arc A770 Manager v2.0${NC}"
    diagnose_system
    echo -e "\n${YELLOW}Actions:${NC}"
    echo "1) AUTO-HEAL (Fix Keys, Repos, and Duplicates in one go)"
    echo "2) Full System Clean (Nuke cache + Fix broken packages)"
    echo "3) Install AI/Compute Stack (OpenCL, Level-Zero, Headers)"
    echo "4) Hardware Bench/Check (Monitor GPU load)"
    echo "q) Exit"
    read -p "Selection: " choice

    case $choice in
        1)
            echo "Healing..."
            wget -qO - $INTEL_KEY_URL | sudo gpg --yes --dearmor -o /usr/share/keyrings/intel-graphics.gpg
            sudo rm -f /etc/apt/sources.list.d/intel-graphics.list /etc/apt/sources.list.d/intel-gpu.list
            echo "$INTEL_REPO_LINE" | sudo tee /etc/apt/sources.list.d/intel-gpu-noble.list
            sudo apt update
            ;;
        2)
            sudo apt clean && sudo rm -rf /var/lib/apt/lists/*
            sudo apt install -f && sudo dpkg --configure -a && sudo apt update
            ;;
        3)
            sudo apt install -y intel-opencl-icd intel-level-zero-gpu level-zero intel-media-va-driver-non-free linux-headers-$(uname -r)
            ;;
        4)
            if command -v intel_gpu_top &> /dev/null; then
                sudo intel_gpu_top
            else
                echo "Installing GPU tools..."
                sudo apt install -y intel-gpu-tools && sudo intel_gpu_top
            fi
            ;;
        q) exit 0 ;;
    esac
done