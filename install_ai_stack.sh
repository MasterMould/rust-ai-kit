#!/bin/bash
# ================================================================
#  🤖  LOCAL AI STACK INSTALLER  —  Ubuntu 24.04
#  GPU: Intel Arc A770 (SYCL/oneAPI backend)
#  Components: WasmEdge+GGML-SYCL · LlamaEdge · MemU · AnythingLLM
# ================================================================

set -euo pipefail

# ── Colours ─────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m'
C='\033[0;36m' W='\033[1m' N='\033[0m'
OK()   { echo -e "${G}  ✅  $*${N}"; }
INFO() { echo -e "${C}  ℹ️   $*${N}"; }
WARN() { echo -e "${Y}  ⚠️   $*${N}"; }
ERR()  { echo -e "${R}  ❌  $*${N}"; exit 1; }
STEP() { echo -e "\n${W}${C}━━━  $*  ━━━${N}"; }

# ── Paths ────────────────────────────────────────────────────────
INSTALL_DIR="$HOME/ai_stack"
MODEL_DIR="$INSTALL_DIR/models"
MEMU_DIR="$INSTALL_DIR/memu"
APPS_DIR="$HOME/Applications"

# ── Versions / URLs ──────────────────────────────────────────────
LLAMACPP_REPO="https://github.com/ggerganov/llama.cpp"
LLAMACPP_DIR="$INSTALL_DIR/llama.cpp"
LLAMACPP_BIN="$LLAMACPP_DIR/build/bin/llama-server"
MEMU_REPO="https://github.com/NevaMind-AI/memU"
ANYTHINGLLM_APPIMAGE_URL="https://cdn.anythingllm.com/latest/AnythingLLMDesktop-x86_64.AppImage"

# ── Model choice ─────────────────────────────────────────────────
# A770 has 16 GB VRAM — use a proper 8B model instead of the tiny 1B
# Llama-3.1-8B-Instruct Q4_K_M  ≈ 4.9 GB  — fits easily, much better quality
MODEL_NAME="Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"

# ── Helper ───────────────────────────────────────────────────────
ask() {
    local yn="[Y/n]"; [[ "${2:-y}" == "n" ]] && yn="[y/N]"
    read -rp "$(echo -e "${Y}  ❓  $1 $yn: ${N}")" r
    r="${r:-${2:-y}}"
    [[ "${r,,}" == "y" ]]
}
PAUSE() { read -rp "$(echo -e "${Y}  Press Enter to continue…${N}")"; }

# ================================================================
#  PREFLIGHT
# ================================================================
preflight() {
    STEP "System check"
    [[ "$(uname -m)" == "x86_64" ]] || ERR "x86_64 required."

    echo -e "${W}  GPU detection:${N}"
    if lspci | grep -qi "Arc A770"; then
        OK "Intel Arc A770 detected."
    else
        WARN "Could not confirm Arc A770 via lspci. Proceeding anyway — verify your GPU."
        lspci | grep -i "VGA\|Display\|3D" || true
    fi

    echo ""
    INFO "Available disk: $(df -h "$HOME" | awk 'NR==2{print $4}') free"
    WARN "The 8B model download is ~5 GB. Ensure you have ~8 GB free total."
    ask "Continue?" || exit 0
}

# ================================================================
#  STEP 1 — System packages
# ================================================================
install_system_deps() {
    STEP "1/7  System packages"
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
        curl wget git build-essential cmake pkg-config \
        libssl-dev ca-certificates unzip file libfuse2 \
        libwebkit2gtk-4.1-dev libgtk-3-dev \
        gpg-agent software-properties-common \
        ocl-icd-libopencl1           # OpenCL ICD loader
    OK "System packages installed."
}

