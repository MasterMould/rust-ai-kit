# **rust-ai-kit 🦀⚡**  
**A fully local, GPU-accelerated AI stack for Intel Arc — built on llama.cpp SYCL, mem0, and SearXNG.** Private. Fast. No cloud. No subscriptions. No data leaving your machine.  
[![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg==)  
](https://ubuntu.com/ "https://ubuntu.com/")[![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg==)  
](https://www.intel.com/content/www/us/en/products/sku/229151/intel-arc-a770-graphics-16gb/specifications.html "https://www.intel.com/content/www/us/en/products/sku/229151/intel-arc-a770-graphics-16gb/specifications.html")[![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg==)  
](https://github.com/ggerganov/llama.cpp "https://github.com/ggerganov/llama.cpp")[![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg==)  
](https://github.com/mem0ai/mem0 "https://github.com/mem0ai/mem0")![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg==)  
## **What Is This?**  
rust-ai-kit turns an Ubuntu 24.04 machine with an Intel Arc A770 into a fully self-hosted AI workstation with persistent memory and live web search — capabilities that rival paid cloud AI services, running entirely on your hardware.  
┌─────────────────────────────────────────────────────────────┐  
│                AnythingLLM  (UI · AppImage)                  │  
│                     connects to :8090                        │  
├─────────────────────────────────────────────────────────────┤  
│         Search Proxy  :8090  (OpenAI-compatible)             │  
│   detects search intent → queries SearXNG → injects context  │  
├──────────────────┬──────────────────┬───────────────────────┤  
│  llama-server    │  Memory Server   │  SearXNG              │  
│  :8080  (SYCL)   │  :8000  (mem0)   │  :8081  (Docker)      │  
│  Intel Arc A770  │  ChromaDB+CPU    │  private web search   │  
│  16 GB VRAM      │  sentence-xfmrs  │  no tracking          │  
└──────────────────┴──────────────────┴───────────────────────┘  
   
**Port map:**  
| | | |  
|-|-|-|  
| **Port** | **Service** | **Purpose** |   
| :8080 | llama-server | LLM inference engine (direct, no search) |   
| :8090 | search_proxy | **Point AnythingLLM here** — adds web search transparently |   
| :8000 | memory_server | Persistent memory via mem0 + ChromaDB |   
| :8081 | SearXNG | Private metasearch engine |   
## **Why Intel Arc + SYCL?**  
Most local AI guides assume NVIDIA. The Arc A770's **16 GB VRAM** is exceptional value — larger than most consumer NVIDIA cards — but GPU acceleration requires Intel's SYCL/oneAPI stack rather than CUDA. This kit handles all of that, including the notoriously finicky driver setup.  
| | |  
|-|-|  
| **Feature** | **This Kit** |   
| VRAM | 16 GB (full model on-GPU) |   
| Model size supported | Up to ~13B Q4 comfortably |   
| Backend | llama.cpp SYCL (Intel-native, not a CUDA wrapper) |   
| Memory | mem0 + ChromaDB — persistent facts across sessions |   
| Web search | SearXNG — private, no-tracking metasearch |   
| Privacy | 100% local — zero telemetry, zero cloud |   
| Cost after hardware | £0/month |   
## **Repository Contents**  
rust-ai-kit/  
├── install_ai_stack.sh   # One-shot installer  
├── ai_stack_manager.sh   # Interactive management menu  
├── memory_server.py      # mem0 + ChromaDB REST API  
├── search_proxy.py       # Search-augmented OpenAI proxy  
└── validate_stack.py     # End-to-end health checker  
   
All scripts are co-located — the installer picks up the Python files automatically.  
## **Prerequisites**  
| | |  
|-|-|  
| **Requirement** | **Notes** |   
| Ubuntu 24.04 LTS | Tested on noble; fresh install recommended |   
| Intel Arc A770 | 16 GB variant; A750/A580 should work |   
| ~12 GB free disk | Model (~5 GB) + oneAPI compiler (~1.5 GB) + Python deps (~1 GB) + build |   
| Internet connection | Initial download only |   
| sudo access | Required for apt, Docker, and group changes |   
## **Quick Start**  
# 1. Clone  
git clone https://github.com/MasterMould/rust-ai-kit.git  
cd rust-ai-kit  
   
# 2. Make executable  
chmod +x install_ai_stack.sh ai_stack_manager.sh  
   
# 3. Install (30–45 min including model download)  
./install_ai_stack.sh  
   
# 4. ⚠️  LOG OUT AND BACK IN  
#    Required for render/video/docker group membership to take effect.  
   
# 5. Start the manager  
./ai_stack_manager.sh  
   
Select **2) Start AI Stack**, then open AnythingLLM and point it at http://localhost:8090/v1.  
## **Installer — Step by Step**  
install_ai_stack.sh runs seven steps. Each is **idempotent** — safe to re-run if interrupted.  
### **Step 1 — System Packages**  
Installs build tools: cmake, ninja-build, libssl-dev, libopenblas-dev, libfuse2, libwebkit2gtk, and other dependencies.  
### **Step 2 — Intel Arc GPU Drivers**  
The most involved step. The Arc A770 needs **two separate driver stacks**:  
| | | |  
|-|-|-|  
| **Stack** | **Package** | **Used by** |   
| OpenCL | intel-opencl-icd | clinfo, general compute |   
| SYCL/level-zero | libze-intel-gpu1 | llama.cpp SYCL backend |   
These come from different apt repositories and have historically conflicting dependencies on Ubuntu 24.04 Noble. The installer checks each package independently and never removes a working one.  
It also installs intel-oneapi-compiler-dpcpp-cpp (the icx/icpx SYCL compilers, ~1.5 GB) from Intel's apt repository.  
### **Step 3 — Rust Toolchain**  
Installs via rustup if not present.  
### **Step 4 — llama.cpp (SYCL, compiled from source)**  
Clones llama.cpp and compiles with Intel's compilers:  
cmake -B build -DGGML_SYCL=ON \  
      -DCMAKE_C_COMPILER=icx \  
      -DCMAKE_CXX_COMPILER=icpx \  
      -DGGML_SYCL_F16=ON  
   
