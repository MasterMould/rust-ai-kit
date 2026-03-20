# core/config.py — paths, ports, constants, enums, dataclasses, catalogue
# No local imports — standard library only.
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

# ── Curated model catalogue — exact match with _model_catalogue() in the script ──
# Fields: name, file, url, vram (str GB), desc
MODEL_CATALOGUE: List[Dict] = [
    {
        "name": "Llama 3.1 8B Instruct Q4_K_M",
        "file": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
                 "/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"),
        "vram": "5.5", "desc": "Best all-rounder. Fast, instruction-tuned, fits with room to spare.",
    },
    {
        "name": "Llama 3.1 8B Instruct Q8_0",
        "file": "Meta-Llama-3.1-8B-Instruct-Q8_0.gguf",
        "url":  ("https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"
                 "/resolve/main/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf"),
        "vram": "9.0", "desc": "Higher quality than Q4, still fits. Slower throughput.",
    },
    {
        "name": "Mistral 7B Instruct v0.3 Q4_K_M",
        "file": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF"
                 "/resolve/main/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"),
        "vram": "5.0", "desc": "Excellent for coding and structured tasks. Very fast.",
    },
    {
        "name": "Mistral 7B Instruct v0.3 Q8_0",
        "file": "Mistral-7B-Instruct-v0.3-Q8_0.gguf",
        "url":  ("https://huggingface.co/bartowski/Mistral-7B-Instruct-v0.3-GGUF"
                 "/resolve/main/Mistral-7B-Instruct-v0.3-Q8_0.gguf"),
        "vram": "8.5", "desc": "Near-lossless quality Mistral. Great for long-form writing.",
    },
    {
        "name": "Phi-3.5 Mini Instruct Q4_K_M",
        "file": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF"
                 "/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf"),
        "vram": "2.8", "desc": "Tiny but surprisingly capable. Fastest option.",
    },
    {
        "name": "Qwen2.5 7B Instruct Q4_K_M",
        "file": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
                 "/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"),
        "vram": "5.2", "desc": "Excellent at coding, maths, multilingual.",
    },
    {
        "name": "Qwen2.5 14B Instruct Q4_K_M",
        "file": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Qwen2.5-14B-Instruct-GGUF"
                 "/resolve/main/Qwen2.5-14B-Instruct-Q4_K_M.gguf"),
        "vram": "9.5", "desc": "Noticeably smarter than 7B. Fits A770 with ctx 4096.",
    },
    {
        "name": "Llama 3.2 3B Instruct Q4_K_M",
        "file": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF"
                 "/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"),
        "vram": "2.5", "desc": "Ultra-fast. Use as an agent sub-model or for simple tasks.",
    },
    {
        "name": "DeepSeek-R1 7B Distill Q4_K_M",
        "file": "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF"
                 "/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"),
        "vram": "5.2", "desc": "Reasoning/chain-of-thought distil. Great for logic problems.",
    },
    {
        "name": "DeepSeek-R1 14B Distill Q4_K_M",
        "file": "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        "url":  ("https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF"
                 "/resolve/main/DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf"),
        "vram": "9.5", "desc": "Best reasoning model that fits. Think before answering.",
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

# App-local dirs (separate from the stack install)
BASE_DIR         = Path(__file__).parent
APP_WORKSPACE    = BASE_DIR / "workspace"
APP_LOG_DIR      = BASE_DIR / "logs"
AUDIT_LOG        = APP_LOG_DIR / "audit.log"
CONFIG_DIR       = BASE_DIR / "config"
USERS_DB         = CONFIG_DIR / "users.json"
CHAT_HISTORY_DIR = CONFIG_DIR / "chat_history"
RAG_DOCS_DIR     = CONFIG_DIR / "rag_documents"

for _d in [APP_WORKSPACE, APP_LOG_DIR, CONFIG_DIR, CHAT_HISTORY_DIR, RAG_DOCS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

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
