# rust-ai-kit 🦀⚡

> **A fully local, GPU-accelerated AI stack for Intel Arc — built on Rust, llama.cpp, and oneAPI SYCL.**
> Private. Fast. Yours.

[![Ubuntu 24.04](https://img.shields.io/badge/Ubuntu-24.04_LTS-E95420?style=flat-square&logo=ubuntu&logoColor=white)](https://ubuntu.com)
[![Intel Arc A770](https://img.shields.io/badge/GPU-Intel_Arc_A770-0071C5?style=flat-square&logo=intel&logoColor=white)](https://www.intel.com/content/www/us/en/products/sku/229151/intel-arc-a770-graphics-16gb/specifications.html)
[![llama.cpp](https://img.shields.io/badge/Engine-llama.cpp_SYCL-8A2BE2?style=flat-square)](https://github.com/ggerganov/llama.cpp)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)

---

## What Is This?

`rust-ai-kit` is a **two-script toolkit** that turns an Ubuntu 24.04 machine with an Intel Arc A770 into a fully self-hosted AI workstation — no cloud, no subscriptions, no data leaving your machine.

It installs and manages a complete inference stack:

```
┌─────────────────────────────────────────────────────────┐
│                    AnythingLLM  (UI)                    │
│                  localhost:3001 · AppImage               │
├─────────────────────────────────────────────────────────┤
│              llama-server  (OpenAI-compatible API)       │
│               llama.cpp · SYCL · localhost:8080          │
├──────────────────────────┬──────────────────────────────┤
│   Intel Arc A770 (SYCL)  │   Intel oneAPI 2025.x        │
│   16 GB VRAM · level-zero│   icx/icpx compilers         │
└──────────────────────────┴──────────────────────────────┘
```

The API is **OpenAI-compatible** — anything that speaks to ChatGPT can speak to this instead.

---

## Why Intel Arc + SYCL?

Most local AI guides assume NVIDIA. The Arc A770's **16 GB VRAM** is exceptional value — larger than most consumer NVIDIA cards — but getting GPU acceleration working requires Intel's SYCL stack (oneAPI / level-zero) rather than CUDA. This kit handles all of that automatically.

| Feature | This Kit |
|---|---|
| VRAM | 16 GB (full model on-GPU) |
| Model size supported | Up to ~13B Q4 comfortably |
| Backend | llama.cpp SYCL (Intel-native, not a CUDA wrapper) |
| API | OpenAI-compatible REST on `localhost:8080` |
| Privacy | 100% local — zero telemetry, zero cloud |
| Cost after hardware | £0/month |

---

## Repository Contents

```
rust-ai-kit/
├── install_ai_stack.sh   # One-shot installer (run once)
└── ai_stack_manager.sh   # Interactive management menu (run daily)
```

That's it. Two scripts, one purpose.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Ubuntu 24.04 LTS | Fresh install recommended; tested on noble |
| Intel Arc A770 | 16 GB variant; A750/A580 should work with minor VRAM adjustments |
| ~8 GB free disk | ~5 GB model + ~1.5 GB oneAPI compiler + build artifacts |
| Internet connection | For initial download only |
| `sudo` access | Required for apt and group changes |

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/MasterMould/rust-ai-kit.git
cd rust-ai-kit

# 2. Make scripts executable
chmod +x install_ai_stack.sh ai_stack_manager.sh

# 3. Run the installer (takes ~20–30 min including model download)
./install_ai_stack.sh

# 4. ⚠️  LOG OUT AND BACK IN — required for render group + oneAPI env

# 5. Launch the manager
./ai_stack_manager.sh
```

Then select **2) Start AI Stack** from the menu.

---

## Installer Walkthrough

`install_ai_stack.sh` runs seven steps, each idempotent — safe to re-run if interrupted:

### Step 1 — System Packages
Installs build essentials: `cmake`, `ninja-build`, `libssl-dev`, `libopenblas-dev`, `libfuse2`, `libwebkit2gtk`, and supporting libraries. Skips anything already present.

### Step 2 — Intel Arc GPU Drivers
The most complex step — sets up the two separate Intel driver stacks that the Arc A770 needs:

- **OpenCL** (`intel-opencl-icd`) — general compute, verified by `clinfo`
- **SYCL/level-zero** (`libze-intel-gpu1`) — **required for llama.cpp GPU acceleration**; this is the one most guides miss

> **Common pitfall:** These two stacks come from different apt repositories and have historically conflicting packages on Noble. The installer handles this by checking each independently and never removing an already-working package.

### Step 3 — Rust Toolchain
Installs via `rustup` if not present. Used to build any Rust-based components. Skips if `cargo` already exists.

### Step 4 — llama.cpp (SYCL build from source)
Clones [llama.cpp](https://github.com/ggerganov/llama.cpp) and compiles it with Intel's `icx`/`icpx` compilers from oneAPI:

```bash
cmake -B build -DGGML_SYCL=ON \
      -DCMAKE_C_COMPILER=icx \
      -DCMAKE_CXX_COMPILER=icpx \
      -DGGML_SYCL_F16=ON
```

This produces a native `llama-server` binary with full Arc A770 SYCL acceleration — not an emulation layer, not CUDA translation. The binary lives at `~/ai_stack/llama.cpp/build/bin/llama-server`.

> **Why build from source?** There are no pre-built Intel SYCL binaries for llama.cpp. NVIDIA users can `brew install` or grab AppImages; Arc users must compile. This step takes ~5 minutes.

### Step 5 — Model Download
Downloads **Meta-Llama-3.1-8B-Instruct Q4\_K\_M** (~4.9 GB) from Hugging Face. At Q4\_K\_M quantisation, this fits entirely in the A770's 16 GB VRAM with room to spare for a context window of 8192 tokens.

```
Model:   Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
Size:    ~4.9 GB
VRAM:    ~5.5 GB loaded
Quality: Excellent for instruction-following, coding, analysis
```

Want a different model? Drop any GGUF into `~/ai_stack/models/` and update `MODEL_PATH` at the top of `ai_stack_manager.sh`.

### Step 6 — MemU (optional)
Attempts to build the MemU persistent memory layer. Skipped gracefully if unavailable — the core stack functions without it. AnythingLLM's built-in RAG pipeline serves as an alternative.

### Step 7 — AnythingLLM Desktop
Downloads the official AppImage, makes it executable, and creates a desktop shortcut. Connects to `llama-server` on port 8080 as an OpenAI-compatible provider.

---

## The Manager Menu

`ai_stack_manager.sh` provides an interactive TUI for day-to-day operation:

```
  ╔══════════════════════════════════════════════╗
  ║   🤖  RUST-AI STACK MANAGER                  ║
  ║       Ubuntu 24.04  ·  Intel Arc A770        ║
  ╚══════════════════════════════════════════════╝
  Engine: ● running   MemU: ○ stopped
  Search: ○ stopped   GPU:  ● Arc A770 visible
```

| Option | Action |
|---|---|
| **1** | Full automated install (calls `install_ai_stack.sh`) |
| **2** | Start AI stack (engine + MemU + AnythingLLM) |
| **3** | Stop all stack processes |
| **4** | Status check — API health, GPU info, disk usage |
| **5** | Enable systemd auto-start on boot |
| **6** | Disable auto-start |
| **7** | Deploy SearXNG private web search (Docker) |
| **8** | View logs (engine / MemU / SearXNG) |
| **9** | GPU benchmark — tokens/sec measurement |
| **10** | Full uninstall |

### Starting the Stack

When you select **2**, the manager:
1. Checks the Arc A770 is visible to level-zero (catches the common render-group issue before a cryptic crash)
2. Launches `llama-server` with `--n-gpu-layers 99` and `ONEAPI_DEVICE_SELECTOR=level_zero:0`
3. Polls `http://localhost:8080/v1/models` for up to 90 seconds
4. Starts MemU if available
5. Launches AnythingLLM

### API Access

Once running, the stack exposes a standard OpenAI-compatible API:

```bash
# List models
curl http://localhost:8080/v1/models

# Chat completion
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

Any tool that supports a custom OpenAI base URL works: **Open WebUI**, **Continue.dev** (VS Code), **LM Studio** (as client), **Aider**, and hundreds of others.

### Web Search Integration

Option 7 deploys [SearXNG](https://github.com/searxng/searxng) in Docker — a self-hosted metasearch engine that aggregates results from multiple search providers without tracking:

```bash
# After setup, SearXNG is available at:
http://localhost:8081

# Connect to AnythingLLM:
# Workspace → Agent Config → Search Provider → SearXNG → http://localhost:8081
```

---

## Systemd Auto-Start

Option 5 creates user-level systemd services that start the stack on login (no root required):

```ini
# ~/.config/systemd/user/llamaedge.service
[Service]
Environment="ONEAPI_DEVICE_SELECTOR=level_zero:0"
Environment="SYCL_DEVICE_FILTER=level_zero:gpu"
ExecStart=/home/user/ai_stack/llama.cpp/build/bin/llama-server \
    --model ... --n-gpu-layers 99 --port 8080
```

`loginctl enable-linger` is set automatically so services survive logout.

---

## Troubleshooting

### `No device of requested type available` (SYCL crash)

This is the most common issue. It means level-zero cannot see the GPU — almost always one of two causes:

**Cause 1: Missing `libze-intel-gpu1`**
```bash
dpkg -l libze-intel-gpu1 | grep '^ii'
# If not shown:
sudo apt-get install libze-intel-gpu1
```

**Cause 2: Not in `render` group (requires re-login)**
```bash
groups  # check for 'render' in the list
# If missing, the installer added you but you haven't re-logged in:
# Log out and back in, then try again.
```

### GPU visible to `clinfo` but not to llama.cpp

OpenCL and SYCL/level-zero are separate stacks. `clinfo` uses OpenCL; llama.cpp SYCL uses level-zero. Both `intel-opencl-icd` *and* `libze-intel-gpu1` must be installed.

```bash
# Verify both stacks:
clinfo -l                          # should show Intel Arc (OpenCL)
dpkg -l libze-intel-gpu1           # should show 'ii' status (level-zero)
```

### `icx: command not found` during build

The oneAPI compiler package is `intel-oneapi-compiler-dpcpp-cpp` (not `intel-oneapi-dpcpp-cpp`):

```bash
sudo apt-get install intel-oneapi-compiler-dpcpp-cpp
source /opt/intel/oneapi/setvars.sh
icx --version
```

### Engine starts but performance is slow

Verify the model is running on GPU, not CPU:

```bash
# Should show SYCL device usage during inference:
tail -f ~/ai_stack/logs/engine.log | grep -i "sycl\|gpu\|layer"
```

If layers show as `CPU`, the SYCL plugin didn't load — check `libze-intel-gpu1` is installed and you've re-logged in after the group change.

### Port 8080 already in use

```bash
# Find what's using it:
lsof -i :8080 -sTCP:LISTEN
# Kill a stale llama-server:
pkill -f llama-server
```

---

## Architecture Notes

### Why llama.cpp instead of LlamaEdge / WasmEdge?

LlamaEdge (WebAssembly-based) has no pre-built SYCL plugin for current WasmEdge releases — the `wasi_nn-ggml-sycl` plugin simply doesn't exist as a downloadable binary. Building it from source requires patching WasmEdge itself. llama.cpp's SYCL backend is Intel's own recommended path for Arc GPU inference and is actively maintained by both the llama.cpp community and Intel engineers.

### Why not Ollama?

Ollama does not support Intel Arc via SYCL at the time of writing. It uses CUDA (NVIDIA only) or CPU fallback. `llama-server` with SYCL gives you native Arc acceleration that Ollama cannot.

### Why not ROCm?

ROCm is AMD's GPU compute stack. Intel Arc uses Intel's oneAPI/SYCL stack. They are not interchangeable.

---

## Performance Expectations

Tested on Intel Arc A770 16GB, Ubuntu 24.04, oneAPI 2025.3:

| Model | Quant | VRAM | Tokens/sec (est.) |
|---|---|---|---|
| Llama 3.1 8B | Q4\_K\_M | ~5.5 GB | 25–45 tok/s |
| Llama 3.1 8B | Q8\_0 | ~9 GB | 18–30 tok/s |
| Llama 3 13B | Q4\_K\_M | ~9 GB | 15–25 tok/s |
| Mistral 7B | Q4\_K\_M | ~5 GB | 28–48 tok/s |

Use option **9** (Benchmark) in the manager to measure your actual throughput.

---

## File Layout After Install

```
~/
├── ai_stack/
│   ├── models/
│   │   └── Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
│   ├── llama.cpp/
│   │   └── build/bin/
│   │       └── llama-server          ← main engine binary
│   ├── memu/                         ← optional memory layer
│   ├── logs/
│   │   ├── engine.log
│   │   └── memu.log
│   ├── start_ai_stack.sh             ← standalone launcher
│   └── .pids                         ← running process IDs
├── Applications/
│   └── AnythingLLM.AppImage
└── .config/systemd/user/
    ├── llamaedge.service
    └── memu.service
```

---

## Contributing

Issues, PRs and tested hardware reports are welcome. If you've got this working on an Arc A750, A580, or with a different model — open an issue and share your config.

When reporting bugs, please include:

```bash
# Attach this output to your issue:
uname -a
dpkg -l intel-opencl-icd libze-intel-gpu1 libze1 intel-oneapi-compiler-dpcpp-cpp 2>/dev/null | grep '^ii'
clinfo -l
groups
tail -30 ~/ai_stack/logs/engine.log
```

---

## Licence

MIT — do whatever you like with it.

---

<div align="center">

**Built for people who believe their AI should run on their hardware.**

*Intel Arc A770 · llama.cpp SYCL · Ubuntu 24.04 · oneAPI 2025*

</div>
