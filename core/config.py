# core/config.py — paths, ports, constants, enums, dataclasses, catalogue
# No local imports — standard library only.
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict
import logging

# PATHS & CONSTANTS — sourced directly from ai_stack_manager.sh
# ============================================================================
# INSTALL_DIR="$HOME/ai_stack"
# MODEL_DIR="$INSTALL_DIR/models"
# MODEL_CONFIG="$INSTALL_DIR/.active_model"
# LLAMACPP_BIN="$INSTALL_DIR/llama.cpp/build/bin/llama-server"
# LOG_DIR="$INSTALL_DIR/logs"
# PID_FILE="$INSTALL_DIR/.pids"
# ENGINE_PORT=8080 / SEARXNG_PORT=8081
# memory_server: :8000 / search_proxy: :8090

HOME            = Path.home()
INSTALL_DIR     = HOME / "ai_stack"
MODEL_DIR       = INSTALL_DIR / "models"
MODEL_CONFIG    = INSTALL_DIR / ".active_model"      # written by option 14
LLAMACPP_BIN    = INSTALL_DIR / "llama.cpp" / "build" / "bin" / "llama-server"
STACK_LOG_DIR   = INSTALL_DIR / "logs"
PID_FILE        = INSTALL_DIR / ".pids"
MEM_DIR         = INSTALL_DIR / "memory_server"
PROXY_DIR       = INSTALL_DIR / "search_proxy"
SYSTEMD_DIR     = HOME / ".config" / "systemd" / "user"

ENGINE_PORT  = 8080
SEARXNG_PORT = 8081
MEMORY_PORT  = 8000
PROXY_PORT   = 8090

ENGINE_URL  = f"http://localhost:{ENGINE_PORT}"
PROXY_URL   = f"http://localhost:{PROXY_PORT}"
MEMORY_URL  = f"http://localhost:{MEMORY_PORT}"
SEARXNG_URL = f"http://localhost:{SEARXNG_PORT}"

# Model identifier used by llama-server and in AnythingLLM config
LLAMA_SERVER_MODEL = "llama"
LLAMA_API_KEY      = "local"

# ── Curated model catalogue ────────────────────────────────────────────────────
# Each entry fields:
#   name        display name
#   file        local filename (.gguf)
#   url         direct download URL (HuggingFace resolve/main)
#   vram        estimated VRAM in GB at Q4_K_M (str)
#   category    one of the MODEL_CATEGORIES keys below
#   tags        list of short badge strings shown in the UI
#   desc        one-sentence plain-English description (shown to novice users)
#   notes       optional longer note (A770 tips, special flags needed, etc.)
#   new         bool — True highlights the card with a 🔥 New badge
#   recommended bool — True adds ⭐ Recommended badge
#   jinja       bool — requires --jinja flag to work correctly
#   vision      bool — multimodal model (requires mmproj, extra setup)
#
# All models verified to have a GGUF on HuggingFace as of 2025-04.
# Source: bartowski (main curator), official org repos (Qwen, DeepSeek).
# ─────────────────────────────────────────────────────────────────────────────

MODEL_CATEGORIES: Dict[str, str] = {
    "⭐ General / Chat":   "Balanced, all-purpose assistants — good starting point",
    "🧠 Reasoning":        "Chain-of-thought models that 'think before answering'",
    "💻 Coding":           "Specialised for code generation, debugging & refactoring",
    "👁️ Vision / Multimodal": "Can describe or reason about images alongside text",
    "⚡ Small / Edge":     "Under 3 GB — fast, low-VRAM, great for quick tasks",
}