This produces llama-server — a native binary with full Arc A770 acceleration. Pre-built SYCL binaries for llama.cpp do not exist; this build (~5 minutes) is unavoidable for Arc users.  
### **Step 5 — Model Download**  
Downloads **Llama 3.1 8B Instruct Q4_K_M** (~4.9 GB) as the default. The Model Manager (option 14) lets you switch to any of 10 curated models without editing files.  
### **Step 6 — Memory Server**  
Installs memory_server.py into its own Python venv with:  
- **mem0ai** — extracts and deduplicates facts from conversations  
- **ChromaDB** — SQLite-backed vector store (no Docker, no server process)  
- **sentence-transformers** — local CPU embeddings (22 MB model, fast)  
- **FastAPI + uvicorn** — REST API on port 8000  
The embedding model downloads on first start. Subsequent starts are instant.  
### **Step 7 — Search Proxy + AnythingLLM**  
Installs search_proxy.py into its own lightweight venv (httpx, fastapi, uvicorn) and downloads the AnythingLLM AppImage with a desktop shortcut.  
## **The Manager Menu**  
  ╔══════════════════════════════════════════════╗  
  ║   🤖  RUST-AI STACK MANAGER                  ║  
  ║       Ubuntu 24.04  ·  Intel Arc A770        ║  
  ╚══════════════════════════════════════════════╝  
  Engine: ● running  Memory: ● running  GPU: ● A770 visible  
  Proxy:  ● running  Search: ● running  
  Model:  Qwen2.5-14B-Instruct-Q4_K_M.gguf  
   
