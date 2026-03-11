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
MODEL_PATH="$MODEL_DIR/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
LLAMACPP_BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
MEMU_DIR="$INSTALL_DIR/memu"
LOG_DIR="$INSTALL_DIR/logs"
PID_FILE="$INSTALL_DIR/.pids"
APPS_DIR="$HOME/Applications"
SYSTEMD_DIR="$HOME/.config/systemd/user"

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
    echo "  4)  Check Status + GPU Info"
    echo ""
    echo -e "${W}  Autostart${N}"
    echo "  5)  Enable Auto-Start on Boot (systemd)"
    echo "  6)  Disable Auto-Start"
    echo ""
    echo -e "${W}  Extras${N}"
    echo "  7)  Setup Web Search (SearXNG)"
    echo "  8)  View Logs"
    echo "  9)  Benchmark GPU (quick inference test)"
    echo "  10) Uninstall / Clean Up"
    echo ""
    echo "  0)  Exit"
    echo -e "${B}  ──────────────────────────────────────────────${N}"
    echo -n "  Select: "
}

_print_quick_status() {
    local engine_s memu_s searxng_s gpu_s
    if _svc_running "llamaedge"; then
        engine_s="${G}● running${N}"
    elif pgrep -f "llama-server" &>/dev/null; then
        engine_s="${Y}● running (no systemd)${N}"
    else
        engine_s="${R}○ stopped${N}"
    fi

    _svc_running "memu" && memu_s="${G}● running${N}" || memu_s="${R}○ stopped${N}"

    if docker ps --filter name=searxng --filter status=running -q 2>/dev/null | grep -q .; then
        searxng_s="${G}● running${N}"
    else
        searxng_s="${R}○ stopped${N}"
    fi

    # Arc A770 visible?
    if clinfo -l 2>/dev/null | grep -qi "intel"; then
        gpu_s="${G}● Arc A770 visible${N}"
    else
        gpu_s="${Y}⚠ GPU not detected${N}"
    fi

    echo -e "  Engine: $engine_s  MemU: $memu_s"
    echo -e "  Search: $searxng_s  GPU:  $gpu_s"
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

    # Sanity checks
    command -v "$LLAMACPP_BIN" &>/dev/null || [[ -f "$LLAMACPP_BIN" ]] \
        || { ERR "llama-server not found. Run Install (option 1) first."; PAUSE; return; }
    [[ -f "$MODEL_PATH" ]]                     || { ERR "Model not found. Run Install first."; PAUSE; return; }
    [[ -f "$MEMU_DIR/target/release/memu" ]]   || { ERR "MemU binary missing. Run Install first."; PAUSE; return; }

    if lsof -i ":$ENGINE_PORT" -sTCP:LISTEN -t &>/dev/null; then
        WARN "Port $ENGINE_PORT already in use — stack may already be running."
        ask "Start anyway?" n || { PAUSE; return; }
    fi

    STEP "llama-server (llama.cpp SYCL → Arc A770)"
    INFO "Backend:  level_zero:0  (full 16 GB VRAM)"
    INFO "Model:    $(basename "$MODEL_PATH")"
    INFO "Context:  8192 tokens"

    ONEAPI_DEVICE_SELECTOR="level_zero:0" \
    SYCL_DEVICE_FILTER="level_zero:gpu" \
    "$LLAMACPP_BIN" \
        --model "$MODEL_PATH" \
        --ctx-size 8192 \
        --n-gpu-layers 99 \
        --port "$ENGINE_PORT" \
        --host 0.0.0.0 \
        > "$LOG_DIR/engine.log" 2>&1 &
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

    STEP "MemU memory layer"
    "$MEMU_DIR/target/release/memu" \
        --api-url "http://localhost:$ENGINE_PORT" \
        > "$LOG_DIR/memu.log" 2>&1 &
    local memu_pid=$!
    sleep 2
    OK "MemU started (PID: $memu_pid)"

    echo "$engine_pid $memu_pid" > "$PID_FILE"

    STEP "AnythingLLM UI"
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
stop_stack() {
    STEP "Stopping AI Stack"
    local stopped=0

    if systemctl --user is-active llamaedge.service &>/dev/null; then
        systemctl --user stop llamaedge.service memu.service 2>/dev/null || true
        OK "Systemd services stopped."; stopped=1
    fi

    if [[ -f "$PID_FILE" ]]; then
        read -r pids < "$PID_FILE" 2>/dev/null || pids=""
        for pid in $pids; do
            kill -0 "$pid" 2>/dev/null && kill "$pid" && OK "Killed PID $pid" || true
            stopped=1
        done
        rm -f "$PID_FILE"
    fi

    pkill -f "llama-server"   2>/dev/null && { OK "Killed llama-server."; stopped=1; } || true
    pkill -f "memu --api-url" 2>/dev/null && { OK "Killed memu.";         stopped=1; } || true

    [[ $stopped -eq 0 ]] && WARN "No running processes found." || OK "Stack stopped."
    PAUSE
}

# ================================================================
#  4. STATUS + GPU INFO
# ================================================================
check_status() {
    clear
    echo -e "${W}${C}  STATUS — Intel Arc A770${N}\n"

    # Services
    for svc in llamaedge memu; do
        if systemctl --user is-active "$svc.service" &>/dev/null; then
            echo -e "  ${G}● $svc${N}  (systemd active)"
        elif pgrep -f "$svc" &>/dev/null; then
            echo -e "  ${Y}● $svc${N}  (running, no systemd)"
        else
            echo -e "  ${R}○ $svc${N}  (not running)"
        fi
    done

    # API
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

    mkdir -p "$SYSTEMD_DIR" "$LOG_DIR"

    cat > "$SYSTEMD_DIR/llamaedge.service" <<EOF
[Unit]
Description=llama-server (llama.cpp SYCL — Intel Arc A770)
After=network.target

[Service]
Environment="ONEAPI_DEVICE_SELECTOR=level_zero:0"
Environment="SYCL_DEVICE_FILTER=level_zero:gpu"
Environment="PATH=/opt/intel/oneapi/compiler/latest/bin:/usr/local/bin:/usr/bin:/bin"
ExecStartPre=/bin/bash -c 'source /opt/intel/oneapi/setvars.sh --force 2>/dev/null || true'
ExecStart=$LLAMACPP_BIN \
    --model $MODEL_PATH \
    --ctx-size 8192 \
    --n-gpu-layers 99 \
    --port $ENGINE_PORT \
    --host 0.0.0.0
Restart=on-failure
RestartSec=10
StandardOutput=append:$LOG_DIR/engine.log
StandardError=append:$LOG_DIR/engine.log

[Install]
WantedBy=default.target
EOF

    cat > "$SYSTEMD_DIR/memu.service" <<EOF
[Unit]
Description=MemU Persistent Memory Layer
After=llamaedge.service
Requires=llamaedge.service

[Service]
ExecStartPre=/bin/sleep 15
ExecStart=$MEMU_DIR/target/release/memu --api-url http://localhost:$ENGINE_PORT
Restart=on-failure
RestartSec=5
StandardOutput=append:$LOG_DIR/memu.log
StandardError=append:$LOG_DIR/memu.log

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable llamaedge.service memu.service
    loginctl enable-linger "$USER"

    OK "Auto-start enabled. Services will start at login/boot."
    INFO "Start now? → systemctl --user start llamaedge.service"
    PAUSE
}

disable_systemd() {
    STEP "Disabling auto-start"
    systemctl --user disable --now llamaedge.service memu.service 2>/dev/null \
        && OK "Auto-start disabled." || WARN "Services were not enabled."
    PAUSE
}

# ================================================================
#  7. SEARXNG
# ================================================================
setup_web_search() {
    STEP "SearXNG private web search"
    local DOCKER="docker"

    if ! command -v docker &>/dev/null; then
        INFO "Installing Docker…"
        sudo apt-get update -qq
        sudo apt-get install -y docker.io docker-compose-v2
        sudo systemctl enable --now docker
        sudo usermod -aG docker "$USER"
        WARN "Added to docker group — re-login required. Using sudo for now."
        DOCKER="sudo docker"
    fi

    $DOCKER rm -f searxng 2>/dev/null || true

    $DOCKER run -d \
        --name searxng \
        --restart unless-stopped \
        -p "${SEARXNG_PORT}:8080" \
        -e "SEARXNG_BASE_URL=http://localhost:${SEARXNG_PORT}/" \
        searxng/searxng:latest

    local up=false
    for i in $(seq 1 30); do
        sleep 1; curl -sf "http://localhost:$SEARXNG_PORT" &>/dev/null && { up=true; break; }
    done
    $up && OK "SearXNG live → http://localhost:$SEARXNG_PORT" \
           || WARN "SearXNG still starting — check: docker logs searxng"

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
    echo -e "${W}  Log viewer${N}"
    echo "  1) Engine (LlamaEdge)"
    echo "  2) MemU"
    echo "  3) SearXNG (Docker)"
    echo "  0) Back"
    echo -n "  Select: "
    read -r log_opt
    case "$log_opt" in
        1) tail -n 50 "$LOG_DIR/engine.log" 2>/dev/null || WARN "No engine log yet." ;;
        2) tail -n 50 "$LOG_DIR/memu.log"   2>/dev/null || WARN "No MemU log yet."   ;;
        3) docker logs --tail 50 searxng     2>/dev/null || WARN "SearXNG not running." ;;
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
    systemctl --user disable --now llamaedge.service memu.service 2>/dev/null || true
    rm -f "$SYSTEMD_DIR/llamaedge.service" "$SYSTEMD_DIR/memu.service"
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
#  MAIN LOOP
# ================================================================
main() {
    while true; do
        show_menu
        read -r opt
        case "$opt" in
            1)  install_stack    ;;
            2)  start_stack      ;;
            3)  stop_stack       ;;
            4)  check_status     ;;
            5)  setup_systemd    ;;
            6)  disable_systemd  ;;
            7)  setup_web_search ;;
            8)  view_logs        ;;
            9)  benchmark        ;;
            10) uninstall        ;;
            0)  echo "Bye!"; exit 0 ;;
            *)  WARN "Invalid option."; sleep 1 ;;
        esac
    done
}

main "$@"
