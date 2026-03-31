#!/bin/bash
# ================================================================
#  🤖  RUST-AI STACK MANAGER  —  Ubuntu 24.04
#  GPU: Intel Arc A770 (SYCL/oneAPI backend)
#  Components: llama.cpp/SYCL · MemU · AnythingLLM · SearXNG
# ================================================================
# NOTE: No set -euo pipefail here — this is an interactive menu script.
# Strict mode causes silent exits on any non-zero command (e.g. a grep
# that finds no match, or setvars.sh returning non-zero). Functions that
# need strict error handling manage their own error checking explicitly.

# ── Directories ──────────────────────────────────────────────────
INSTALL_DIR="$HOME/ai_stack"
MODEL_DIR="$INSTALL_DIR/models"
MEM_DIR="$INSTALL_DIR/memory_server"
PROXY_DIR="$INSTALL_DIR/search_proxy"
MODEL_CONFIG="$INSTALL_DIR/.active_model"   # persists chosen model across sessions
LLAMACPP_BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
LOG_DIR="$INSTALL_DIR/logs"
PID_FILE="$INSTALL_DIR/.pids"
APPS_DIR="$HOME/Applications"
SYSTEMD_DIR="$HOME/.config/systemd/user"

# ── Read active model from config (falls back to first .gguf found) ─
_load_active_model() {
    if [[ -f "$MODEL_CONFIG" ]]; then
        MODEL_PATH=$(cat "$MODEL_CONFIG")
    else
        # Auto-detect first available model
        MODEL_PATH=$(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" 2>/dev/null | sort | head -1)
        [[ -n "$MODEL_PATH" ]] && echo "$MODEL_PATH" > "$MODEL_CONFIG" || MODEL_PATH=""
    fi
    # Validate the stored path still exists
    if [[ -n "$MODEL_PATH" && ! -f "$MODEL_PATH" ]]; then
        MODEL_PATH=$(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" 2>/dev/null | sort | head -1)
        [[ -n "$MODEL_PATH" ]] && echo "$MODEL_PATH" > "$MODEL_CONFIG" || { MODEL_PATH=""; rm -f "$MODEL_CONFIG"; }
    fi
}
mkdir -p "$MODEL_DIR"
_load_active_model

# ── Network ───────────────────────────────────────────────────────
ENGINE_PORT=8080
SEARXNG_PORT=8081

# ── Intel Arc A770 SYCL env ───────────────────────────────────────
_source_envs() {
    [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env" 2>/dev/null || true
    if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
        source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true
    fi
    export ONEAPI_DEVICE_SELECTOR="level_zero:0"
    export SYCL_DEVICE_FILTER="level_zero:gpu"
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
}
_source_envs || true

# ── Colours ───────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m'
B='\033[0;34m' C='\033[0;36m' W='\033[1m' N='\033[0m'

OK()    { echo -e "${G}  ✅  $*${N}"; }
INFO()  { echo -e "${C}  ℹ️   $*${N}"; }
WARN()  { echo -e "${Y}  ⚠️   $*${N}"; }
ERR()   { echo -e "${R}  ❌  $*${N}"; }
STEP()  { echo -e "\n${W}${C}── $* ──${N}"; }
PAUSE() { read -rp "$(echo -e "${Y}  Press Enter to return to menu…${N}")"; }
ask()   {
    local yn="[Y/n]"; [[ "${2:-y}" == "n" ]] && yn="[y/N]"
    read -rp "$(echo -e "${Y}  ❓  $1 $yn: ${N}")" r
    r="${r:-${2:-y}}"; [[ "${r,,}" == "y" ]]
}

# ── Quick GPU status ──────────────────────────────────────────────
_gpu_status() {
    # intel_gpu_top or xpu-smi if available; fall back to clinfo
    if command -v xpu-smi &>/dev/null; then
        xpu-smi discovery 2>/dev/null | grep -i "arc\|A770" | head -1 || true
    elif command -v clinfo &>/dev/null; then
        clinfo -l 2>/dev/null | grep -i "Intel" | head -1 || true
    fi
}

_svc_running() {
    systemctl --user is-active "${1}.service" &>/dev/null
}

# ================================================================
#  MENU
# ================================================================
show_menu() {
    clear
    echo -e "${B}${W}"
    echo "  ╔══════════════════════════════════════════════╗"
    echo "  ║   🤖  RUST-AI STACK MANAGER                  ║"
    echo "  ║       Ubuntu 24.04  ·  Intel Arc A770        ║"
    echo "  ╚══════════════════════════════════════════════╝"
    echo -e "${N}"
    _print_quick_status
    echo -e "${W}  Core${N}"
    echo "  1)  Full Automated Install (Arc A770 / SYCL)"
    echo "  2)  Start AI Stack"
    echo "  3)  Stop AI Stack"
    echo "  4)  Restart AI Stack"
    echo "  5)  Check Status + GPU Info"
    echo ""
    echo -e "${W}  Autostart${N}"
    echo "  6)  Enable Auto-Start on Boot (systemd)"
    echo "  7)  Disable Auto-Start"
    echo ""
    echo -e "${W}  Setup & Tools${N}"
    echo "  8)  AnythingLLM Connection Guide"
    echo "  9)  Setup Web Search (SearXNG)"
    echo "  10) View Logs"
    echo "  11) Validate Stack (memory · search · engine)"
    echo "  12) Benchmark GPU (quick inference test)"
    echo "  13) Uninstall / Clean Up"
    echo ""
    echo -e "${W}  Models${N}"
    echo "  14) Model Manager  (download · switch · delete)"
    echo "  15) LLM-Factory "
    echo ""
    echo "  0)  Exit"
    echo -e "${B}  ──────────────────────────────────────────────${N}"
    echo -n "  Select: "
}

_print_quick_status() {
    local engine_s mem_s proxy_s searxng_s gpu_s

    if pgrep -f "llama-server" &>/dev/null || _svc_running "llamaedge"; then
        engine_s="${G}● running${N}"
    else
        engine_s="${R}○ stopped${N}"
    fi

    pgrep -f "memory_server.py" &>/dev/null \
        && mem_s="${G}● running${N}" || mem_s="${R}○ stopped${N}"

    pgrep -f "search_proxy.py" &>/dev/null \
        && proxy_s="${G}● running${N}" || proxy_s="${R}○ stopped${N}"

    if docker ps --filter name=searxng --filter status=running -q 2>/dev/null | grep -q .; then
        searxng_s="${G}● running${N}"
    else
        searxng_s="${R}○ stopped${N}"
    fi

    if clinfo -l 2>/dev/null | grep -qi "intel"; then
        gpu_s="${G}● A770 visible${N}"
    else
        gpu_s="${Y}⚠ GPU not detected${N}"
    fi

    echo -e "  Engine: $engine_s  Memory: $mem_s  GPU: $gpu_s"
    echo -e "  Proxy:  $proxy_s   Search: $searxng_s"
    if [[ -n "${MODEL_PATH:-}" ]]; then
        echo -e "  Model:  ${W}$(basename "$MODEL_PATH")${N}"
    else
        echo -e "  Model:  ${R}none — use option 13${N}"
    fi
    echo ""
}

# ================================================================
#  1. INSTALL  (delegates to install script)
# ================================================================
install_stack() {
    local installer
    installer="$(dirname "$(realpath "$0")")/install_ai_stack.sh"
    if [[ -f "$installer" ]]; then
        bash "$installer"
    else
        WARN "install_ai_stack.sh not found next to this script."
        WARN "Download it from the same location as this file."
    fi
    PAUSE
}

# ================================================================
#  2. START
# ================================================================
start_stack() {
    _source_envs
    mkdir -p "$LOG_DIR"

    # Hard requirements — engine and model must exist
    [[ -f "$LLAMACPP_BIN" ]] \
        || { ERR "llama-server not found. Run Install (option 1) first."; PAUSE; return; }
    [[ -f "$MODEL_PATH" ]] \
        || { ERR "Model not found. Run Install first."; PAUSE; return; }

    # Write PID file
    echo "$engine_pid" > "$PID_FILE"

    # ── Memory server ─────────────────────────────────────────────
    STEP "Memory server (mem0 + ChromaDB)"
    local MEM_LAUNCH="$MEM_DIR/start_memory_server.sh"
    if [[ -f "$MEM_LAUNCH" ]]; then
        LLAMA_API_KEY=local \
        LLAMA_BASE_URL="http://localhost:$ENGINE_PORT/v1" \
        LLAMA_MODEL=llama \
        bash "$MEM_LAUNCH" >> "$LOG_DIR/memory.log" 2>&1 &
        local mem_pid=$!
        sleep 3
        if kill -0 "$mem_pid" 2>/dev/null; then
            OK "Memory server started (PID $mem_pid) → http://localhost:8000"
            echo "$engine_pid $mem_pid" > "$PID_FILE"
        else
            WARN "Memory server exited — check: tail $LOG_DIR/memory.log"
        fi
    else
        INFO "Memory server not installed — run Install (option 1) to set it up."
    fi

    if lsof -i ":$ENGINE_PORT" -sTCP:LISTEN -t &>/dev/null; then
        WARN "Port $ENGINE_PORT already in use — stack may already be running."
        ask "Start anyway?" n || { PAUSE; return; }
    fi

    STEP "llama-server (llama.cpp SYCL → Arc A770)"

    # ── GPU preflight ─────────────────────────────────────────────
    # Check level-zero can see the GPU before we even try to launch.
    # Most common cause of "No device of requested type" is the user
    # not being in the render group yet (requires re-login after install).
    local ze_ok=false
    if command -v clinfo &>/dev/null; then
        clinfo -l 2>/dev/null | grep -qi "intel" && ze_ok=true || true
    fi
    # Also try ze_info / zeinfo if available
    command -v sycl-ls &>/dev/null && sycl-ls 2>/dev/null | grep -qi "gpu" && ze_ok=true || true

    if ! $ze_ok; then
        WARN "Intel GPU not visible to level-zero/OpenCL."
        WARN "Most likely cause: you haven't re-logged in since install."
        WARN "Your user needs to be in the 'render' group — check with: groups"
        WARN "Fix: log out and back in (or reboot), then try again."
        WARN ""
        WARN "Falling back to CPU mode (slow but functional)."
        ask "Continue with CPU fallback?" n || { PAUSE; return; }
        local GPU_LAYERS=0
    else
        OK "Intel Arc A770 visible — using GPU."
        local GPU_LAYERS=99
    fi

    INFO "Model:    $(basename "$MODEL_PATH")"
    INFO "Context:  8192 tokens"
    INFO "GPU layers: $GPU_LAYERS"

    # ── Launch engine (array form avoids continuation-line shell bugs) ─
    mkdir -p "$LOG_DIR"
    local -a ENGINE_CMD=(
        "$LLAMACPP_BIN"
        --model         "$MODEL_PATH"
        --ctx-size      8192
        --n-gpu-layers  "$GPU_LAYERS"
        --port          "$ENGINE_PORT"
        --host          0.0.0.0
        --api-key       local
    )

    ONEAPI_DEVICE_SELECTOR="level_zero:0" \
    SYCL_DEVICE_FILTER="level_zero:gpu" \
    "${ENGINE_CMD[@]}" >> "$LOG_DIR/engine.log" 2>&1 &
    local engine_pid=$!
    INFO "Engine PID $engine_pid — waiting for API (up to 90s)…"

    local ready=false
    for i in $(seq 1 90); do
        sleep 1
        printf "\r  ${C}  Waiting… %2ds${N}" "$i"
        if curl -sf "http://localhost:$ENGINE_PORT/v1/models" &>/dev/null; then
            ready=true; echo ""; break
        fi
    done

    if ! $ready; then
        echo ""
        ERR "Engine did not respond after 90s."
        INFO "Check log: tail -f $LOG_DIR/engine.log"
        INFO "Common cause: SYCL libs not loaded. Verify with:"
        INFO "  clinfo -l           (should show Intel Arc)"
        INFO "  $LLAMACPP_BIN --version"
        kill "$engine_pid" 2>/dev/null || true
        PAUSE; return
    fi

    OK "Engine API is live."

    # ── Search proxy ──────────────────────────────────────────────
    STEP "Search proxy (SearXNG → llama-server bridge)"
    local PROXY_LAUNCH="$PROXY_DIR/start_search_proxy.sh"
    if [[ -f "$PROXY_LAUNCH" ]]; then
        bash "$PROXY_LAUNCH" >> "$LOG_DIR/proxy.log" 2>&1 &
        local proxy_pid=$!
        sleep 2
        if kill -0 "$proxy_pid" 2>/dev/null; then
            OK "Search proxy started (PID $proxy_pid) → http://localhost:8090"
            INFO "Point AnythingLLM at :8090 (not :8080) to enable web search"
        else
            WARN "Search proxy exited — check: tail $LOG_DIR/proxy.log"
        fi
    else
        INFO "Search proxy not installed — run Install (option 1) to set it up."
    fi
    if command -v anythingllm &>/dev/null; then
        anythingllm &>/dev/null &
        OK "AnythingLLM launched."
    else
        WARN "AnythingLLM not found — launch $APPS_DIR/AnythingLLM.AppImage manually."
    fi

    echo ""
    OK "Stack is LIVE → http://localhost:$ENGINE_PORT"
    echo -e "  ${W}Logs:${N} $LOG_DIR/"
    PAUSE
}

# ================================================================
#  3. STOP
# ================================================================
# Internal silent stop — no PAUSE, used by restart and systemd setup
_stop_stack_silent() {
    local stopped=0
    if systemctl --user is-active llamaedge.service &>/dev/null; then
        systemctl --user stop llamaedge.service 2>/dev/null || true
        OK "Systemd service stopped."; stopped=1
    fi
    if [[ -f "$PID_FILE" ]]; then
        read -r pids < "$PID_FILE" 2>/dev/null || pids=""
        for pid in $pids; do
            kill -0 "$pid" 2>/dev/null && kill "$pid" && OK "Killed PID $pid" || true
        done
        rm -f "$PID_FILE"
        stopped=1
    fi
    pkill -f "search_proxy.py"  2>/dev/null && { OK "Killed search proxy.";  stopped=1; } || true
    pkill -f "memory_server.py" 2>/dev/null && { OK "Killed memory server."; stopped=1; } || true
    pkill -f "llama-server"     2>/dev/null && { OK "Killed llama-server.";  stopped=1; } || true
    [[ $stopped -eq 0 ]] && WARN "No running processes found." || OK "Stack stopped."
}

stop_stack() {
    STEP "Stopping AI Stack"
    _stop_stack_silent
    PAUSE
}

# ================================================================
#  4. RESTART
# ================================================================
restart_stack() {
    clear
    INFO "Restarting AI Stack…"
    INFO "Active model: $(basename "${MODEL_PATH:-none}")"
    _stop_stack_silent
    sleep 1
    start_stack
}

# ================================================================
#  5. STATUS + GPU INFO
# ================================================================
check_status() {
    clear
    echo -e "${W}${C}  STATUS — Intel Arc A770${N}\n"

    # Engine
    if systemctl --user is-active llamaedge.service &>/dev/null; then
        echo -e "  ${G}● engine${N}  (systemd active)"
    elif pgrep -f "llama-server" &>/dev/null; then
        echo -e "  ${G}● engine${N}  (running · PID $(pgrep -f 'llama-server' | head -1))"
    else
        echo -e "  ${R}○ engine${N}  (not running)"
    fi

    # Search proxy
    if pgrep -f "search_proxy.py" &>/dev/null; then
        echo -e "  ${G}● proxy${N}   (running · PID $(pgrep -f 'search_proxy.py' | head -1) · :8090)"
        curl -sf http://localhost:8090/health 2>/dev/null | python3 -m json.tool 2>/dev/null || true
    else
        echo -e "  ${R}○ proxy${N}   (not running — web search unavailable)"
    fi

    # Memory server
    if pgrep -f "memory_server.py" &>/dev/null; then
        echo -e "  ${G}● memory${N}  (running · PID $(pgrep -f 'memory_server.py' | head -1))"
        local mem_health
        mem_health=$(curl -sf http://localhost:8000/health 2>/dev/null) \
            && echo -e "  ${G}  API responding${N}: $mem_health" \
            || WARN "  Memory API not responding yet"
    else
        echo -e "  ${R}○ memory${N}  (not running)"
    fi
    echo ""
    INFO "API health (http://localhost:$ENGINE_PORT/v1/models):"
    if curl -sf "http://localhost:$ENGINE_PORT/v1/models" | python3 -m json.tool 2>/dev/null; then
        OK "API responding."
    else
        WARN "API not responding on port $ENGINE_PORT."
    fi

    # GPU
    echo ""
    INFO "Intel Arc A770 — GPU compute visibility:"
    clinfo -l 2>/dev/null || WARN "clinfo not found or no GPU detected."

    if command -v xpu-smi &>/dev/null; then
        echo ""
        INFO "Intel XPU-SMI (live GPU utilisation):"
        xpu-smi stats 2>/dev/null || true
    elif [[ -f /sys/class/drm/card*/device/tile0/gt0/freq0/cur_freq_mhz ]]; then
        local freq; freq=$(cat /sys/class/drm/card*/device/tile0/gt0/freq0/cur_freq_mhz 2>/dev/null | head -1)
        INFO "Arc A770 current core freq: ${freq} MHz"
    fi

    # SearXNG
    echo ""
    if docker ps --filter name=searxng --filter status=running -q 2>/dev/null | grep -q .; then
        OK "SearXNG running at http://localhost:$SEARXNG_PORT"
    else
        WARN "SearXNG not running."
    fi

    # Disk
    echo ""
    INFO "Stack disk usage: $(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1)"
    PAUSE
}

# ================================================================
#  5. SYSTEMD — ARC A770 AWARE
# ================================================================
setup_systemd() {
    STEP "Systemd user services (Arc A770 / SYCL)"
    _source_envs

    [[ -f "$LLAMACPP_BIN" ]] \
        || { ERR "llama-server not found. Run Install first."; PAUSE; return; }
    [[ -n "$MODEL_PATH" ]] \
        || { ERR "No active model set. Use option 12 (Model Manager) first."; PAUSE; return; }

    mkdir -p "$SYSTEMD_DIR" "$LOG_DIR"

    # The systemd unit reads the active model from MODEL_CONFIG at each start,
    # so switching models via option 12 automatically applies on next restart.
    cat > "$SYSTEMD_DIR/llamaedge.service" <<EOF
[Unit]
Description=llama-server (llama.cpp SYCL — Intel Arc A770)
After=network.target

[Service]
Environment="ONEAPI_DEVICE_SELECTOR=level_zero:0"
Environment="SYCL_DEVICE_FILTER=level_zero:gpu"
Environment="PATH=/opt/intel/oneapi/compiler/latest/bin:/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/bin/bash -c 'source /opt/intel/oneapi/setvars.sh --force 2>/dev/null || true'
ExecStart=/bin/bash -c '$LLAMACPP_BIN \
    --model \$(cat $MODEL_CONFIG) \
    --ctx-size 8192 \
    --n-gpu-layers 99 \
    --port $ENGINE_PORT \
    --host 0.0.0.0 \
    --api-key local'
Restart=on-failure
RestartSec=10
StandardOutput=append:$LOG_DIR/engine.log
StandardError=append:$LOG_DIR/engine.log

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable llamaedge.service
    loginctl enable-linger "$USER"

    OK "Auto-start enabled. Engine starts at login/boot."
    INFO "Start now? → systemctl --user start llamaedge.service"
    PAUSE
}

disable_systemd() {
    STEP "Disabling auto-start"
    systemctl --user disable --now llamaedge.service 2>/dev/null \
        && OK "Auto-start disabled." || WARN "Service was not enabled."
    PAUSE
}

# ================================================================
#  7. SEARXNG
# ================================================================
setup_web_search() {
    STEP "SearXNG private web search"
    local DOCKER="docker"
    local SEARXNG_CONFIG_DIR="$HOME/searxng-config"

    if ! command -v docker &>/dev/null; then
        INFO "Installing Docker…"
        sudo apt-get update -qq
        sudo apt-get install -y docker.io docker-compose-v2
        sudo systemctl enable --now docker
        sudo usermod -aG docker "$USER"
        WARN "Added to docker group — re-login required. Using sudo for now."
        DOCKER="sudo docker"
    fi
    command -v docker &>/dev/null && ! docker info &>/dev/null 2>&1 && DOCKER="sudo docker"

    # Write settings.yml with JSON format enabled (required for API use).
    # Without this SearXNG returns 403 on all format=json requests.
    mkdir -p "$SEARXNG_CONFIG_DIR"
    cat > "$SEARXNG_CONFIG_DIR/settings.yml" <<'SEARXNG_SETTINGS'
use_default_settings: true
search:
  formats:
    - html
    - json
server:
  limiter: false
SEARXNG_SETTINGS
    INFO "SearXNG config written with JSON API enabled."

    $DOCKER rm -f searxng 2>/dev/null || true

    $DOCKER run -d \
        --name searxng \
        --restart unless-stopped \
        -p "${SEARXNG_PORT}:8080" \
        -v "$SEARXNG_CONFIG_DIR/settings.yml:/etc/searxng/settings.yml:ro" \
        -e "SEARXNG_BASE_URL=http://localhost:${SEARXNG_PORT}/" \
        searxng/searxng:latest

    INFO "Waiting for SearXNG to be ready…"
    local up=false
    for i in $(seq 1 30); do
        sleep 1
        curl -sf "http://localhost:$SEARXNG_PORT" &>/dev/null && { up=true; break; }
    done
    if $up; then
        OK "SearXNG live → http://localhost:$SEARXNG_PORT"
        # Verify JSON works
        if curl -sf "http://localhost:$SEARXNG_PORT/search?q=test&format=json" &>/dev/null; then
            OK "JSON API working — search proxy can now query SearXNG"
        else
            WARN "JSON API not yet responding — wait 10s then re-run this option"
        fi
    else
        WARN "SearXNG still starting — check: $DOCKER logs searxng"
    fi

    echo ""
    echo -e "${W}  Connect to AnythingLLM:${N}"
    echo "  Workspace → Agent Config → Search Provider → SearXNG"
    echo "  Base URL → http://localhost:$SEARXNG_PORT"
    PAUSE
}

# ================================================================
#  8. LOGS
# ================================================================
view_logs() {
    clear
    local DC; DC=$(docker info &>/dev/null 2>&1 && echo "docker" || echo "sudo docker")
    echo -e "${W}  Log viewer${N}"
    echo "  1) Engine (llama-server)"
    echo "  2) Memory server (mem0)"
    echo "  3) Search proxy"
    echo "  4) SearXNG"
    echo "  0) Back"
    echo -n "  Select: "
    read -r log_opt
    case "$log_opt" in
        1) tail -n 50 "$LOG_DIR/engine.log"  2>/dev/null || WARN "No engine log yet."  ;;
        2) tail -n 50 "$LOG_DIR/memory.log"  2>/dev/null || WARN "No memory log yet."  ;;
        3) tail -n 50 "$LOG_DIR/proxy.log"   2>/dev/null || WARN "No proxy log yet."   ;;
        4) $DC logs --tail 50 searxng        2>/dev/null || WARN "SearXNG not running." ;;
        0) return ;;
    esac
    PAUSE
}