MODEL_CATALOGUE: List[Dict] = [

    # ── General / Chat ─────────────────────────────────────────────────────────
    {
        "name": "Llama 3.1 8B Instruct Q4_K_M",
        "file": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
                 "/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"),
        "vram": "5.5", "category": "⭐ General / Chat",
        "tags": ["Meta", "8B", "Q4_K_M", "128k ctx"],
        "recommended": True, "new": False, "jinja": False, "vision": False,
        "desc": "Meta's flagship 8B — the best balanced starting point for most users.",
        "notes": "Excellent all-rounder with 128k context support. ~30 tok/s on A770.",
    },
    {
        "name": "Llama 3.1 8B Instruct Q8_0",
        "file": "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf",
        "url":  ("https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
                 "/resolve/main/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"),
        "vram": "9.0", "category": "⭐ General / Chat",
        "tags": ["Meta", "8B", "Q8_0", "high quality"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Near-full-precision Llama 3.1 8B — noticeably sharper than Q4.",
        "notes": "Best quality for models that fully fit in VRAM. ~22 tok/s on A770.",
    },
    {
        "name": "Qwen2.5 7B Instruct Q4_K_M",
        "file": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
                 "/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"),
        "vram": "5.2", "category": "⭐ General / Chat",
        "tags": ["Alibaba", "7B", "Q4_K_M", "multilingual"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Alibaba's Qwen2.5 — strong maths, multilingual, 128k context.",
        "notes": "Outperforms Llama on maths and structured output. Supports 29 languages.",
    },
    {
        "name": "Qwen2.5 14B Instruct Q4_K_M",
        "file": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF"
                 "/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf"),
        "vram": "9.5", "category": "⭐ General / Chat",
        "tags": ["Alibaba", "14B", "Q4_K_M", "multilingual"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Noticeably smarter than Qwen2.5 7B — fits A770 with ctx 4096.",
        "notes": "Reduce --ctx-size to 4096 on A770 to avoid OOM.",
    },
    {
        "name": "Mistral Small 3.2 24B Instruct Q4_K_M",
        "file": "mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF"
                 "/resolve/main/mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf"),
        "vram": "14.5", "category": "⭐ General / Chat",
        "tags": ["Mistral", "24B", "Q4_K_M", "🔥 New"],
        "recommended": False, "new": True, "jinja": True, "vision": False,
        "desc": "Mistral's latest 24B — near-frontier quality, just fits A770.",
        "notes": "Requires --jinja flag. Use ctx 4096 on A770. Released mid-2025.",
    },
    {
        "name": "Gemma 2 9B Instruct Q4_K_M",
        "file": "gemma-2-9b-it-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/gemma-2-9b-it-GGUF"
                 "/resolve/main/gemma-2-9b-it-Q4_K_M.gguf"),
        "vram": "6.0", "category": "⭐ General / Chat",
        "tags": ["Google", "9B", "Q4_K_M", "efficient"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Google Gemma 2 9B — excellent instruction following, very clean outputs.",
        "notes": "Google's best small model. Punches above its weight on benchmarks.",
    },
    {
        "name": "Gemma 4 31B Instruct Q4_K_M",
        "file": "google_gemma-4-31B-it-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/google_gemma-4-31B-it-GGUF"
                 "/resolve/main/google_gemma-4-31B-it-Q4_K_M.gguf"),
        "vram": "19.6", "category": "⭐ General / Chat",
        "tags": ["Google", "31B", "Q4_K_M", "🔥 New", "Jinja"],
        "recommended": False, "new": True, "jinja": True, "vision": True,
        "desc": "Google's Gemma 4 31B — frontier-class quality, multimodal-capable.",
        "notes": (
            "Requires --jinja. Slightly exceeds A770 VRAM at Q4_K_M (19.6 GB) — "
            "use IQ4_XS (17.2 GB) to fit, or allow CPU offload of a few layers."
        ),
    },

    # ── Reasoning ─────────────────────────────────────────────────────────────
    {
        "name": "DeepSeek-R1 Distill Qwen 7B Q4_K_M",
        "file": "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF"
                 "/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"),
        "vram": "5.2", "category": "🧠 Reasoning",
        "tags": ["DeepSeek", "7B", "Q4_K_M", "CoT"],
        "recommended": True, "new": False, "jinja": False, "vision": False,
        "desc": "Smallest R1 distil — chain-of-thought reasoning at 7B scale.",
        "notes": "Set temp 0.5–0.7. Best for maths, logic, and step-by-step problems.",
    },
    {
        "name": "DeepSeek-R1 Distill Qwen 14B Q4_K_M",
        "file": "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF"
                 "/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"),
        "vram": "9.5", "category": "🧠 Reasoning",
        "tags": ["DeepSeek", "14B", "Q4_K_M", "CoT"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "R1 14B distil — significantly stronger reasoning than 7B.",
        "notes": "Recommended temp 0.6. Outperforms OpenAI o1-mini on many benchmarks.",
    },
    {
        "name": "DeepSeek-R1 Distill Llama 8B Q4_K_M",
        "file": "DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF"
                 "/resolve/main/DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf"),
        "vram": "5.5", "category": "🧠 Reasoning",
        "tags": ["DeepSeek", "8B", "Q4_K_M", "CoT", "Llama base"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "R1 reasoning distilled into a Llama 3 8B backbone — fast thinker.",
        "notes": "Llama-architecture version of R1 distil. Good compatibility with llama.cpp.",
    },
    {
        "name": "DeepSeek-R1 Distill Qwen 32B Q4_K_M",
        "file": "DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF"
                 "/resolve/main/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"),
        "vram": "20.0", "category": "🧠 Reasoning",
        "tags": ["DeepSeek", "32B", "Q4_K_M", "CoT", "CPU offload"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Best open-source reasoning model under 70B — outperforms o1-mini.",
        "notes": (
            "20 GB at Q4_K_M — exceeds A770 VRAM. Offload a few layers to CPU: "
            "reduce --n-gpu-layers to ~80 and accept ~40% speed penalty. "
            "Or use IQ3_M (~14 GB) for full GPU."
        ),
    },
    {
        "name": "QwQ 32B Q4_K_M",
        "file": "Qwen_QwQ-32B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen_QwQ-32B-GGUF"
                 "/resolve/main/Qwen_QwQ-32B-Q4_K_M.gguf"),
        "vram": "20.0", "category": "🧠 Reasoning",
        "tags": ["Alibaba", "32B", "Q4_K_M", "CoT", "CPU offload"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Alibaba's QwQ — deep reasoning rival to o1, 32B parameter scale.",
        "notes": (
            "Same VRAM caveat as R1-32B. Use IQ3_M (~14 GB) to run fully on A770. "
            "Recommended temp 0.6. Excellent for maths and science problems."
        ),
    },

    # ── Coding ─────────────────────────────────────────────────────────────────
    {
        "name": "Qwen2.5 Coder 7B Instruct Q4_K_M",
        "file": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF"
                 "/resolve/main/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"),
        "vram": "5.2", "category": "💻 Coding",
        "tags": ["Alibaba", "7B", "Q4_K_M", "40+ languages"],
        "recommended": True, "new": False, "jinja": False, "vision": False,
        "desc": "State-of-the-art 7B coder — rivals GPT-4o on HumanEval.",
        "notes": "Supports 40+ languages. Best coding model that fits comfortably on A770.",
    },
    {
        "name": "Qwen2.5 Coder 14B Instruct Q4_K_M",
        "file": "Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2.5-Coder-14B-Instruct-GGUF"
                 "/resolve/main/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf"),
        "vram": "9.5", "category": "💻 Coding",
        "tags": ["Alibaba", "14B", "Q4_K_M", "40+ languages"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Larger Qwen Coder — deeper code understanding, better refactoring.",
        "notes": "Strong on complex multi-file tasks. Fits A770 with ctx 4096–8192.",
    },
    {
        "name": "Codestral 22B v0.1 Q4_K_M",
        "file": "Codestral-22B-v0.1-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Codestral-22B-v0.1-GGUF"
                 "/resolve/main/Codestral-22B-v0.1-Q4_K_M.gguf"),
        "vram": "13.5", "category": "💻 Coding",
        "tags": ["Mistral", "22B", "Q4_K_M", "80+ languages", "FIM"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Mistral's dedicated code model — 80+ languages, fill-in-the-middle.",
        "notes": (
            "Just fits A770 (13.5 GB). Excellent for tab-completion / FIM workflows. "
            "256k context (reduce to 8192 on A770)."
        ),
    },
    {
        "name": "DeepSeek Coder V2 Lite 16B Q4_K_M",
        "file": "DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-Coder-V2-Lite-Instruct-GGUF"
                 "/resolve/main/DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf"),
        "vram": "10.5", "category": "💻 Coding",
        "tags": ["DeepSeek", "16B MoE", "Q4_K_M", "300+ languages"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "DeepSeek's code specialist — supports 300+ languages, MoE efficiency.",
        "notes": "16B total, ~2.4B active per token (MoE). Very fast for its quality.",
    },

    # ── Vision / Multimodal ────────────────────────────────────────────────────
    {
        "name": "Qwen2-VL 2B Instruct Q4_K_M",
        "file": "Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF"
                 "/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf"),
        "vram": "1.5", "category": "👁️ Vision / Multimodal",
        "tags": ["Alibaba", "2B", "Q4_K_M", "image+text", "mmproj"],
        "recommended": False, "new": False, "jinja": False, "vision": True,
        "desc": "Tiny 2B vision model — describe and reason about images.",
        "notes": (
            "Requires a separate mmproj file. Use llama-qwen2vl-cli binary, not llama-server. "
            "Download mmproj-Qwen2-VL-2B-Instruct-f32.gguf from the same HF repo."
        ),
    },
    {
        "name": "Qwen2-VL 7B Instruct Q4_K_M",
        "file": "Qwen2-VL-7B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2-VL-7B-Instruct-GGUF"
                 "/resolve/main/Qwen2-VL-7B-Instruct-Q4_K_M.gguf"),
        "vram": "5.4", "category": "👁️ Vision / Multimodal",
        "tags": ["Alibaba", "7B", "Q4_K_M", "image+text", "mmproj"],
        "recommended": True, "new": False, "jinja": False, "vision": True,
        "desc": "Best local vision model at 7B — excellent image Q&A and captioning.",
        "notes": (
            "Requires mmproj-Qwen2-VL-7B-Instruct-f32.gguf from the same repo. "
            "Use llama-qwen2vl-cli. Outstanding OCR capability."
        ),
    },
    {
        "name": "Llama 3.2 11B Vision Instruct Q4_K_M",
        "file": "Llama-3.2-11B-Vision-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Llama-3.2-11B-Vision-Instruct-GGUF"
                 "/resolve/main/Llama-3.2-11B-Vision-Instruct-Q4_K_M.gguf"),
        "vram": "7.5", "category": "👁️ Vision / Multimodal",
        "tags": ["Meta", "11B", "Q4_K_M", "image+text"],
        "recommended": False, "new": False, "jinja": False, "vision": True,
        "desc": "Meta's 11B multimodal — strong visual reasoning, Llama ecosystem.",
        "notes": "Native llava-style vision support in llama.cpp. No separate mmproj needed.",
    },

    # ── Small / Edge ──────────────────────────────────────────────────────────
    {
        "name": "Llama 3.2 3B Instruct Q4_K_M",
        "file": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF"
                 "/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"),
        "vram": "2.5", "category": "⚡ Small / Edge",
        "tags": ["Meta", "3B", "Q4_K_M", "fast"],
        "recommended": True, "new": False, "jinja": False, "vision": False,
        "desc": "Meta 3B — ultra-fast, great for simple tasks or agent sub-models.",
        "notes": "Excellent tok/s on A770. Ideal as a router or lightweight assistant.",
    },
    {
        "name": "Llama 3.2 1B Instruct Q4_K_M",
        "file": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF"
                 "/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf"),
        "vram": "1.3", "category": "⚡ Small / Edge",
        "tags": ["Meta", "1B", "Q4_K_M", "instant"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Smallest usable Llama — near-instant responses, minimal VRAM.",
        "notes": "Good for always-on, classification, or routing tasks.",
    },
    {
        "name": "Phi-3.5 Mini Instruct Q4_K_M",
        "file": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF"
                 "/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf"),
        "vram": "2.8", "category": "⚡ Small / Edge",
        "tags": ["Microsoft", "3.8B", "Q4_K_M", "128k ctx"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Microsoft Phi-3.5 — surprisingly capable 3.8B with 128k context.",
        "notes": "Best-in-class for its size on reasoning benchmarks.",
    },
    {
        "name": "Gemma 2 2B Instruct Q4_K_M",
        "file": "gemma-2-2b-it-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/gemma-2-2b-it-GGUF"
                 "/resolve/main/gemma-2-2b-it-Q4_K_M.gguf"),
        "vram": "1.8", "category": "⚡ Small / Edge",
        "tags": ["Google", "2B", "Q4_K_M", "efficient"],
        "recommended": False, "new": False, "jinja": False, "vision": False,
        "desc": "Google Gemma 2 2B — punches above its weight, clean instruction following.",
        "notes": "Excellent quality/size ratio. Good as a fast chatbot or summariser.",
    },
]