| | |  
|-|-|  
| **Option** | **Action** |   
| **1** | Full automated install |   
| **2** | Start stack (engine + memory + proxy + AnythingLLM) |   
| **3** | Stop stack |   
| **4** | Restart — picks up model changes automatically |   
| **5** | Status + GPU info + API health |   
| **6** | Enable auto-start on boot (systemd) |   
| **7** | Disable auto-start |   
| **8** | AnythingLLM connection guide |   
| **9** | Setup SearXNG web search |   
| **10** | View logs (engine / memory / proxy / SearXNG) |   
| **11** | Validate stack — end-to-end health check |   
| **12** | GPU benchmark — tokens/sec |   
| **13** | Uninstall |   
| **14** | Model Manager — download, switch, delete models |   
## **Connecting AnythingLLM**  
Open AnythingLLM → Settings (⚙️) → AI Providers → LLM:  
| | |  
|-|-|  
| **Field** | **Value** |   
| Provider | Generic OpenAI |   
| Base URL | http://localhost:8090/v1 ← the search proxy |   
| API Key | local |   
| Model Name | llama |   
| Token Limit | 8192 |   
**Port 8090, not 8080.** The search proxy on 8090 adds live web search transparently. Port 8080 (llama-server direct) bypasses web search entirely.  
## **Memory — How It Works**  
The memory server gives the AI persistent facts across sessions using [mem0](https://github.com/mem0ai/mem0 "https://github.com/mem0ai/mem0"):  
# Store a conversation — mem0 extracts discrete facts automatically  
curl -X POST http://localhost:8000/memorize \  
  -H "Content-Type: application/json" \  
  -d '{"messages":[  
    {"role":"user","content":"I prefer dark mode and work in Python"},  
    {"role":"assistant","content":"Noted!"}  
  ],"user_id":"me"}'  
   
# Semantic search — finds "dark mode" when you ask about "display preferences"  
curl -X POST http://localhost:8000/retrieve \  
  -H "Content-Type: application/json" \  
  -d '{"query":"display preferences","user_id":"me"}'  
   
# List all stored facts  
curl http://localhost:8000/memories?user_id=me  
   
# Interactive API docs  
open http://localhost:8000/docs  
   
mem0 uses llama-server to extract facts and sentence-transformers for embeddings. The embedding model runs entirely on CPU — the Arc A770 is not needed for memory operations.  
## **Web Search — How It Works**  
search_proxy.py sits transparently between AnythingLLM and llama-server. It scans incoming messages for search intent and, when triggered, queries SearXNG and injects results into the system prompt before forwarding to the LLM.  
**Trigger detection** (conservative — only clear intent fires):  
- "what's the latest news on..." → search triggered  
- "current price of..." → search triggered  
- "what is 2 + 2?" → no search, goes direct to LLM  
# Health check — confirms both backends are reachable  
curl http://localhost:8090/health  
   
SearXNG requires format=json enabled in its config. Manager option 9 writes ~/searxng-config/settings.yml automatically with the correct settings.  
## **Model Manager**  
Option 14 provides a full model management UI — no file editing required.  
**Curated catalogue** (all verified to fit on 16 GB VRAM):  
| | | |  
|-|-|-|  
| **Model** | **VRAM** | **Best For** |   
| Llama 3.1 8B Q4_K_M | 5.5 GB | General purpose, fast |   
| Llama 3.1 8B Q8_0 | 9.0 GB | Higher quality |   
| Qwen2.5 14B Q4_K_M | 9.5 GB | Coding, maths, reasoning |   
| DeepSeek-R1 14B Distill Q4_K_M | 9.5 GB | Chain-of-thought reasoning |   
| Mistral 7B Q4_K_M | 5.0 GB | Speed, structured output |   
| Phi-3.5 Mini Q4_K_M | 2.8 GB | Ultra-fast, simple tasks |   
| Qwen2.5 7B Q4_K_M | 5.2 GB | Coding, multilingual |   
| Llama 3.2 3B Q4_K_M | 2.5 GB | Agent sub-model |   
Active model is stored in ~/.ai_stack/.active_model. **Restart** (option 4) loads the new model automatically — no config editing.  
## **Validation**  
Option 11 runs validate_stack.py against every service. Uses stdlib only — no pip install needed:  
── 1  llama-server  :8080 ──  
  ✅  PASS  Models endpoint — found: Qwen2.5-14B-Instruct-Q4_K_M.gguf  
  ✅  PASS  Chat completion — got response in 2.0s  
   