# ================================================================
#  9. BENCHMARK (Arc A770)
# ================================================================
benchmark() {
    STEP "GPU Inference Benchmark"
    _source_envs

    command -v "$LLAMACPP_BIN" &>/dev/null || [[ -f "$LLAMACPP_BIN" ]] \
        || { ERR "llama-server not found."; PAUSE; return; }
    [[ -f "$LLAMACPP_BIN" && -f "$MODEL_PATH" ]] || { ERR "Stack not installed."; PAUSE; return; }

    INFO "Running a single 200-token completion — measuring tokens/sec…"
    local start end elapsed
    start=$(date +%s%N)

    local result
    result=$(curl -sf -X POST "http://localhost:$ENGINE_PORT/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{"model":"llama","prompt":"The Intel Arc A770 GPU is","max_tokens":200}' \
        2>/dev/null) || { WARN "API not running — start the stack first."; PAUSE; return; }

    end=$(date +%s%N)
    elapsed=$(( (end - start) / 1000000 ))  # ms
    local tokens; tokens=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['usage']['completion_tokens'])" 2>/dev/null || echo "?")
    local tps; tps=$(echo "$tokens $elapsed" | awk '{printf "%.1f", $1 / ($2/1000)}')

    echo ""
    OK "Benchmark complete"
    echo -e "  Tokens generated: ${W}$tokens${N}"
    echo -e "  Time elapsed:     ${W}${elapsed}ms${N}"
    echo -e "  Throughput:       ${W}${tps} tok/s${N}"
    echo ""
    INFO "Expected on Arc A770 (SYCL): ~25-45 tok/s for 8B Q4_K_M"
    [[ "$tps" == "?" ]] || \
        awk -v t="$tps" 'BEGIN { if (t < 10) print "  ⚠️  Low throughput — SYCL plugin may not be loaded" }' || true
    PAUSE
}