# ============================================================================
# ENUMS & CONFIG
# ============================================================================

class BackendMode(Enum):
    RUSTAIKIT = "rust-ai-kit"
    OLLAMA    = "ollama"


class SecurityLevel(Enum):
    ADMIN    = "admin"
    USER     = "user"
    READONLY = "readonly"


@dataclass
class SecurityConfig:
    ALLOWED_EXTENSIONS: List[str] = field(default_factory=lambda: [
        ".py", ".txt", ".json", ".yaml", ".yml", ".md", ".pdf", ".docx"
    ])
    BLOCKED_PATTERNS: List[str] = field(default_factory=lambda: [
        r"rm\s+-rf", r"sudo\s+", r"chmod\s+777", r"mkfs", r"dd\s+",
        r":(\(\)){", r"shutdown", r"reboot", r"eval\(", r"exec\(",
        r"__import__", r"subprocess\.(?!run\()", r"os\.system",
        r"shutil\.rmtree", r"/etc/", r"/sys/", r"/proc/", r"\.\.\\/",
    ])


SECURITY_CONFIG = SecurityConfig()


# ============================================================================
# MODEL RUN CONFIGURATION
# Each field maps 1-to-1 to a llama-server / llama-cli flag.
# Descriptions are shown verbatim in the UI so novice users understand
# what each setting does without reading the llama.cpp docs.
# ============================================================================