── 2  Memory server  :8000 ──  
  ✅  PASS  Health endpoint  
  ✅  PASS  Memorize — extracted 3 memories in 25.8s  
  ✅  PASS  List memories — found 3 stored fact(s)  
  ✅  PASS  Retrieve 'display preferences' — semantic match ✓  
  ✅  PASS  Retrieve 'programming language' — semantic match ✓  
   
── 3  Search proxy  :8090 ──  
  ✅  PASS  Proxy health — llama=True searxng=True  
  ✅  PASS  Non-search query — no search triggered  
  ✅  PASS  Search-triggered query — web context injected  
python3 validate_stack.py             # all services  
python3 validate_stack.py --memory    # memory only  
python3 validate_stack.py --verbose   # show full responses  
   
Exit code 0 = all pass, 1 = failures — CI-friendly.  
## **Systemd Auto-Start**  
Option 6 creates a user-level systemd service — starts on login, no root required. Reads the active model from .active_model at start time, so switching models is automatic.  
systemctl --user status llamaedge.service  
journalctl --user -u llamaedge.service -f  
   
## **Troubleshooting**  
### **No device of requested type available** ** (SYCL crash on start)**  
Nearly always one of two causes:  
**Missing ** **libze-intel-gpu1** **:**  
dpkg -l libze-intel-gpu1 | grep '^ii'  
sudo apt-get install libze-intel-gpu1   # if missing  
   
**Not yet in ** **render** ** group** (re-login required after install):  
groups   # 'render' must appear here  
# If missing: log out, log back in, try again  
   
### **clinfo** ** shows GPU but SYCL still crashes**  
OpenCL and SYCL/level-zero are entirely separate stacks. clinfo tests OpenCL (intel-opencl-icd); llama.cpp tests level-zero (libze-intel-gpu1). Both must be installed and both require render group membership.  
### **SearXNG returns 403**  
JSON API disabled by default. Re-run manager option 9 — it writes ~/searxng-config/settings.yml with formats: [html, json] and restarts the container.  
### **Memory extraction is slow (~25s per conversation)**  
Normal — mem0 sends the conversation to llama-server for fact extraction (a full inference pass). Retrieval is ~50ms regardless of memory size.  
### **Engine starts but runs on CPU (slow throughput)**  
tail -f ~/ai_stack/logs/engine.log | grep -i "sycl\|layer\|offload"  
   
If you see CPU layers, libze-intel-gpu1 is missing or you need to re-login after the group change.  
### **Port conflicts**  
lsof -i :8080 -sTCP:LISTEN   # engine  
lsof -i :8090 -sTCP:LISTEN   # proxy  
lsof -i :8000 -sTCP:LISTEN   # memory  
pkill -f llama-server && pkill -f search_proxy.py && pkill -f memory_server.py  
   
