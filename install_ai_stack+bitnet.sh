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
APPS_DIR="$HOME/Applications"

# ── Versions / URLs ──────────────────────────────────────────────
LLAMACPP_REPO="https://github.com/ggerganov/llama.cpp"
LLAMACPP_DIR="$INSTALL_DIR/llama.cpp"
LLAMACPP_BIN="$LLAMACPP_DIR/build/bin/llama-server"
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
    # Two separate driver stacks must both be present:
    #   OpenCL:    intel-opencl-icd  (used by clinfo, OpenCL apps)
    #   SYCL/L0:   libze-intel-gpu1  (used by llama.cpp SYCL backend)
    # These come from different repos and must NOT conflict. We check
    # each independently and only install what is genuinely missing.
    INFO "Checking Intel GPU driver packages…"

    # Ensure Intel GPU repo is present (needed for libze-intel-gpu1)
    if [[ ! -f /etc/apt/sources.list.d/intel-gpu.list ]]; then
        wget -qO - https://repositories.intel.com/gpu/intel-graphics.key \
            | sudo gpg --yes --dearmor \
                -o /usr/share/keyrings/intel-graphics.gpg
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/intel-graphics.gpg] \
https://repositories.intel.com/gpu/ubuntu noble unified" \
            | sudo tee /etc/apt/sources.list.d/intel-gpu.list
        sudo apt-get update -qq || true
    fi

    local PKGS=()

    # OpenCL ICD — from Ubuntu universe if not present
    if ! dpkg -l intel-opencl-icd 2>/dev/null | grep -q '^ii'; then
        PKGS+=("intel-opencl-icd")
    else
        INFO "  intel-opencl-icd     ✓ already installed"
    fi

    # level-zero GPU backend — CRITICAL for SYCL; from Intel GPU repo
    # libze-intel-gpu1 and intel-level-zero-gpu are alternatives; accept either
    if dpkg -l libze-intel-gpu1 2>/dev/null | grep -q '^ii' \
    || dpkg -l intel-level-zero-gpu 2>/dev/null | grep -q '^ii'; then
        INFO "  level-zero GPU shim  ✓ already installed"
    else
        PKGS+=("libze-intel-gpu1")
    fi

    # level-zero loader (ICD dispatcher) — from Ubuntu main
    if ! dpkg -l libze1 2>/dev/null | grep -q '^ii'; then
        PKGS+=("libze1")
    else
        INFO "  libze1               ✓ already installed"
    fi

    if [[ ${#PKGS[@]} -gt 0 ]]; then
        INFO "  Installing: ${PKGS[*]}"
        sudo apt-get install -y "${PKGS[@]}" || true
    fi

    sudo apt-get install -y --no-install-recommends clinfo libze-dev 2>/dev/null || true
    OK "Intel GPU driver packages ready."

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
    echo -e "  OpenCL (clinfo):"; clinfo -l 2>/dev/null | grep -i "intel\|Arc" || WARN "  No Intel GPU via OpenCL"
    echo -e "  level-zero backend:"
    if dpkg -l libze-intel-gpu1 2>/dev/null | grep -q '^ii'; then
        OK "  libze-intel-gpu1 installed — SYCL should see the GPU after re-login"
    else
        WARN "  libze-intel-gpu1 NOT installed — SYCL will not find the GPU!"
        WARN "  Run: sudo apt-get install libze-intel-gpu1"
    fi
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

        INFO "Configuring cmake with SYCL backend${USE_BITNET:+ and BitNet 1.58b support}…"    cmake -B "$LLAMACPP_DIR/build" \
        -S "$LLAMACPP_DIR" \
        -G Ninja \
        -DGGML_SYCL=ON \
        ${USE_BITNET:+-DGGML_USE_BITNET=ON} \
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
#  STEP 6 — Memory server (mem0 + ChromaDB + sentence-transformers)
# ================================================================
install_memory_server() {
    STEP "6/7  Memory server (mem0 · ChromaDB · sentence-transformers)"

    local MEM_DIR="$INSTALL_DIR/memory_server"
    local MEM_VENV="$MEM_DIR/.venv"
    local MEM_SCRIPT="$MEM_DIR/memory_server.py"
    local MEM_MARKER="$MEM_DIR/.installed"

    # Copy the server script from next to the installer
    local SCRIPT_DIR
    SCRIPT_DIR="$(dirname "$(realpath "$0")")"

    mkdir -p "$MEM_DIR"

    # Skip if already installed
    if [[ -f "$MEM_MARKER" && -f "$MEM_SCRIPT" ]]; then
        OK "Memory server already installed."
        return
    fi

    # Copy memory_server.py
    if [[ -f "$SCRIPT_DIR/memory_server.py" ]]; then
        cp "$SCRIPT_DIR/memory_server.py" "$MEM_SCRIPT"
        OK "Copied memory_server.py"
    else
        ERR "memory_server.py not found in $SCRIPT_DIR — ensure it's next to install_ai_stack.sh"
    fi

    # Python 3.10+ is fine — use system python3 (Ubuntu 24.04 ships 3.12)
    INFO "Creating Python venv for memory server…"
    python3 -m venv "$MEM_VENV"

    INFO "Installing Python dependencies…"
    "$MEM_VENV/bin/pip" install --upgrade pip 

    INFO "Step 1/3 — web framework (fast)…"
    "$MEM_VENV/bin/pip" install \
        "fastapi" \
        "uvicorn[standard]"

    INFO "Step 2/3 — mem0ai + ChromaDB (slow, ~200 MB)…"
    "$MEM_VENV/bin/pip" install \
        "mem0ai" \
        "chromadb"

    INFO "Step 3/3 — sentence-transformers (slow, ~300 MB)…"
    "$MEM_VENV/bin/pip" install \
        "sentence-transformers" \
        "huggingface-hub"

    # Write a wrapper launch script
    cat > "$MEM_DIR/start_memory_server.sh" <<MEMSTART
#!/bin/bash
# Memory server launcher — called by ai_stack_manager.sh
source "$MEM_VENV/bin/activate"
export LLAMA_BASE_URL="\${LLAMA_BASE_URL:-http://localhost:8080/v1}"
export LLAMA_API_KEY="\${LLAMA_API_KEY:-local}"
export LLAMA_MODEL="\${LLAMA_MODEL:-llama}"
exec python3 "$MEM_SCRIPT"
MEMSTART
    chmod +x "$MEM_DIR/start_memory_server.sh"

    touch "$MEM_MARKER"
    OK "Memory server installed → $MEM_DIR"
    INFO "First start will download the sentence-transformer model (~22 MB)."
}
install_memu() { install_memory_server; }   # alias so main() call still works

# ================================================================
#  STEP 7 — AnythingLLM + Search Proxy
# ================================================================
install_anythingllm() {
    STEP "7/7  AnythingLLM + Search Proxy"

    # ── AnythingLLM ───────────────────────────────────────────────
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

    # ── Search proxy ──────────────────────────────────────────────
    local PROXY_DIR="$INSTALL_DIR/search_proxy"
    local PROXY_VENV="$PROXY_DIR/.venv"
    local PROXY_SCRIPT="$PROXY_DIR/search_proxy.py"
    local PROXY_MARKER="$PROXY_DIR/.installed"
    local SCRIPT_DIR; SCRIPT_DIR="$(dirname "$(realpath "$0")")"

    mkdir -p "$PROXY_DIR"

    if [[ -f "$PROXY_MARKER" ]]; then
        OK "Search proxy already installed."
    else
        if [[ -f "$SCRIPT_DIR/search_proxy.py" ]]; then
            cp "$SCRIPT_DIR/search_proxy.py" "$PROXY_SCRIPT"
            OK "Copied search_proxy.py"
        else
            ERR "search_proxy.py not found in $SCRIPT_DIR"
        fi

        INFO "Creating search proxy venv…"
        python3 -m venv "$PROXY_VENV"
        INFO "Installing proxy dependencies (httpx, fastapi, uvicorn)…"
        "$PROXY_VENV/bin/pip" install --upgrade pip
        "$PROXY_VENV/bin/pip" install "httpx" "fastapi" "uvicorn[standard]"

        # Launch script
        cat > "$PROXY_DIR/start_search_proxy.sh" <<PROXYSTART
#!/bin/bash
export LLAMA_URL="\${LLAMA_URL:-http://localhost:8080}"
export LLAMA_API_KEY="\${LLAMA_API_KEY:-local}"
export SEARXNG_URL="\${SEARXNG_URL:-http://localhost:8081}"
export PROXY_PORT="\${PROXY_PORT:-8090}"
exec "$PROXY_VENV/bin/python" "$PROXY_SCRIPT"
PROXYSTART
        chmod +x "$PROXY_DIR/start_search_proxy.sh"
        touch "$PROXY_MARKER"
        OK "Search proxy installed — listens on :8090, forwards to llama-server :8080"
        INFO "Point AnythingLLM at http://localhost:8090 (not 8080) to enable web search."
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
    --api-key local \\
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

echo "\$ENGINE_PID" > "$INSTALL_DIR/.pids"

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