@dataclass
class ModelRunConfig:
    # ── GPU / compute ─────────────────────────────────────────────────────────
    n_gpu_layers: int   = 99      # --n-gpu-layers / -ngl
    split_mode:   str   = "none"  # --split-mode   (none | layer | row)
    main_gpu:     int   = 0       # --main-gpu
    flash_attn:   bool  = True    # --flash-attn / -fa

    # ── Context & batching ────────────────────────────────────────────────────
    ctx_size:     int   = 8192    # --ctx-size / -c
    batch_size:   int   = 512     # --batch-size / -b
    threads:      int   = 8       # --threads / -t

    # ── Sampling ──────────────────────────────────────────────────────────────
    temperature:  float = 1.0     # --temp
    top_p:        float = 0.95    # --top-p
    min_p:        float = 0.05    # --min-p
    repeat_penalty: float = 1.0   # --repeat-penalty

    # ── Chat template ─────────────────────────────────────────────────────────
    jinja:        bool  = False   # --jinja  (needed for gemma-4 / some newer models)

    # ── Server-only extras (not in llama-cli but used by llama-server) ────────
    parallel:        int  = 1      # --parallel  (concurrent request slots)
    cont_batching:   bool = True   # --cont-batching
    mlock:           bool = False  # --mlock  (pin model RAM, prevents swapping)