## **Architecture Notes**  
**Why llama.cpp instead of Ollama or LlamaEdge?** Ollama has no Intel Arc SYCL support and falls back to CPU. LlamaEdge has no pre-built SYCL plugin and building one requires patching WasmEdge itself. llama.cpp's SYCL backend is Intel's own recommended inference path for Arc, actively co-maintained by Intel engineers.  
**Why mem0 instead of raw ChromaDB?** A raw vector store just stores and retrieves chunks of text. mem0 adds an extraction layer — it uses the LLM to distil conversations into discrete facts, deduplicates against existing memories, and updates stale ones. The result is a compact, high-signal memory store rather than a growing heap of raw conversation text.  
**Why a search proxy instead of agent tools?** Agent tool-use requires the LLM to decide to call a tool, generate valid JSON, and handle results — adding latency and failure modes. The proxy approach is simpler: it enriches the context before the LLM ever sees the request, and the LLM just answers naturally.  
## **Performance**  
Tested on Intel Arc A770 16 GB, Ubuntu 24.04, oneAPI 2025.3:  
| | | | |  
|-|-|-|-|  
| **Model** | **Quant** | **VRAM** | **Tok/s (est.)** |   
| Llama 3.1 8B | Q4_K_M | 5.5 GB | 25–45 |   
| Llama 3.1 8B | Q8_0 | 9.0 GB | 18–30 |   
| Qwen2.5 14B | Q4_K_M | 9.5 GB | 12–22 |   
| Mistral 7B | Q4_K_M | 5.0 GB | 28–48 |   
| Phi-3.5 Mini | Q4_K_M | 2.8 GB | 50–80 |   
Use option **12 (Benchmark)** to measure your actual throughput.  
## **File Layout After Install**  
~/  
├── ai_stack/  
│   ├── models/                         ← GGUF model files  
│   ├── llama.cpp/  
│   │   └── build/bin/llama-server      ← inference engine  
│   ├── memory_server/  
│   │   ├── memory_server.py  
│   │   ├── .venv/                      ← mem0, chromadb, sentence-transformers  
│   │   └── start_memory_server.sh  
│   ├── search_proxy/  
│   │   ├── search_proxy.py  
│   │   ├── .venv/                      ← httpx, fastapi, uvicorn  
│   │   └── start_search_proxy.sh  
│   ├── logs/  
│   │   ├── engine.log  
│   │   ├── memory.log  
│   │   └── proxy.log  
│   ├── .active_model                   ← path to current model  
│   └── .pids                           ← running process IDs  
├── Applications/  
│   └── AnythingLLM.AppImage  
├── searxng-config/  
│   └── settings.yml                    ← JSON API enabled  
└── .config/systemd/user/  
    └── llamaedge.service  
   
## **Contributing**  
Issues, PRs and tested hardware reports welcome. If you've got this working on an Arc A750, A580, or B580 — open an issue and share your config.  
When reporting bugs, please include:  
uname -a  
dpkg -l intel-opencl-icd libze-intel-gpu1 libze1 intel-oneapi-compiler-dpcpp-cpp 2>/dev/null | grep '^ii'  
clinfo -l  
groups  
python3 validate_stack.py 2>&1  
   
## **Licence**  
MIT — do whatever you like with it.  
 <div align="center">   
**Built for people who believe their AI should run on their hardware.**  
*Intel Arc A770 · llama.cpp SYCL · mem0 · SearXNG · Ubuntu 24.04 · oneAPI 2025*  
 </div>  

# 🦀 rust-ai-kit — Local AI Stack (Intel Arc A770, SYCL)

A fully local, GPU-accelerated AI stack designed for **zero cloud dependency**, **self-healing execution**, and **one-command startup**.

Built for power users who want performance, control, and reliability — without babysitting fragile scripts.

---

# 🚀 Overview

rust-ai-kit installs and runs a complete local LLM environment:

* ⚡ **llama.cpp (SYCL backend)** — full Intel Arc GPU acceleration
* 🧠 **Llama 3.1 8B (GGUF)** — high-quality local model
* 💾 **Memory server (mem0 + ChromaDB)** — long-term context
* 🌐 **Search proxy** — optional web grounding
* 🖥️ **Streamlit Web UI** — optional interface layer
* 🔁 **Self-healing launcher** — detects and fixes issues automatically

---

# ✨ Core Features

## 1. 🔥 Full GPU Acceleration (Intel Arc A770)

**Purpose:** Use your GPU instead of CPU for massive speed gains.

**How it works:**

* Uses SYCL + Level Zero backend
* Automatically detects GPU availability
* Falls back to CPU if needed

**Benefits:**

* 5–20x faster inference
* Full 8B model fits in 16GB VRAM
* No manual tuning required