# ================================================================
#  10. UNINSTALL
# ================================================================
uninstall() {
    WARN "This removes all AI stack files, systemd services, the model, and SearXNG."
    ask "Are you SURE?" n || { PAUSE; return; }

    stop_stack 2>/dev/null || true
    systemctl --user disable --now llamaedge.service 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/llamaedge.service"
    systemctl --user daemon-reload 2>/dev/null || true
    docker rm -f searxng 2>/dev/null || true
    rm -rf "$INSTALL_DIR" "$APPS_DIR/AnythingLLM.AppImage" \
           "$HOME/.local/bin/anythingllm" \
           "$HOME/.local/share/applications/anythingllm.desktop"

    OK "Uninstall complete."
    INFO "Rust left in place     → remove with: rustup self uninstall"
    INFO "Intel oneAPI left in place → remove with: sudo apt remove intel-oneapi-runtime-dpcpp-cpp"
    PAUSE
}

# ================================================================
#  ANYTHINGLLM SETUP GUIDE
# ================================================================
setup_anythingllm() {
    clear
    echo -e "${W}${C}  AnythingLLM → llama-server Connection Guide${N}"
    echo ""
    echo -e "  AnythingLLM uses the ${W}Generic OpenAI${N} provider to talk to"
    echo -e "  our local llama-server. Set it up once in the UI:"
    echo ""
    echo -e "${W}  ── LLM Provider ──────────────────────────────────${N}"
    echo "  1. Open AnythingLLM"
    echo "  2. Click the ⚙️  wrench icon (bottom-left)"
    echo "  3. AI Providers → LLM"
    echo "  4. Provider:    Generic OpenAI"
    echo -e "  5. Base URL:    ${C}http://localhost:8090/v1${N}  ← the search proxy (not 8080)"
    echo "  6. API Key:     local"
    echo -e "  7. Model Name:  ${C}llama${N}"
    echo "  8. Token Limit: 8192"
    echo "  9. Save Changes"
    echo ""
    echo -e "  ${Y}  ℹ️  Port 8090 = search proxy (adds web results automatically)${N}"
    echo -e "  ${Y}     Port 8080 = llama-server direct (no web search)${N}"
    echo ""
    echo -e "${W}  ── Embedding Provider ────────────────────────────${N}"
    echo "  For RAG / document search, llama-server can serve embeddings"
    echo "  if you load a second embedding model. Simplest option:"
    echo ""
    echo "  AI Providers → Embedding"
    echo "  Provider:    Generic OpenAI"
    echo -e "  Base URL:    ${C}http://localhost:8080/v1${N}"
    echo "  API Key:     local"
    echo "  Model:       llama   (or load a dedicated embed model)"
    echo ""
    echo -e "${W}  ── Memory API (mem0 + ChromaDB) ──────────────────${N}"
    echo "  The memory server runs on http://localhost:8000"
    echo ""
    echo -e "  ${C}# Store a conversation:${N}"
    echo '  curl -X POST http://localhost:8000/memorize \'
    echo '    -H "Content-Type: application/json" \'
    echo '    -d '"'"'{"messages":[{"role":"user","content":"I prefer dark mode"},{"role":"assistant","content":"Got it!"}],"user_id":"me"}'"'"
    echo ""
    echo -e "  ${C}# Search memories:${N}"
    echo '  curl -X POST http://localhost:8000/retrieve \'
    echo '    -H "Content-Type: application/json" \'
    echo '    -d '"'"'{"query":"display preferences","user_id":"me"}'"'"
    echo ""
    echo -e "  ${C}# List all memories:${N}"
    echo "  curl http://localhost:8000/memories?user_id=me"
    echo ""
    echo -e "  ${C}# API docs (full Swagger UI):${N}"
    echo "  http://localhost:8000/docs"
    echo ""
    echo -e "${W}  ── Quick Test ─────────────────────────────────────${N}"
    echo "  Once configured, test with:"
    echo -e "  ${C}curl http://localhost:8080/v1/models${N}   ← should list 'llama'"
    echo -e "  ${C}curl http://localhost:8000/health${N}       ← MemU health check"
    echo ""
    PAUSE
}