# Human-readable metadata for every field — used to build the UI form.
# Each entry: (label, help_text, widget_type, extra)
#   widget_type: "int_slider" | "float_slider" | "int_input" | "checkbox" | "select"
#   extra: {"min","max","step"} for sliders/inputs; {"options"} for selects
MODEL_RUN_CONFIG_FIELDS: List[Dict] = [
    # ── GPU ──────────────────────────────────────────────────────────────────
    {
        "key": "n_gpu_layers", "group": "GPU / Compute",
        "label": "GPU layers  (--n-gpu-layers)",
        "help": (
            "How many transformer layers to offload to the GPU.  "
            "**99 = offload everything** — always use this on Arc A770.  "
            "Set to 0 to run entirely on CPU (very slow)."
        ),
        "widget": "int_slider", "min": 0, "max": 99, "step": 1,
    },
    {
        "key": "split_mode", "group": "GPU / Compute",
        "label": "Multi-GPU split mode  (--split-mode)",
        "help": (
            "How the model is split across multiple GPUs.  "
            "**none** = use a single GPU (correct for single-card setups).  "
            "'layer' splits by whole transformer layers; 'row' splits weight matrices row-wise."
        ),
        "widget": "select", "options": ["none", "layer", "row"],
    },
    {
        "key": "main_gpu", "group": "GPU / Compute",
        "label": "Primary GPU index  (--main-gpu)",
        "help": (
            "Index of the GPU that handles the compute work.  "
            "0 = first GPU (correct for most systems with a single Arc A770)."
        ),
        "widget": "int_slider", "min": 0, "max": 7, "step": 1,
    },
    {
        "key": "flash_attn", "group": "GPU / Compute",
        "label": "Flash Attention  (--flash-attn)",
        "help": (
            "Uses a memory-efficient attention algorithm.  "
            "**Recommended: ON** — reduces VRAM usage and speeds up long contexts.  "
            "Turn off only if you see SYCL errors or garbled output."
        ),
        "widget": "checkbox",
    },
    # ── Context & batching ────────────────────────────────────────────────────
    {
        "key": "ctx_size", "group": "Context & Batching",
        "label": "Context size  (--ctx-size)",
        "help": (
            "Maximum number of tokens the model can 'see' at once — "
            "your question plus the conversation history.  "
            "Larger = better memory of earlier turns but uses more VRAM.  "
            "**8192** is a safe default for Arc A770 with 8B models; "
            "reduce to 4096 for 14B+ models."
        ),
        "widget": "int_slider", "min": 512, "max": 32768, "step": 512,
    },
    {
        "key": "batch_size", "group": "Context & Batching",
        "label": "Batch size  (--batch-size)",
        "help": (
            "Number of tokens processed together when reading your prompt.  "
            "Larger values speed up the initial 'reading' phase but use more VRAM.  "
            "**512** is a balanced default; reduce to 128 if you see OOM errors."
        ),
        "widget": "int_slider", "min": 64, "max": 2048, "step": 64,
    },
    {
        "key": "threads", "group": "Context & Batching",
        "label": "CPU threads  (--threads)",
        "help": (
            "Number of CPU threads used for the parts of inference that run on the CPU "
            "(e.g. embeddings, final logits).  "
            "Set to the number of *physical* cores on your machine — "
            "hyperthreads don't help here and can hurt. Typical desktop: 8–12."
        ),
        "widget": "int_slider", "min": 1, "max": 64, "step": 1,
    },
    {
        "key": "parallel", "group": "Context & Batching",
        "label": "Parallel slots  (--parallel)  [server only]",
        "help": (
            "How many simultaneous requests the server can handle.  "
            "**1** = one user at a time (simplest, full VRAM for one response).  "
            "Increase only if multiple users share this instance; each extra slot "
            "reserves a full context-size block of VRAM."
        ),
        "widget": "int_slider", "min": 1, "max": 8, "step": 1,
    },
    {
        "key": "cont_batching", "group": "Context & Batching",
        "label": "Continuous batching  (--cont-batching)  [server only]",
        "help": (
            "Allows the server to start processing new requests before the previous "
            "one finishes, improving throughput when parallel > 1.  "
            "Leave **ON** unless you need deterministic single-request behaviour."
        ),
        "widget": "checkbox",
    },
    # ── Sampling ──────────────────────────────────────────────────────────────
    {
        "key": "temperature", "group": "Sampling",
        "label": "Temperature  (--temp)",
        "help": (
            "Controls randomness.  "
            "**0.0** = always pick the most likely word (deterministic, repetitive).  "
            "**1.0** = sample according to the model's natural probability (balanced).  "
            "**> 1.0** = more creative and unpredictable.  "
            "For factual Q&A use 0.2–0.4; for creative writing 0.8–1.2."
        ),
        "widget": "float_slider", "min": 0.0, "max": 2.0, "step": 0.05,
    },
    {
        "key": "top_p", "group": "Sampling",
        "label": "Top-P  (--top-p)",
        "help": (
            "Nucleus sampling.  At each step, only consider tokens that together "
            "make up the top P% of probability mass.  "
            "**0.95** keeps the ~95% most likely tokens and discards the tail.  "
            "Lower values make output more focused; higher values allow more variety.  "
            "Works alongside Temperature — both are applied simultaneously."
        ),
        "widget": "float_slider", "min": 0.0, "max": 1.0, "step": 0.01,
    },
    {
        "key": "min_p", "group": "Sampling",
        "label": "Min-P  (--min-p)",
        "help": (
            "Removes any token whose probability is below (min_p × top_token_probability).  "
            "**0.05** means: drop tokens that are less than 5% as likely as the best token.  "
            "This cuts out extreme long-tail tokens without affecting the main distribution.  "
            "Set to 0 to disable."
        ),
        "widget": "float_slider", "min": 0.0, "max": 0.5, "step": 0.01,
    },
    {
        "key": "repeat_penalty", "group": "Sampling",
        "label": "Repeat penalty  (--repeat-penalty)",
        "help": (
            "Penalises re-use of tokens that have already appeared in the output.  "
            "**1.0** = no penalty (model behaviour unchanged).  "
            "**1.1–1.3** discourages repetitive loops.  "
            "> 1.5 can make the model avoid necessary repetition (e.g. variable names in code)."
        ),
        "widget": "float_slider", "min": 0.5, "max": 2.0, "step": 0.05,
    },
    # ── Chat template ─────────────────────────────────────────────────────────
    {
        "key": "jinja", "group": "Chat Template",
        "label": "Jinja chat template  (--jinja)",
        "help": (
            "Uses the chat template embedded in the model's metadata (GGUF header) "
            "to format the conversation, rather than llama.cpp's built-in templates.  "
            "**Required for Gemma 4** and other newer models that ship their own template.  "
            "For older models (Llama 2/3, Mistral 0.1) leave this OFF."
        ),
        "widget": "checkbox",
    },
    # ── Memory ────────────────────────────────────────────────────────────────
    {
        "key": "mlock", "group": "Memory",
        "label": "Lock model in RAM  (--mlock)",
        "help": (
            "Pins the model's CPU-side buffers in physical RAM so the OS cannot "
            "swap them to disk.  Prevents stuttering on first inference after a period "
            "of inactivity, but requires enough free RAM to hold the model.  "
            "Leave **OFF** on systems with limited RAM."
        ),
        "widget": "checkbox",
    },
]

