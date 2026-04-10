#!/bin/bash
# ================================================================
#  server-window.sh
#  Runs INSIDE a terminal window.  Starts llama-server in the
#  foreground so all output is visible.  When the process exits
#  (crash, Ctrl-C, or stop from another source) it shows a
#  summary and waits for the user to close the window.
#
#  Do NOT call this directly — use run-server-window.sh which
#  opens the terminal for you.
# ================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/ai_stack"
MODEL_DIR="$INSTALL_DIR/models"
MODEL_CONFIG="$INSTALL_DIR/.active_model"
LLAMACPP_BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
LOG_DIR="$INSTALL_DIR/logs"
PID_FILE="$INSTALL_DIR/.pids"
ENGINE_PORT=8080

# ── Colours ─────────────────────────────────────────────────────
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' C='\033[0;36m'
B='\033[1;34m' W='\033[1m' N='\033[0m'
ok()   { echo -e "${G}  ✅  $*${N}"; }
info() { echo -e "${C}  ℹ   $*${N}"; }
warn() { echo -e "${Y}  ⚠   $*${N}"; }
err()  { echo -e "${R}  ✗   $*${N}"; }
sep()  { echo -e "${C}  ────────────────────────────────────────────${N}"; }

# ── Header ───────────────────────────────────────────────────────
clear
echo ""
echo -e "${B}${W}  ╔══════════════════════════════════════════════════════╗"
echo -e "  ║   🦀  rust-ai-kit  —  llama-server                   ║"
echo -e "  ╚══════════════════════════════════════════════════════╝${N}"
echo ""

# ── oneAPI ──────────────────────────────────────────────────────
if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
    source /opt/intel/oneapi/setvars.sh --force >/dev/null 2>&1 || true
fi
export ONEAPI_DEVICE_SELECTOR="level_zero:0"
export SYCL_DEVICE_FILTER="level_zero:gpu"
[[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env" 2>/dev/null || true

# ── GPU ─────────────────────────────────────────────────────────
GPU_LAYERS=0
if command -v clinfo >/dev/null 2>&1 && clinfo -l 2>/dev/null | grep -qi "intel"; then
    GPU_LAYERS=99
    ok "Intel Arc GPU visible — SYCL enabled (99 layers)"
else
    warn "GPU not visible — falling back to CPU inference"
fi

# ── Model ────────────────────────────────────────────────────────
MODEL_PATH=""
[[ -f "$MODEL_CONFIG" ]] && MODEL_PATH=$(cat "$MODEL_CONFIG" | tr -d '[:space:]')
if [[ -z "$MODEL_PATH" ]] || [[ ! -f "$MODEL_PATH" ]]; then
    MODEL_PATH=$(find "$MODEL_DIR" -maxdepth 1 -name "*.gguf" 2>/dev/null | sort | head -1)
    [[ -n "$MODEL_PATH" ]] && echo "$MODEL_PATH" > "$MODEL_CONFIG"
fi

if [[ ! -f "$LLAMACPP_BIN" ]]; then
    err "llama-server binary not found: $LLAMACPP_BIN"
    err "Run:  ./ai_stack_manager.sh  →  option 1  to install llama.cpp"
    echo ""; read -rp "  Press Enter to close this window..." _; exit 1
fi

if [[ -z "$MODEL_PATH" ]] || [[ ! -f "$MODEL_PATH" ]]; then
    err "No .gguf model found in $MODEL_DIR"
    err "Use the Model Manager → Download tab to get one first."
    echo ""; read -rp "  Press Enter to close this window..." _; exit 1
fi

# ── Load saved ModelRunConfig if present ─────────────────────────
# The Python app saves per-model JSON configs.  Parse them here
# with python3 so the window respects what the UI configured.
CFG_DIR="$SCRIPT_DIR/core/config"
MODEL_STEM="$(basename "$MODEL_PATH" .gguf)"
CFG_FILE="$CFG_DIR/model_configs/${MODEL_STEM}.json"

CTX_SIZE=8192
BATCH_SIZE=512
THREADS=8
PARALLEL=1
EXTRA_FLAGS=""

if [[ -f "$CFG_FILE" ]] && command -v python3 >/dev/null 2>&1; then
    read -r CTX_SIZE BATCH_SIZE THREADS PARALLEL GPU_LAYERS_CFG FLASH_ATTN CONT_BATCH MLOCK JINJA SPLIT_MODE MAIN_GPU < <(
        python3 - "$CFG_FILE" <<'PYEOF'
import sys, json
d = json.load(open(sys.argv[1]))
print(
    d.get('ctx_size',8192),
    d.get('batch_size',512),
    d.get('threads',8),
    d.get('parallel',1),
    d.get('n_gpu_layers',99),
    int(d.get('flash_attn',True)),
    int(d.get('cont_batching',True)),
    int(d.get('mlock',False)),
    int(d.get('jinja',False)),
    d.get('split_mode','none'),
    d.get('main_gpu',0),
)
PYEOF
    )
    GPU_LAYERS=$GPU_LAYERS_CFG
    [[ "$FLASH_ATTN"  == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --flash-attn"
    [[ "$CONT_BATCH"  == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --cont-batching"
    [[ "$MLOCK"       == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --mlock"
    [[ "$JINJA"       == "1" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --jinja"
    [[ "$SPLIT_MODE"  != "none" ]] && EXTRA_FLAGS="$EXTRA_FLAGS --split-mode $SPLIT_MODE"
    EXTRA_FLAGS="$EXTRA_FLAGS --main-gpu $MAIN_GPU"
    info "Loaded config from: $(basename "$CFG_FILE")"
fi

# Kill anything already on the port
STALE=$(lsof -ti ":${ENGINE_PORT}" 2>/dev/null | head -1)
if [[ -n "$STALE" ]]; then
    warn "Port ${ENGINE_PORT} already in use (PID $STALE) — stopping it first..."
    kill -9 "$STALE" 2>/dev/null || true
    sleep 1
fi

# ── Summary ──────────────────────────────────────────────────────
sep
echo -e "  ${W}Model   :${N}  $(basename "$MODEL_PATH")"
echo -e "  ${W}Context :${N}  ${CTX_SIZE} tokens"
echo -e "  ${W}Batch   :${N}  ${BATCH_SIZE}"
echo -e "  ${W}Threads :${N}  ${THREADS}"
echo -e "  ${W}GPU lyr :${N}  ${GPU_LAYERS}"
echo -e "  ${W}Port    :${N}  ${ENGINE_PORT}"
[[ -n "$EXTRA_FLAGS" ]] && echo -e "  ${W}Extras  :${N} $EXTRA_FLAGS"
ip a | grep 192.168
sep
echo ""
echo -e "${Y}  Press Ctrl-C at any time to stop the server.${N}"
echo ""
sleep 5

mkdir -p "$LOG_DIR"

# ── Write PID stub (will be overwritten once server starts) ──────
SERVER_PID=""

cleanup() {
    echo ""
    sep
    warn "Stopping llama-server…"
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
    pkill -f "llama-server" 2>/dev/null || true
    sleep 1
    ok "Server stopped."
    sep
    echo ""
    read -rp "  Press Enter to close this window..." _
    exit 0
}
trap cleanup INT TERM

# ── Start server in foreground — output goes to this terminal ─────
# Also tee to log file so the Logs tab stays useful.
exec "$LLAMACPP_BIN" \
    --model         "$MODEL_PATH" \
    --ctx-size      "$CTX_SIZE" \
    --batch-size    "$BATCH_SIZE" \
    --threads       "$THREADS" \
    --n-gpu-layers  "$GPU_LAYERS" \
    --parallel      "$PARALLEL" \
    --port          "$ENGINE_PORT" \
    --host          0.0.0.0 \
    --api-key       local \
    $EXTRA_FLAGS \
    2>&1 | tee -a "$LOG_DIR/engine.log"

# ── Reached here only if exec somehow returns (shouldn't happen) ──
echo ""
sep
warn "llama-server exited."
sep
echo ""
read -rp "  Press Enter to close this window..." _