# ================================================================
#  MODEL MANAGER
# ================================================================

# Curated model catalogue — all verified to fit on Arc A770 16 GB
# Format: "display_name|filename|url|vram_gb|description"
_model_catalogue() {
    cat <<'CATALOGUE'
Llama 3.1 8B Instruct Q4_K_M (default)|Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf|https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf|5.5|Best all-rounder. Fast, instruction-tuned, fits with room to spare.
Llama 3.1 8B Instruct Q8_0 (high quality)|Meta-Llama-3.1-8B-Instruct-Q8_0.gguf|https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf|9.0|Higher quality than Q4, still fits. Slower throughput.
Mistral 7B Instruct v0.3 Q4_K_M|Mistral-7B-Instruct-v0.3-Q4_K_M.gguf|https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf|5.0|Excellent for coding and structured tasks. Very fast.
Mistral 7B Instruct v0.3 Q8_0|Mistral-7B-Instruct-v0.3-Q8_0.gguf|https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF/resolve/main/Mistral-7B-Instruct-v0.3-Q8_0.gguf|8.5|Near-lossless quality Mistral. Great for long-form writing.
Phi-3.5 Mini Instruct Q4_K_M|Phi-3.5-mini-instruct-Q4_K_M.gguf|https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf|2.8|Tiny but surprisingly capable. Fastest option, great for quick tasks.
Qwen2.5 7B Instruct Q4_K_M|Qwen2.5-7B-Instruct-Q4_K_M.gguf|https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf|5.2|Excellent at coding, maths, multilingual. Strong reasoning.
Qwen2.5 14B Instruct Q4_K_M|Qwen2.5-14B-Instruct-Q4_K_M.gguf|https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf|9.5|Noticeably smarter than 7B. Fits A770 with ctx 4096.
Llama 3.2 3B Instruct Q4_K_M|Llama-3.2-3B-Instruct-Q4_K_M.gguf|https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf|2.5|Ultra-fast. Use as an agent sub-model or for simple tasks.
DeepSeek-R1 7B Distill Q4_K_M|DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf|https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf|5.2|Reasoning/chain-of-thought distill. Great for logic problems.
DeepSeek-R1 14B Distill Q4_K_M|DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf|https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf|9.5|Best reasoning model that fits. Think before answering.
CATALOGUE
}

