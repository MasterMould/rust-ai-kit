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
        curl wget git build-essential cmake pkg-config ninja-build \
        libssl-dev ca-certificates unzip file libfuse2 \
        libwebkit2gtk-4.1-dev libgtk-3-dev \
        gpg-agent software-properties-common \
        libopenblas-dev \
        libcurl4-openssl-dev \
        libsqlite3-dev \
        ocl-icd-libopencl1
    OK "System packages installed."
}

# ================================================================
#  STEP 2 — Intel GPU drivers + level-zero (Arc A770)
# ================================================================
install_intel_gpu_drivers() {
    STEP "2/7  Intel Arc A770 GPU drivers"

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

    INFO "Checking Intel oneAPI compiler…"

    local ICX_BIN=""
    ICX_BIN=$(command -v icx 2>/dev/null) \
        || ICX_BIN=$(find /opt/intel/oneapi -name icx -type f 2>/dev/null | head -1) \
        || true

    if [[ -n "$ICX_BIN" ]]; then
        OK "Intel icx compiler found: $ICX_BIN"
    else
        INFO "Installing Intel oneAPI compiler…"
        if [[ ! -f /etc/apt/sources.list.d/oneAPI.list ]]; then
            wget -qO - https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
                | sudo gpg --yes --dearmor \
                    -o /usr/share/keyrings/oneapi-archive-keyring.gpg
            echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
                | sudo tee /etc/apt/sources.list.d/oneAPI.list
            sudo apt-get update -qq || true
        fi

        sudo apt-get install -y intel-oneapi-compiler-dpcpp-cpp 

        ICX_BIN=$(command -v icx 2>/dev/null) \
            || ICX_BIN=$(find /opt/intel/oneapi -name icx -type f 2>/dev/null | head -1) \
            || true

        [[ -n "$ICX_BIN" ]] && OK "icx installed: $ICX_BIN" \
            || ERR "icx still not found after install."
    fi

    sudo usermod -aG render,video "$USER" 2>/dev/null || true
    OK "User added to render/video groups (re-login to take effect)."

    INFO "GPU visibility check:"
    clinfo -l 2>/dev/null | grep -i "intel\|Arc" \
        || WARN "clinfo shows no Intel GPU — reboot may be required."

    INFO "SYCL device detection:"
    command -v sycl-ls >/dev/null && sycl-ls || WARN "sycl-ls not found"
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
#  STEP 4 — llama.cpp built with SYCL
# ================================================================
install_llamacpp_sycl() {

STEP "4/7  Building llama.cpp (Intel Arc SYCL)"
if [[ -d "$LLAMACPP_DIR" ]]; then
INFO="Updating llama.cpp"
echo "$INFO"
git -C "$LLAMACPP_DIR" pull
else
git clone https://github.com/ggerganov/llama.cpp "$LLAMACPP_DIR"
fi

cd "$LLAMACPP_DIR"
rm -rf build

echo "Loading Intel oneAPI environment"

# save shell state
OLD_OPTS=$(set +o)

# disable strict mode temporarily
set +u
set +e

#install oneapi-goodies
sudo apt install -y \
intel-oneapi-mkl \
intel-oneapi-mkl-devel \
intel-oneapi-dnnl \
intel-oneapi-dnnl-devel

# guard variable expected by Intel scripts
export OCL_ICD_FILENAMES=${OCL_ICD_FILENAMES:-}

# load oneAPI environment
source /opt/intel/oneapi/setvars.sh --force

# restore strict mode
eval "$OLD_OPTS"

OK "Intel environment loaded"

echo "Checking SYCL devices"

if command -v sycl-ls >/dev/null; then
sycl-ls | grep -i arc || WARN "Arc not visible to SYCL"
fi

ICX=$(command -v icx)
ICPX=$(command -v icpx)

[[ -z "$ICX" ]] && ERR "icx compiler not found"
[[ -z "$ICPX" ]] && ERR "icpx compiler not found"

OK "Compilers detected"

cmake -B build \
-S . \
-G Ninja \
-DCMAKE_C_COMPILER="$ICX" \
-DCMAKE_CXX_COMPILER="$ICPX" \
-DGGML_SYCL=ON \
-DGGML_SYCL_F16=ON \
-DGGML_OPENMP=ON \
-DGGML_BLAS=ON \
-DGGML_BLAS_VENDOR=OpenBLAS \
-DCMAKE_BUILD_TYPE=Release

cmake --build build -j$(nproc)

[[ -f "$LLAMACPP_BIN" ]] || ERR "llama-server build failed"

OK "llama.cpp built successfully"


}
# ================================================================
#  STEP 5 — Model
# ================================================================
download_model() {
    STEP "5/7  Download LLM model"
    mkdir -p "$MODEL_DIR"

    if [[ -f "$MODEL_PATH" ]]; then
        OK "Model already present."
    else
        INFO "Downloading model (~5GB)..."
        wget -c --show-progress -O "$MODEL_PATH" "$MODEL_URL"
        OK "Model downloaded."
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
        wget -c --show-progress -O "$ai" "$ANYTHINGLLM_APPIMAGE_URL"
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

    OK "Shell configured."
}

# ================================================================
#  Startup script
# ================================================================
write_startup_script() {
    STEP "Writing startup script"

    local script="$INSTALL_DIR/start_ai_stack.sh"

cat > "$script" <<STARTUP
#!/bin/bash
source "\$HOME/.cargo/env" 2>/dev/null || true
[ -f /opt/intel/oneapi/setvars.sh ] && source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1

export ONEAPI_DEVICE_SELECTOR="level_zero:0"
export SYCL_DEVICE_FILTER="level_zero:gpu"

LLAMA_SERVER="$LLAMACPP_BIN"
MODEL="$MODEL_PATH"
MEMU="$MEMU_DIR/target/release/memu"
LOGS="$INSTALL_DIR/logs"

mkdir -p "\$LOGS"

echo "🤖 Starting AI Stack..."

"\$LLAMA_SERVER" \
    --model "\$MODEL" \
    --ctx-size 4096 \
    --batch-size 1024 \
    --threads \$(nproc) \
    --n-gpu-layers -1 \
    --port 8080 \
    --host 0.0.0.0 \
    > "\$LOGS/engine.log" 2>&1 &

ENGINE_PID=\$!

for i in \$(seq 1 90); do
    sleep 1
    curl -sf http://localhost:8080/v1/models >/dev/null 2>&1 && break
done

"\$MEMU" --api-url http://localhost:8080 > "\$LOGS/memu.log" 2>&1 &
MEMU_PID=\$!

echo "\$ENGINE_PID \$MEMU_PID" > "$INSTALL_DIR/.pids"

command -v anythingllm &>/dev/null && anythingllm &>/dev/null &

echo "🚀 AI Stack running → http://localhost:8080"
STARTUP

chmod +x "$script"
}

# ================================================================
#  Summary
# ================================================================
print_summary() {

echo ""
echo "🎉 Installation Complete!"
echo ""
echo "Model: Llama-3.1-8B Q4_K_M"
echo "API: http://localhost:8080"
echo ""
echo "Start stack:"
echo "bash ~/ai_stack/start_ai_stack.sh"
echo ""
echo "Re-login or reboot before first run."
}

# ================================================================
#  MAIN
# ================================================================
main() {

clear

echo ""
echo "LOCAL AI STACK INSTALLER"
echo "Ubuntu 24.04  ·  Intel Arc A770"
echo ""

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