---

## 2. 🤖 llama.cpp (SYCL Build)

**Purpose:** High-performance inference engine

**Features:**

* Built with Intel oneAPI (icx/icpx)
* FP16 acceleration enabled
* Optional BitNet support

**Usage:**
Automatically compiled during install.

---

## 3. 🧠 Smart Model Management

**Purpose:** Ensure a model is always available and valid

**Behavior:**

* Auto-detects `.gguf` models
* Stores active model in config
* Auto-recovers from missing/broken model

**Example:**

```bash
./launch.sh
```

---

## 4. 🔁 Self-Healing Engine Startup

**Purpose:** Start reliably without manual debugging

**Detects and fixes:**

* GPU driver issues
* Missing `libze-intel-gpu1`
* Port conflicts
* Model loading errors

**Behavior:**

* Retries up to 3 times
* Applies automatic fixes between attempts

---

## 5. 🛠️ Auto GPU Repair System

**Fixes automatically:**

* Missing `render` / `video` groups
* Missing Level Zero drivers
* Session permission issues

**Benefit:**
No reboot or manual intervention required in most cases

---

## 6. 💾 Memory Server (mem0 + ChromaDB)

**Purpose:** Persistent long-term memory for conversations

**Features:**

* Embedding-based recall
* Local vector database
* Automatic startup

**Endpoint:**

```
http://localhost:8000
```

---

## 7. 🌐 Search Proxy (Optional Web Grounding)

**Purpose:** Allow LLM to access web results

**How it works:**

* Proxies queries via SearXNG
* Injects results into LLM context

**Endpoint:**

```
http://localhost:8090
```

---

## 8. 🖥️ Streamlit Web UI (Optional)

**Purpose:** Provide a user-friendly interface

**Default:** OFF

**Enable:**

```bash
./launch.sh --webui
```

**Features:**

* Chat interface
* Stack control panel
* Logs and diagnostics

---

## 9. 🌐 Browser Auto-Launch

**Purpose:** Open UI automatically when enabled

Triggered only when WebUI is active.

---

## 10. ⚙️ Dual-Mode Launcher

Run the system in two modes:

### Headless Mode (default)

```bash
./launch.sh
```

* Engine + memory + proxy
* No UI

### WebUI Mode

```bash
./launch.sh --webui
```

* Full stack
* Opens browser

---

## 11. 🧵 Background Service Persistence

All services use:

* `nohup`
* `setsid`

**Result:**

* Survive terminal close
* Continue running in background

---

## 12. 📜 Logging System

Logs stored in:

```
~/ai_stack/logs/
```

Includes:

* engine.log
* memory.log
* proxy.log
* streamlit.log

---

## 13. 🧪 Auto-Diagnostics

If startup fails:

* Reads logs
* Identifies issue
* Applies fix
* Retries

---

## 14. 📦 Model Preservation (Uninstaller)

**Default behavior:**

* Keeps downloaded models

**Optional:**

* User can choose to delete them

---

# 🧰 Usage Guide

## Start everything

```bash
./launch.sh
```

## Start with UI

```bash
./launch.sh --webui
```

## Force headless

```bash
./launch.sh --headless
```

---

# 🔌 API Access

### LLM API

```
http://localhost:8080/v1
```

### Memory API

```
http://localhost:8000
```

### Search Proxy

```
http://localhost:8090
```

---

# 🧠 Design Philosophy

* **Zero babysitting** — fixes itself
* **Local-first** — no cloud required
* **Performance-first** — GPU by default
* **Fail-soft** — degrades gracefully
* **User-respecting** — never deletes data silently

---

# ⚡ Requirements

* Ubuntu 24.04
* Intel Arc A770 (16GB recommended)
* ~8GB free disk space

---

# 🏁 Final Thoughts

rust-ai-kit is not just an installer.

It’s a **self-healing local AI runtime** that behaves more like a service than a script.

Start it once — and it takes care of the rest.