manage_models() {
    while true; do
        _load_active_model  # refresh in case something changed
        clear
        echo -e "${W}${C}  ╔══════════════════════════════════════════════╗"
        echo -e "  ║          🗂  MODEL MANAGER                   ║"
        echo -e "  ╚══════════════════════════════════════════════╝${N}"
        echo ""

        # ── Installed models ─────────────────────────────────────
        echo -e "${W}  Installed models  (${MODEL_DIR})${N}"
        local installed=()
        while IFS= read -r -d '' f; do
            installed+=("$f")
        done < <(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" -print0 2>/dev/null | sort -z)

        if [[ ${#installed[@]} -eq 0 ]]; then
            echo -e "  ${Y}  No models installed yet.${N}"
        else
            local idx=0
            for f in "${installed[@]}"; do
                local fname; fname=$(basename "$f")
                local size; size=$(du -sh "$f" 2>/dev/null | cut -f1)
                local active_marker="  "
                [[ "$f" == "$MODEL_PATH" ]] && active_marker="${G}▶ ${N}"
                printf "  %b[%d] %-52s %s\n" "$active_marker" "$((++idx))" "$fname" "$size"
            done
        fi

        echo ""
        echo -e "${W}  Actions${N}"
        echo "  d) Download a new model from catalogue"
        echo "  s) Switch active model"
        echo "  r) Remove a model"
        echo "  0) Back to main menu"
        echo ""
        echo -n "  Select: "
        read -r model_opt

        case "${model_opt,,}" in
            d) _download_model_menu ;;
            s) _switch_model_menu "${installed[@]}" ;;
            r) _remove_model_menu "${installed[@]}" ;;
            0|q) return ;;
            *) WARN "Invalid option."; sleep 1 ;;
        esac
    done
}

