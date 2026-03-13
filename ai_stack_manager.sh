#!/bin/bash
# ================================================================
#  🤖  RUST-AI STACK MANAGER  —  Ubuntu 24.04
#  GPU: Intel Arc A770 (SYCL/oneAPI backend)
#  Components: llama.cpp/SYCL · MemU · AnythingLLM · SearXNG
# ================================================================

INSTALL_DIR="$HOME/ai_stack"
MODEL_DIR="$INSTALL_DIR/models"
MODEL_PATH="$MODEL_DIR/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
LLAMACPP_BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
MEMU_DIR="$INSTALL_DIR/memu"
LOG_DIR="$INSTALL_DIR/logs"
PID_FILE="$INSTALL_DIR/.pids"
APPS_DIR="$HOME/Applications"
SYSTEMD_DIR="$HOME/.config/systemd/user"

ENGINE_PORT=8080
SEARXNG_PORT=8081

# ── Intel Arc A770 SYCL env ─────────────────────────────────────
_source_envs() {

    [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"

    if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
        source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true
    fi

    export ONEAPI_DEVICE_SELECTOR="level_zero:0"
    export SYCL_DEVICE_FILTER="level_zero:gpu"

    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
}

_source_envs

# ── Colours ─────────────────────────────────────────────────────
R='\033[0;31m'
G='\033[0;32m'
Y='\033[1;33m'
B='\033[0;34m'
C='\033[0;36m'
W='\033[1m'
N='\033[0m'

OK(){ echo -e "${G}  ✅ $*${N}"; }
INFO(){ echo -e "${C}  ℹ️  $*${N}"; }
WARN(){ echo -e "${Y}  ⚠️  $*${N}"; }
ERR(){ echo -e "${R}  ❌ $*${N}"; }

PAUSE(){ read -rp "$(echo -e "${Y}Press Enter to continue...${N}")"; }

# ================================================================
# MENU
# ================================================================

show_menu(){

clear

echo -e "${B}${W}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   🤖  RUST-AI STACK MANAGER                  ║"
echo "  ║       Ubuntu 24.04  ·  Intel Arc A770        ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${N}"

echo " 1) Install stack"
echo " 2) Start stack"
echo " 3) Stop stack"
echo " 4) Status"
echo ""
echo " 5) Enable auto-start"
echo " 6) Disable auto-start"
echo ""
echo " 7) Setup SearXNG search"
echo " 8) View logs"
echo " 9) Benchmark GPU"
echo "10) Uninstall"
echo ""
echo " 0) Exit"
echo ""
read -rp "Select: " opt

case $opt in

1) install_stack ;;
2) start_stack ;;
3) stop_stack ;;
4) check_status ;;
5) setup_systemd ;;
6) disable_systemd ;;
7) setup_web_search ;;
8) view_logs ;;
9) benchmark ;;
10) uninstall ;;
0) exit 0 ;;

*) WARN "Invalid option"; sleep 1 ;;

esac
}

# ================================================================
# INSTALL
# ================================================================

install_stack(){

local installer
installer="$(dirname "$(realpath "$0")")/install_ai_stack.sh"

if [[ -f "$installer" ]]; then
bash "$installer"
else
WARN "install_ai_stack.sh missing"
fi

PAUSE
}

# ================================================================
# START STACK
# ================================================================