# ================================================================
#  STEP 2 — Intel GPU drivers + level-zero (Arc A770)
# ================================================================
install_intel_gpu_drivers() {
    STEP "2/7  Intel Arc A770 GPU drivers"

    # ── Intel compute-runtime (OpenCL ICD + level-zero) ──────────
    # Don't blindly reinstall — check what's present first.
    # The system may already have libze-intel-gpu1 or intel-opencl-icd
    # from a prior install; removing them would break things.
    INFO "Checking Intel compute-runtime packages…"
    local need_opencl=0 need_ze=0
    dpkg -l intel-opencl-icd 2>/dev/null | grep -q '^ii' || need_opencl=1
    dpkg -l libze1 libze-intel-gpu1 2>/dev/null \
        | grep -qE '^ii.*(libze1|libze-intel-gpu1)' && need_ze=0 || need_ze=1

    if [[ $need_opencl -eq 0 && $need_ze -eq 0 ]]; then
        OK "Intel compute-runtime already installed — skipping."
    else
        local PKGS=()
        [[ $need_opencl -eq 1 ]] && PKGS+=("intel-opencl-icd")
        if [[ $need_ze -eq 1 ]]; then
            apt-cache show libze1 &>/dev/null && PKGS+=("libze1") || true
        fi
        [[ ${#PKGS[@]} -gt 0 ]] && sudo apt-get install -y "${PKGS[@]}" || true
        OK "Intel compute-runtime packages ready."
    fi

    sudo apt-get install -y --no-install-recommends clinfo libze-dev || true

    # ── Intel oneAPI — compiler + runtime ─────────────────────────
    # intel-oneapi-runtime-dpcpp-cpp  = runtime libs only (no icx/icpx)
    # intel-oneapi-dpcpp-cpp          = actual SYCL compiler (icx/icpx)
    # We need the COMPILER to build llama.cpp; runtime alone is not enough.
    INFO "Checking Intel oneAPI compiler…"

    # Find icx wherever oneAPI may have put it
    local ICX_BIN=""
    ICX_BIN=$(command -v icx 2>/dev/null) \
        || ICX_BIN=$(find /opt/intel/oneapi -name icx -type f 2>/dev/null | head -1) \
        || true

    if [[ -n "$ICX_BIN" ]]; then
        OK "Intel icx compiler found: $ICX_BIN"
    else
        INFO "Installing Intel oneAPI compiler (intel-oneapi-dpcpp-cpp)…"
        # Ensure the oneAPI repo is present
        if [[ ! -f /etc/apt/sources.list.d/oneAPI.list ]]; then
            wget -qO - https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
                | sudo gpg --yes --dearmor \
                    -o /usr/share/keyrings/oneapi-archive-keyring.gpg
            echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] \
https://apt.repos.intel.com/oneapi all main" \
                | sudo tee /etc/apt/sources.list.d/oneAPI.list
            sudo apt-get update -qq || true
        fi
        # intel-oneapi-compiler-dpcpp-cpp = icx/icpx compilers + setvars.sh
        # (intel-oneapi-runtime-dpcpp-cpp is runtime only — no compilers)
        sudo apt-get install -y intel-oneapi-compiler-dpcpp-cpp
        ICX_BIN=$(command -v icx 2>/dev/null) \
            || ICX_BIN=$(find /opt/intel/oneapi -name icx -type f 2>/dev/null | head -1) \
            || true
        [[ -n "$ICX_BIN" ]] && OK "icx installed: $ICX_BIN" \
            || ERR "icx still not found after install — check apt output above."
    fi

    # ── Groups + verify ───────────────────────────────────────────
    sudo usermod -aG render,video "$USER" 2>/dev/null || true
    OK "User added to render/video groups (re-login to take effect)."

    INFO "GPU visibility check:"
    clinfo -l 2>/dev/null | grep -i "intel\|Arc" \
        || WARN "clinfo shows no Intel GPU — reboot may be required."
}

# ================================================================
#  STEP 3 — Rust
# ================================================================
install_rust() {
    STEP "3/7  Rust toolchain"
    if command -v cargo &>/dev/null; then
        OK "Rust already present: $(rustc --version)"
    else
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
        source "$HOME/.cargo/env"
        OK "Rust installed: $(rustc --version)"
    fi
    export PATH="$HOME/.cargo/bin:$PATH"
}

# ================================================================
#  STEP 4 — llama.cpp built with SYCL (Intel Arc A770)
# ================================================================
install_llamacpp_sycl() {
    STEP "4/7  llama.cpp + SYCL backend (Intel Arc A770)"

    if [[ -f "$LLAMACPP_BIN" ]]; then
        OK "llama-server already built: $LLAMACPP_BIN"
        return
    fi

    # ── Locate Intel icx/icpx compilers ──────────────────────────
    # setvars.sh may not exist if only the compiler package (not full
    # toolkit) is installed. Find icx directly in the oneAPI tree.
    local ICX_BIN ICPX_BIN ONEAPI_BIN
    ICX_BIN=$(command -v icx 2>/dev/null) \
        || ICX_BIN=$(find /opt/intel/oneapi -name icx  -type f 2>/dev/null | sort -r | head -1) \
        || true
    ICPX_BIN=$(command -v icpx 2>/dev/null) \
        || ICPX_BIN=$(find /opt/intel/oneapi -name icpx -type f 2>/dev/null | sort -r | head -1) \
        || true

    if [[ -z "$ICX_BIN" || -z "$ICPX_BIN" ]]; then
        ERR "Intel icx/icpx compilers not found. Make sure step 2 installed intel-oneapi-dpcpp-cpp."
    fi

    ONEAPI_BIN=$(dirname "$ICX_BIN")
    export PATH="$ONEAPI_BIN:$PATH"

    # Source setvars.sh if it exists (sets library paths), otherwise set manually
    if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
        source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1
    else
        # Find the SYCL runtime lib dir and add it
        local SYCL_LIB
        SYCL_LIB=$(find /opt/intel/oneapi -name "libsycl.so*" -type f 2>/dev/null \
                   | head -1 | xargs dirname 2>/dev/null) || true
        [[ -n "$SYCL_LIB" ]] && export LD_LIBRARY_PATH="$SYCL_LIB:${LD_LIBRARY_PATH:-}"
    fi

    OK "Using Intel compilers: $ICX_BIN / $ICPX_BIN"

    # Extra build deps
    INFO "Installing build dependencies…"
    sudo apt-get install -y --no-install-recommends \
        ninja-build libopenblas-dev

    # Clone or update
    if [[ -d "$LLAMACPP_DIR/.git" ]]; then
        INFO "Updating llama.cpp repo…"
        git -C "$LLAMACPP_DIR" pull --ff-only
    else
        INFO "Cloning llama.cpp…"
        git clone --depth=1 "$LLAMACPP_REPO" "$LLAMACPP_DIR"
    fi

    INFO "Configuring cmake with SYCL backend…"
    cmake -B "$LLAMACPP_DIR/build" \
        -S "$LLAMACPP_DIR" \
        -G Ninja \
        -DGGML_SYCL=ON \
        -DCMAKE_C_COMPILER="$ICX_BIN" \
        -DCMAKE_CXX_COMPILER="$ICPX_BIN" \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_SYCL_F16=ON

    INFO "Building llama.cpp (using $(nproc) cores — takes a few minutes)…"
    cmake --build "$LLAMACPP_DIR/build" --config Release -j"$(nproc)"

    [[ -f "$LLAMACPP_BIN" ]] \
        && OK "llama-server built → $LLAMACPP_BIN" \
        || ERR "Build completed but llama-server binary not found — check build output above."
}

# ================================================================
#  STEP 5 — Model (8B now that we have 16 GB VRAM)
# ================================================================
download_model() {
    STEP "5/7  LLM model (Llama-3.1-8B Q4_K_M, ~5 GB)"
    INFO "The A770's 16 GB VRAM easily fits this model fully on-GPU."
    mkdir -p "$MODEL_DIR"
    if [[ -f "$MODEL_PATH" ]]; then
        OK "Model already present: $MODEL_PATH"
    else
        INFO "Downloading from Hugging Face — grab a coffee ☕…"
        wget -q --show-progress -O "$MODEL_PATH" "$MODEL_URL"
        OK "Model saved → $MODEL_PATH"
    fi
}

# ================================================================
#  STEP 6 — MemU
# ================================================================
install_memu() {
    STEP "6/7  MemU"
    if [[ -f "$MEMU_DIR/target/release/memu" ]]; then
        OK "MemU already built."
    else
        [[ -d "$MEMU_DIR/.git" ]] \
            && git -C "$MEMU_DIR" pull --ff-only \
            || git clone "$MEMU_REPO" "$MEMU_DIR"
        INFO "Building MemU…"
        cargo build --release --manifest-path "$MEMU_DIR/Cargo.toml"
        OK "MemU built."
    fi
}

# ================================================================
#  STEP 7 — AnythingLLM
# ================================================================
install_anythingllm() {
    STEP "7/7  AnythingLLM"
    mkdir -p "$APPS_DIR"
    local ai="$APPS_DIR/AnythingLLM.AppImage"
    if [[ -f "$ai" ]]; then
        OK "AnythingLLM already present."
    elif ask "Download AnythingLLM AppImage?"; then
        wget -q --show-progress -O "$ai" "$ANYTHINGLLM_APPIMAGE_URL"
        chmod +x "$ai"
        mkdir -p "$HOME/.local/share/applications" "$HOME/.local/bin"
        cat > "$HOME/.local/share/applications/anythingllm.desktop" <<DESK
[Desktop Entry]
Name=AnythingLLM
Exec=$ai
Icon=utilities-terminal
Type=Application
Categories=Office;AI;
DESK
        ln -sf "$ai" "$HOME/.local/bin/anythingllm"
        OK "AnythingLLM installed."
    else
        WARN "Skipped AnythingLLM."
    fi
}

# ================================================================
#  Shell config
# ================================================================
configure_shell() {
    STEP "Shell configuration"
    local rc="$HOME/.bashrc"
    [[ -f "$HOME/.zshrc" ]] && rc="$HOME/.zshrc"

    local lines=(
        '# AI Stack'
        '[ -f /opt/intel/oneapi/setvars.sh ] && source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true'
        'export ONEAPI_DEVICE_SELECTOR="level_zero:0"'
        'export SYCL_DEVICE_FILTER="level_zero:gpu"'
        'export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"'
    )
    for line in "${lines[@]}"; do
        grep -qF "$line" "$rc" 2>/dev/null || echo "$line" >> "$rc"
    done
    OK "Shell configured ($rc). Run: source $rc"
}

# ================================================================
#  Summary
# ================================================================
print_summary() {
    echo ""
    echo -e "${W}${G}╔══════════════════════════════════════════════════╗"
    echo -e "║  🎉  Installation Complete!  (Intel Arc A770)    ║"
    echo -e "╚══════════════════════════════════════════════════╝${N}"
    echo ""
    echo -e "${W}  GPU backend:${N}    SYCL (level_zero:0) — full A770 16 GB VRAM"
    echo -e "${W}  Model:${N}          Llama-3.1-8B Q4_K_M (~5 GB on VRAM)"
    echo -e "${W}  API:${N}            http://localhost:8080"
    echo ""
    echo -e "${W}  To start the stack:${N}"
    echo -e "  ${C}bash ~/ai_stack/start_ai_stack.sh${N}"
    echo ""
    echo -e "${W}  Or use the manager:${N}"
    echo -e "  ${C}bash ~/ai_stack_manager.sh${N}"
    echo ""
    WARN "Re-login (or reboot) before first use — required for Intel GPU group membership and oneAPI env."
}

# ================================================================
#  Write startup script (Arc A770 SYCL flags)
# ================================================================
write_startup_script() {
    STEP "Writing startup script"
    local script="$INSTALL_DIR/start_ai_stack.sh"
    cat > "$script" <<STARTUP
#!/bin/bash
# ── AI Stack Launcher — Intel Arc A770 / llama.cpp SYCL ──
source "\$HOME/.cargo/env" 2>/dev/null || true
[ -f /opt/intel/oneapi/setvars.sh ] && source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1

export ONEAPI_DEVICE_SELECTOR="level_zero:0"
export SYCL_DEVICE_FILTER="level_zero:gpu"
export PATH="\$HOME/.cargo/bin:\$HOME/.local/bin:\$PATH"

LLAMA_SERVER="$LLAMACPP_BIN"
MODEL="$MODEL_PATH"
MEMU="$MEMU_DIR/target/release/memu"
LOGS="$INSTALL_DIR/logs"
mkdir -p "\$LOGS"

echo "🤖 Starting AI Stack (Intel Arc A770 / llama.cpp SYCL)…"

# llama-server — SYCL backend, all layers on GPU
"\$LLAMA_SERVER" \\
    --model "\$MODEL" \\
    --ctx-size 8192 \\
    --n-gpu-layers 99 \\
    --port 8080 \\
    --host 0.0.0.0 \\
    > "\$LOGS/engine.log" 2>&1 &
ENGINE_PID=\$!
echo "  ⏳ Engine PID \$ENGINE_PID — waiting for API…"

for i in \$(seq 1 90); do
    sleep 1
    curl -sf http://localhost:8080/v1/models >/dev/null 2>&1 && break
done

curl -sf http://localhost:8080/v1/models >/dev/null 2>&1 \\
    && echo "  ✅ Engine ready." \\
    || { echo "  ❌ Engine failed — check \$LOGS/engine.log"; kill \$ENGINE_PID 2>/dev/null; exit 1; }

# MemU
"\$MEMU" --api-url http://localhost:8080 > "\$LOGS/memu.log" 2>&1 &
MEMU_PID=\$!
echo "  ✅ MemU PID \$MEMU_PID"

echo "\$ENGINE_PID \$MEMU_PID" > "$INSTALL_DIR/.pids"

# AnythingLLM
command -v anythingllm &>/dev/null && { anythingllm &>/dev/null & echo "  ✅ AnythingLLM launched."; }

echo ""
echo "🚀 Stack LIVE  —  API: http://localhost:8080"
echo "   Logs: \$LOGS/"
echo "   Stop: kill \$(cat $INSTALL_DIR/.pids)"
STARTUP
    chmod +x "$script"
    OK "Startup script → $script"
}

# ================================================================
#  MAIN
# ================================================================
main() {
    clear
    echo -e "${W}${C}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║   LOCAL AI STACK INSTALLER                   ║"
    echo "  ║   Ubuntu 24.04  ·  Intel Arc A770  (SYCL)    ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${N}"

    preflight
    install_system_deps
    install_intel_gpu_drivers
    install_rust
    install_llamacpp_sycl
    download_model
    install_memu
    install_anythingllm
    configure_shell
    write_startup_script
    print_summary
}

main "$@"