_download_model_menu() {
    clear
    echo -e "${W}${C}  ╔══════════════════════════════════════════════╗"
    echo -e "  ║       ⬇  DOWNLOAD A MODEL                    ║"
    echo -e "  ╚══════════════════════════════════════════════╝${N}"
    echo ""
    echo -e "${W}  Available models — all fit on Intel Arc A770 (16 GB)${N}"
    echo ""

    local names=() files=() urls=() vrams=() descs=()
    local i=0
    while IFS='|' read -r name file url vram desc; do
        names+=("$name"); files+=("$file"); urls+=("$url")
        vrams+=("$vram"); descs+=("$desc")
        printf "  ${W}[%2d]${N} %-45s ${C}%s GB VRAM${N}\n" "$((++i))" "$name" "$vram"
        echo -e "       ${descs[$((i-1))]}"
        echo ""
    done < <(_model_catalogue)

    echo "  [0] Cancel"
    echo ""
    echo -n "  Select model to download: "
    read -r sel

    [[ "$sel" == "0" || -z "$sel" ]] && return
    if ! [[ "$sel" =~ ^[0-9]+$ ]] || (( sel < 1 || sel > ${#names[@]} )); then
        WARN "Invalid selection."; sleep 1; return
    fi

    local idx=$(( sel - 1 ))
    local dest="$MODEL_DIR/${files[$idx]}"

    if [[ -f "$dest" ]]; then
        OK "Already downloaded: ${files[$idx]}"
        if ask "Set as active model?"; then
            echo "$dest" > "$MODEL_CONFIG"
            _load_active_model
            OK "Active model → $(basename "$MODEL_PATH")"
        fi
        PAUSE; return
    fi

    echo ""
    INFO "Downloading ${names[$idx]}…"
    INFO "Destination: $dest"
    INFO "Estimated VRAM: ${vrams[$idx]} GB"
    echo ""
    mkdir -p "$MODEL_DIR"
    wget --show-progress -O "$dest" "${urls[$idx]}"
    local exit_code=$?
    if [[ $exit_code -eq 0 && -f "$dest" ]]; then
        OK "Download complete: $(du -sh "$dest" | cut -f1)"
        if ask "Set as active model now?"; then
            echo "$dest" > "$MODEL_CONFIG"
            _load_active_model
            OK "Active model → $(basename "$MODEL_PATH")"
            WARN "Restart the stack (option 3 then 2) to load the new model."
        fi
    else
        WARN "Download failed or incomplete — removing partial file."
        rm -f "$dest"
    fi
    PAUSE
}

_switch_model_menu() {
    local installed=("$@")
    if [[ ${#installed[@]} -eq 0 ]]; then
        WARN "No models installed. Download one first (option d)."
        PAUSE; return
    fi

    clear
    echo -e "${W}${C}  Switch Active Model${N}"
    echo ""
    local i=0
    for f in "${installed[@]}"; do
        local fname; fname=$(basename "$f")
        local size; size=$(du -sh "$f" 2>/dev/null | cut -f1)
        local active_marker=""
        [[ "$f" == "$MODEL_PATH" ]] && active_marker=" ${G}← active${N}"
        printf "  ${W}[%d]${N} %s  %s%b\n" "$((++i))" "$fname" "$size" "$active_marker"
    done
    echo ""
    echo "  [0] Cancel"
    echo ""
    echo -n "  Select model to activate: "
    read -r sel

    [[ "$sel" == "0" || -z "$sel" ]] && return
    if ! [[ "$sel" =~ ^[0-9]+$ ]] || (( sel < 1 || sel > ${#installed[@]} )); then
        WARN "Invalid selection."; sleep 1; return
    fi

    local chosen="${installed[$((sel-1))]}"
    echo "$chosen" > "$MODEL_CONFIG"
    _load_active_model
    OK "Active model → $(basename "$MODEL_PATH")"
    WARN "Restart the stack (option 3 then 2) to load the new model."
    PAUSE
}

_remove_model_menu() {
    local installed=("$@")
    if [[ ${#installed[@]} -eq 0 ]]; then
        WARN "No models installed."; PAUSE; return
    fi

    clear
    echo -e "${W}${C}  Remove a Model${N}"
    echo ""
    local i=0
    for f in "${installed[@]}"; do
        local fname; fname=$(basename "$f")
        local size; size=$(du -sh "$f" 2>/dev/null | cut -f1)
        printf "  ${W}[%d]${N} %s  %s\n" "$((++i))" "$fname" "$size"
    done
    echo ""
    echo "  [0] Cancel"
    echo ""
    echo -n "  Select model to remove: "
    read -r sel

    [[ "$sel" == "0" || -z "$sel" ]] && return
    if ! [[ "$sel" =~ ^[0-9]+$ ]] || (( sel < 1 || sel > ${#installed[@]} )); then
        WARN "Invalid selection."; sleep 1; return
    fi

    local target="${installed[$((sel-1))]}"
    local fname; fname=$(basename "$target")
    local size; size=$(du -sh "$target" 2>/dev/null | cut -f1)

    echo ""
    WARN "About to delete: $fname ($size)"
    if ask "Confirm deletion?" n; then
        rm -f "$target"
        OK "Deleted: $fname"
        # If we just deleted the active model, clear config and auto-select next
        if [[ "$target" == "$MODEL_PATH" ]]; then
            rm -f "$MODEL_CONFIG"
            _load_active_model
            if [[ -n "$MODEL_PATH" ]]; then
                WARN "Active model switched to: $(basename "$MODEL_PATH")"
            else
                WARN "No models remain. Download one with option d."
            fi
        fi
    else
        INFO "Cancelled."
    fi
    PAUSE
}

validate_stack() {
    clear
    echo -e "${W}${C}  Stack Validator${N}"
    echo ""
    echo "  1) Full validation (all services)"
    echo "  2) Engine only"
    echo "  3) Memory server only"
    echo "  4) Search proxy only"
    echo "  5) Full validation (verbose)"
    echo "  0) Back"
    echo ""
    echo -n "  Select: "
    read -r v_opt

    local script
    script="$(dirname "$(realpath "$0")")/validate_stack.py"
    if [[ ! -f "$script" ]]; then
        ERR "validate_stack.py not found — ensure it's in the same directory as this script."
        PAUSE; return
    fi

    case "$v_opt" in
        1) python3 "$script" ;;
        2) python3 "$script" --engine ;;
        3) python3 "$script" --memory ;;
        4) python3 "$script" --search ;;
        5) python3 "$script" --verbose ;;
        0) return ;;
        *) WARN "Invalid option." ;;
    esac
    PAUSE
}


# ================================================================
main() {
    while true; do
        show_menu
        read -r opt
        case "$opt" in
            1)  install_stack       ;;
            2)  start_stack         ;;
            3)  stop_stack          ;;
            4)  restart_stack       ;;
            5)  check_status        ;;
            6)  setup_systemd       ;;
            7)  disable_systemd     ;;
            8)  setup_anythingllm   ;;
            9)  setup_web_search    ;;
            10) view_logs           ;;
            11) validate_stack      ;;
            12) benchmark           ;;
            13) uninstall           ;;
            14) manage_models       ;;
            15) python3 llm_factory_rustaikit.py ;;
            0)  echo "Bye!"; exit 0 ;;
            *)  WARN "Invalid option."; sleep 1 ;;
        esac
    done
}

main "$@"