start_stack(){

_source_envs
mkdir -p "$LOG_DIR"

[[ -f "$LLAMACPP_BIN" ]] || { ERR "llama-server missing"; PAUSE; return; }
[[ -f "$MODEL_PATH" ]] || { ERR "Model missing"; PAUSE; return; }
[[ -f "$MEMU_DIR/target/release/memu" ]] || { ERR "MemU missing"; PAUSE; return; }

echo
INFO "Starting llama.cpp engine"

"$LLAMACPP_BIN" \
--model "$MODEL_PATH" \
--ctx-size 4096 \
--batch-size 1024 \
--threads $(nproc) \
--n-gpu-layers -1 \
--port "$ENGINE_PORT" \
--host 0.0.0.0 \
> "$LOG_DIR/engine.log" 2>&1 &

ENGINE_PID=$!

INFO "Waiting for API..."

for i in $(seq 1 90)
do
sleep 1
curl -sf "http://localhost:$ENGINE_PORT/v1/models" >/dev/null && break
done

curl -sf "http://localhost:$ENGINE_PORT/v1/models" >/dev/null || {
ERR "Engine failed to start"
PAUSE
return
}

OK "Engine ready"

echo
INFO "Starting MemU"

"$MEMU_DIR/target/release/memu" \
--api-url "http://localhost:$ENGINE_PORT" \
> "$LOG_DIR/memu.log" 2>&1 &

MEMU_PID=$!

echo "$ENGINE_PID $MEMU_PID" > "$PID_FILE"

OK "MemU started"

echo
INFO "Launching AnythingLLM"

command -v anythingllm >/dev/null && anythingllm &>/dev/null &

OK "Stack running → http://localhost:$ENGINE_PORT"

PAUSE
}

# ================================================================
# STOP
# ================================================================

stop_stack(){

echo
INFO "Stopping stack"

if [[ -f "$PID_FILE" ]]
then
for pid in $(cat "$PID_FILE")
do
kill "$pid" 2>/dev/null && OK "Killed $pid"
done
rm -f "$PID_FILE"
fi

pkill -f llama-server 2>/dev/null
pkill -f memu 2>/dev/null

OK "Stopped"

PAUSE
}

# ================================================================
# STATUS
# ================================================================

check_status(){

clear

echo -e "${W}Stack Status${N}"
echo

curl -sf "http://localhost:$ENGINE_PORT/v1/models" >/dev/null \
&& OK "API responding" \
|| WARN "API not responding"

echo

INFO "GPU detection"

clinfo -l 2>/dev/null | grep -i intel || WARN "GPU not visible"

echo
INFO "Disk usage"
du -sh "$INSTALL_DIR"

PAUSE
}

# ================================================================
# SYSTEMD
# ================================================================

setup_systemd(){

mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/llamaedge.service" <<EOF
[Unit]
Description=llama.cpp SYCL engine
After=network.target

[Service]
Environment=ONEAPI_DEVICE_SELECTOR=level_zero:0
Environment=SYCL_DEVICE_FILTER=level_zero:gpu
ExecStart=$LLAMACPP_BIN \
 --model $MODEL_PATH \
 --ctx-size 4096 \
 --batch-size 1024 \
 --threads $(nproc) \
 --n-gpu-layers -1 \
 --port $ENGINE_PORT \
 --host 0.0.0.0

Restart=on-failure

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable llamaedge

OK "Auto-start enabled"

PAUSE
}

disable_systemd(){

systemctl --user disable --now llamaedge 2>/dev/null
OK "Auto-start disabled"

PAUSE
}

# ================================================================
# SEARXNG
# ================================================================

setup_web_search(){

docker rm -f searxng 2>/dev/null

docker run -d \
--name searxng \
--restart unless-stopped \
-p $SEARXNG_PORT:8080 \
searxng/searxng

OK "SearXNG running → http://localhost:$SEARXNG_PORT"

PAUSE
}

# ================================================================
# LOGS
# ================================================================

view_logs(){

echo
echo "1 Engine"
echo "2 MemU"
read -r opt

case $opt in

1) tail -n 50 "$LOG_DIR/engine.log" ;;
2) tail -n 50 "$LOG_DIR/memu.log" ;;

esac

PAUSE
}

# ================================================================
# BENCHMARK
# ================================================================

benchmark(){

INFO "Running quick benchmark..."

curl -X POST "http://localhost:$ENGINE_PORT/v1/completions" \
-H "Content-Type: application/json" \
-d '{"model":"llama","prompt":"The Intel Arc A770 GPU","max_tokens":200}'

echo
INFO "Typical Arc A770 throughput: 25-45 tok/s"

PAUSE
}

# ================================================================
# UNINSTALL
# ================================================================

uninstall(){

WARN "Removing stack"

rm -rf "$INSTALL_DIR"

docker rm -f searxng 2>/dev/null

OK "Removed"

PAUSE
}

# ================================================================
# MAIN LOOP
# ================================================================

while true
do
show_menu
done