# ── Model configs storage dir ─────────────────────────────────────────────────
# Populated after CONFIG_DIR is defined below.
MODEL_CONFIGS_DIR: Path = None   # set at module bottom

# ── Memory client constants ──────────────────────────────────────────────────
RETRY_ATTEMPTS         = 3
RETRY_BACKOFF          = 0.5
RETRY_STATUS_CODES     = (500, 502, 503, 504)
MAX_REQUESTS_PER_MINUTE = 60
API_KEY                = LLAMA_API_KEY   # memory server uses same bearer token

# App-local dirs (separate from the stack install)
BASE_DIR         = Path(__file__).parent
PROJECT_ROOT     = BASE_DIR.parent          # llm-factory/ root (where scripts live)
APP_WORKSPACE    = BASE_DIR / "workspace"
APP_LOG_DIR      = BASE_DIR / "logs"
AUDIT_LOG        = APP_LOG_DIR / "audit.log"
CONFIG_DIR       = BASE_DIR / "config"
USERS_DB         = CONFIG_DIR / "users.json"
CHAT_HISTORY_DIR = CONFIG_DIR / "chat_history"
RAG_DOCS_DIR     = CONFIG_DIR / "rag_documents"

for _d in [APP_WORKSPACE, APP_LOG_DIR, CONFIG_DIR, CHAT_HISTORY_DIR, RAG_DOCS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# Set model configs dir now that CONFIG_DIR is defined
MODEL_CONFIGS_DIR = CONFIG_DIR / "model_configs"
MODEL_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(APP_LOG_DIR / "app.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def audit_log(user: str, action: str, details: str, success: bool = True):
    try:
        with open(AUDIT_LOG, "a") as f:
            status = "SUCCESS" if success else "FAILURE"
            f.write(f"{datetime.now().isoformat()} | {user} | {action} | {status} | {details}\n")
    except Exception as e:
        logger.error(f"audit_log: {e}")


# ============================================================================
# AUTHENTICATION — OS users via PAM, local JSON as fallback
# ============================================================================
#
# Primary: python-pam authenticates against the Linux user database.
#   Requires: pip install python-pam
#   Requires: the process user is in the 'shadow' group so PAM can verify
#             passwords.  The Makefile's `make setup` handles this.
#   Role is determined by checking the user's OS groups:
#     sudo / admin / wheel → ADMIN
#     everyone else        → USER
#
# Fallback: if PAM is unavailable (e.g. dev machine, Windows), the app
#   falls back to the local config/users.json exactly as before.
