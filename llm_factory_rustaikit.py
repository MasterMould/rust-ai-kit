"""
Secure LLM Model Factory — rust-ai-kit Edition
Integrates fully with ai_stack_manager.sh (rust-ai-kit/dev branch).
Paths, ports, model catalogue, PID tracking, GPU detection and systemd
service names are sourced directly from the shell script.

Backends:
  rust-ai-kit  — llama.cpp SYCL · mem0/ChromaDB · SearXNG (Intel Arc A770)
  Ollama       — kept for backward compatibility
Version: 4.1.0
"""

import streamlit as st
import requests
import json
import subprocess
import os
import hashlib
import time
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
from dataclasses import dataclass, field
from enum import Enum

# ============================================================================
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

import pwd as _pwd
import grp as _grp

def _os_user_exists(username: str) -> bool:
    try:
        _pwd.getpwnam(username)
        return True
    except KeyError:
        return False

def _os_user_role(username: str) -> str:
    """admin if in sudo/admin/wheel group, else user."""
    try:
        user_groups = {g.gr_name for g in _grp.getgrall() if username in g.gr_mem}
        # Also add primary group
        pw = _pwd.getpwnam(username)
        primary = _grp.getgrgid(pw.pw_gid).gr_name
        user_groups.add(primary)
        if user_groups & {"sudo", "admin", "wheel"}:
            return SecurityLevel.ADMIN.value
    except Exception:
        pass
    return SecurityLevel.USER.value

def _pam_authenticate(username: str, password: str) -> bool:
    """Try PAM authentication. Returns False (not raises) on any failure."""
    try:
        import pam  # python-pam
        p = pam.pam()
        return p.authenticate(username, password)
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"PAM error: {e}")
        return False


class AuthManager:

    # ── PAM / OS path ─────────────────────────────────────────────────────────

    @staticmethod
    def _try_pam(username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Authenticate against Linux system users via PAM."""
        if not _os_user_exists(username):
            return False, None
        if _pam_authenticate(username, password):
            role = _os_user_role(username)
            return True, role
        return False, None

    # ── Local JSON fallback ───────────────────────────────────────────────────

    @staticmethod
    def _hash(pw: str) -> str:
        return hashlib.sha256(f"{pw}llm_factory_salt_2024".encode()).hexdigest()

    @staticmethod
    def _load_local() -> Dict:
        if not USERS_DB.exists():
            u = {"admin": {
                "password": AuthManager._hash("admin123"),
                "role": SecurityLevel.ADMIN.value,
                "created": datetime.now().isoformat(),
            }}
            USERS_DB.write_text(json.dumps(u, indent=2))
            return u
        return json.loads(USERS_DB.read_text())

    @staticmethod
    def _try_local(username: str, password: str) -> Tuple[bool, Optional[str]]:
        users = AuthManager._load_local()
        if username not in users:
            return False, None
        if users[username]["password"] == AuthManager._hash(password):
            return True, users[username]["role"]
        return False, None

    # ── Public interface ──────────────────────────────────────────────────────

    @staticmethod
    def authenticate(username: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Try PAM first (system users), fall back to local users.json.
        Returns (success, role_string).
        """
        # 1. PAM — system users
        ok, role = AuthManager._try_pam(username, password)
        if ok:
            audit_log(username, "LOGIN_SUCCESS", f"method=pam role={role}")
            return True, role

        # 2. Local JSON — fallback / dev mode
        ok, role = AuthManager._try_local(username, password)
        if ok:
            audit_log(username, "LOGIN_SUCCESS", f"method=local role={role}")
            return True, role

        audit_log("SYSTEM", "LOGIN_FAILED", f"user={username}", False)
        return False, None

    @staticmethod
    def pam_available() -> bool:
        """Returns True when python-pam is installed and PAM is usable."""
        try:
            import pam  # noqa
            return True
        except ImportError:
            return False

    @staticmethod
    def add_local_user(username: str, password: str, role: str = "user") -> bool:
        """Add / update a user in the local JSON DB (admin task)."""
        try:
            users = AuthManager._load_local()
            users[username] = {
                "password": AuthManager._hash(password),
                "role": role,
                "created": datetime.now().isoformat(),
            }
            USERS_DB.write_text(json.dumps(users, indent=2))
            return True
        except Exception as e:
            logger.error(f"add_local_user: {e}")
            return False

    @staticmethod
    def list_local_users() -> List[Dict]:
        users = AuthManager._load_local()
        return [{"username": u, "role": d["role"], "created": d.get("created", "")}
                for u, d in users.items()]

    @staticmethod
    def delete_local_user(username: str) -> bool:
        try:
            users = AuthManager._load_local()
            if username in users:
                del users[username]
                USERS_DB.write_text(json.dumps(users, indent=2))
                return True
            return False
        except Exception:
            return False


# ============================================================================
# GPU DETECTION — mirrors _print_quick_status / check_status in script
# ============================================================================
class GPUDetector:
    @staticmethod
    def clinfo_visible() -> bool:
        """clinfo -l | grep -qi 'intel' — exact test used by the shell script."""
        try:
            r = subprocess.run(["clinfo", "-l"], capture_output=True, text=True, timeout=5)
            return "intel" in r.stdout.lower()
        except Exception:
            return False

    @staticmethod
    def xpu_smi_line() -> str:
        """xpu-smi discovery | grep -i 'arc|A770' | head -1"""
        try:
            r = subprocess.run(["xpu-smi", "discovery"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if re.search(r"arc|a770", line, re.IGNORECASE):
                    return line.strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def arc_freq_mhz() -> Optional[str]:
        """Read current core freq from sysfs — fallback when xpu-smi absent."""
        for p in Path("/sys/class/drm").glob("card*/device/tile0/gt0/freq0/cur_freq_mhz"):
            try:
                return p.read_text().strip()
            except Exception:
                pass
        return None

    @staticmethod
    def gpu_layers() -> int:
        """99 when GPU visible (SYCL), 0 for CPU fallback — mirrors GPU_LAYERS in script."""
        return 99 if GPUDetector.clinfo_visible() else 0


# ============================================================================
# STACK MANAGER — mirrors start/stop/restart/systemd/benchmark in the script
# ============================================================================
class StackManager:

    # ── Process status (mirrors _print_quick_status) ─────────────────────────

    @staticmethod
    def _pgrep(pattern: str) -> bool:
        try:
            return subprocess.run(["pgrep", "-f", pattern],
                                  capture_output=True, timeout=3).returncode == 0
        except Exception:
            return False

    @staticmethod
    def engine_running() -> bool:
        if StackManager._pgrep("llama-server"):
            return True
        # Also check systemd llamaedge.service
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", "llamaedge.service"],
                capture_output=True, text=True, timeout=3,
            )
            return r.stdout.strip() == "active"
        except Exception:
            return False

    @staticmethod
    def memory_running() -> bool:
        return StackManager._pgrep("memory_server.py")

    @staticmethod
    def proxy_running() -> bool:
        return StackManager._pgrep("search_proxy.py")

    @staticmethod
    def searxng_running() -> bool:
        """docker ps --filter name=searxng --filter status=running -q"""
        try:
            r = subprocess.run(
                ["docker", "ps", "--filter", "name=searxng",
                 "--filter", "status=running", "-q"],
                capture_output=True, text=True, timeout=5,
            )
            return bool(r.stdout.strip())
        except Exception:
            return False

    @staticmethod
    def full_status() -> Dict[str, bool]:
        def http(url: str, path: str = "") -> bool:
            try:
                return requests.get(url + path, timeout=2,
                                    headers={"Authorization": f"Bearer {LLAMA_API_KEY}"}
                                    ).status_code < 500
            except Exception:
                return False

        return {
            "engine":  StackManager.engine_running()  or http(ENGINE_URL,  "/v1/models"),
            "memory":  StackManager.memory_running()  or http(MEMORY_URL,  "/health"),
            "proxy":   StackManager.proxy_running()   or http(PROXY_URL,   "/health"),
            "searxng": StackManager.searxng_running() or http(SEARXNG_URL),
        }

    # ── PID file (written by the shell script's start_stack) ─────────────────

    @staticmethod
    def read_pids() -> List[int]:
        try:
            if PID_FILE.exists():
                return [int(p) for p in PID_FILE.read_text().split() if p.isdigit()]
        except Exception:
            pass
        return []

    # ── SYCL environment (_source_envs + ONEAPI_DEVICE_SELECTOR exports) ─────

    @staticmethod
    def _sycl_env() -> Dict[str, str]:
        env = os.environ.copy()
        env["ONEAPI_DEVICE_SELECTOR"] = "level_zero:0"
        env["SYCL_DEVICE_FILTER"]     = "level_zero:gpu"
        setvars = Path("/opt/intel/oneapi/setvars.sh")
        if setvars.exists():
            try:
                r = subprocess.run(
                    ["bash", "-c", f"source {setvars} --force 2>/dev/null; env"],
                    capture_output=True, text=True, timeout=15,
                )
                for line in r.stdout.splitlines():
                    if "=" in line:
                        k, _, v = line.partition("=")
                        env[k] = v
            except Exception:
                pass
        env["PATH"] = str(HOME / ".cargo" / "bin") + ":" + env.get("PATH", "")
        return env

    # ── Start engine (mirrors ENGINE_CMD array in start_stack) ───────────────

    @staticmethod
    def start_engine(model_path: str, gpu_layers: int = 99) -> Tuple[bool, str]:
        if not LLAMACPP_BIN.exists():
            return False, f"llama-server not found at {LLAMACPP_BIN} — run Install first"
        if not Path(model_path).exists():
            return False, f"Model not found: {model_path}"

        STACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = open(STACK_LOG_DIR / "engine.log", "a")
        cmd = [
            str(LLAMACPP_BIN),
            "--model",       model_path,
            "--ctx-size",    "8192",
            "--n-gpu-layers", str(gpu_layers),
            "--port",        str(ENGINE_PORT),
            "--host",        "0.0.0.0",
            "--api-key",     LLAMA_API_KEY,
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                                    env=StackManager._sycl_env())
            # Poll for API readiness — up to 90s, mirrors the shell script loop
            for _ in range(90):
                time.sleep(1)
                try:
                    r = requests.get(f"{ENGINE_URL}/v1/models", timeout=1,
                                     headers={"Authorization": f"Bearer {LLAMA_API_KEY}"})
                    if r.status_code == 200:
                        PID_FILE.write_text(str(proc.pid))
                        return True, f"Engine live (PID {proc.pid}) → {ENGINE_URL}"
                except Exception:
                    pass
            proc.kill()
            return False, "Engine did not respond after 90s — check engine.log"
        except Exception as e:
            return False, str(e)
        finally:
            log_file.close()

    @staticmethod
    def start_memory_server() -> Tuple[bool, str]:
        """Mirrors memory server launch in start_stack() including env vars."""
        launch = MEM_DIR / "start_memory_server.sh"
        if not launch.exists():
            return False, f"start_memory_server.sh not found at {launch}"
        STACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = open(STACK_LOG_DIR / "memory.log", "a")
        env = StackManager._sycl_env()
        env.update({
            "LLAMA_API_KEY":  LLAMA_API_KEY,
            "LLAMA_BASE_URL": f"{ENGINE_URL}/v1",
            "LLAMA_MODEL":    LLAMA_SERVER_MODEL,
        })
        try:
            proc = subprocess.Popen(["bash", str(launch)],
                                    stdout=log_file, stderr=log_file, env=env)
            time.sleep(4)
            if proc.poll() is None:
                return True, f"Memory server started (PID {proc.pid}) → {MEMORY_URL}"
            return False, "Memory server exited immediately — check memory.log"
        except Exception as e:
            return False, str(e)
        finally:
            log_file.close()

    @staticmethod
    def start_search_proxy() -> Tuple[bool, str]:
        """Mirrors proxy launch in start_stack()."""
        launch = PROXY_DIR / "start_search_proxy.sh"
        if not launch.exists():
            return False, f"start_search_proxy.sh not found at {launch}"
        STACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = open(STACK_LOG_DIR / "proxy.log", "a")
        try:
            proc = subprocess.Popen(["bash", str(launch)],
                                    stdout=log_file, stderr=log_file,
                                    env=StackManager._sycl_env())
            time.sleep(3)
            if proc.poll() is None:
                return True, f"Search proxy started (PID {proc.pid}) → {PROXY_URL}"
            return False, "Proxy exited immediately — check proxy.log"
        except Exception as e:
            return False, str(e)
        finally:
            log_file.close()

    # ── Stop — mirrors _stop_stack_silent() ──────────────────────────────────

    @staticmethod
    def stop_all() -> List[str]:
        """
        Exact same kill order as _stop_stack_silent():
          systemctl stop llamaedge.service
          kill PIDs from .pids file
          pkill -f search_proxy.py
          pkill -f memory_server.py
          pkill -f llama-server
        """
        results = []
        try:
            r = subprocess.run(
                ["systemctl", "--user", "stop", "llamaedge.service"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                results.append("Systemd llamaedge.service stopped")
        except Exception:
            pass

        for pid in StackManager.read_pids():
            try:
                os.kill(pid, 15)
                results.append(f"Killed PID {pid}")
            except Exception:
                pass
        PID_FILE.unlink(missing_ok=True)

        for pattern in ["search_proxy.py", "memory_server.py", "llama-server"]:
            try:
                r = subprocess.run(["pkill", "-f", pattern],
                                   capture_output=True, timeout=5)
                if r.returncode == 0:
                    results.append(f"Killed {pattern}")
            except Exception:
                pass

        return results or ["No running processes found"]

    # ── Restart — mirrors restart_stack() ────────────────────────────────────

    @staticmethod
    def restart(model_path: str, gpu_layers: int = 99) -> Dict[str, Tuple[bool, str]]:
        StackManager.stop_all()
        time.sleep(1)
        results: Dict[str, Tuple[bool, str]] = {}
        ok, msg = StackManager.start_engine(model_path, gpu_layers)
        results["engine"] = (ok, msg)
        if ok:
            results["memory"] = StackManager.start_memory_server()
            results["proxy"]  = StackManager.start_search_proxy()
        return results

    # ── Systemd — mirrors setup_systemd() / disable_systemd() ───────────────

    @staticmethod
    def enable_systemd() -> Tuple[bool, str]:
        if not LLAMACPP_BIN.exists():
            return False, "llama-server not found"
        active = ModelManager.get_active_path()
        if not active:
            return False, "No active model — set one in Model Manager first"
        SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
        STACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        unit = (
            "[Unit]\n"
            "Description=llama-server (llama.cpp SYCL — Intel Arc A770)\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Environment=\"ONEAPI_DEVICE_SELECTOR=level_zero:0\"\n"
            "Environment=\"SYCL_DEVICE_FILTER=level_zero:gpu\"\n"
            "Environment=\"PATH=/opt/intel/oneapi/compiler/latest/bin:/usr/local/bin:/usr/bin:/bin\"\n"
            f"ExecStartPre=/bin/bash -c 'source /opt/intel/oneapi/setvars.sh --force 2>/dev/null || true'\n"
            f"ExecStart=/bin/bash -c '{LLAMACPP_BIN} \\\n"
            f"    --model $(cat {MODEL_CONFIG}) \\\n"
            f"    --ctx-size 8192 \\\n"
            f"    --n-gpu-layers 99 \\\n"
            f"    --port {ENGINE_PORT} \\\n"
            f"    --host 0.0.0.0 \\\n"
            f"    --api-key {LLAMA_API_KEY}'\n"
            "Restart=on-failure\n"
            "RestartSec=10\n"
            f"StandardOutput=append:{STACK_LOG_DIR}/engine.log\n"
            f"StandardError=append:{STACK_LOG_DIR}/engine.log\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )
        (SYSTEMD_DIR / "llamaedge.service").write_text(unit)
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=10)
            subprocess.run(["systemctl", "--user", "enable", "llamaedge.service"], timeout=10)
            subprocess.run(["loginctl", "enable-linger", os.environ.get("USER", "")], timeout=10)
            return True, "Auto-start enabled — llamaedge.service will start at login/boot"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def disable_systemd() -> Tuple[bool, str]:
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "llamaedge.service"],
                timeout=10,
            )
            return True, "llamaedge.service disabled"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def systemd_enabled() -> bool:
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-enabled", "llamaedge.service"],
                capture_output=True, text=True, timeout=3,
            )
            return r.stdout.strip() == "enabled"
        except Exception:
            return False

    # ── Benchmark — mirrors benchmark() / option 12 in the script ────────────

    @staticmethod
    def benchmark() -> Dict:
        """
        Same request as the script:
          curl -X POST .../v1/completions
            -d '{"model":"llama","prompt":"The Intel Arc A770 GPU is","max_tokens":200}'
        Calculates tok/s the same way: tokens / (elapsed_ms / 1000)
        """
        try:
            start = time.time()
            r = requests.post(
                f"{ENGINE_URL}/v1/completions",
                json={"model": LLAMA_SERVER_MODEL,
                      "prompt": "The Intel Arc A770 GPU is",
                      "max_tokens": 200},
                headers={"Authorization": f"Bearer {LLAMA_API_KEY}"},
                timeout=120,
            )
            elapsed_ms = int((time.time() - start) * 1000)
            r.raise_for_status()
            data   = r.json()
            tokens = data.get("usage", {}).get("completion_tokens", 0)
            tps    = round(tokens / (elapsed_ms / 1000), 1) if elapsed_ms > 0 else 0
            return {
                "ok": True, "tokens": tokens,
                "elapsed_ms": elapsed_ms, "tps": tps,
                "text": data.get("choices", [{}])[0].get("text", ""),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── SearXNG setup — mirrors setup_web_search() / option 9 ────────────────

    @staticmethod
    def setup_searxng() -> Tuple[bool, str]:
        import shutil as _shutil
        if not _shutil.which("docker"):
            return False, "Docker not installed — run: sudo apt install docker.io"

        cfg_dir = HOME / "searxng-config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "settings.yml").write_text(
            "use_default_settings: true\nsearch:\n  formats:\n    - html\n    - json\n"
            "server:\n  limiter: false\n"
        )
        for cmd in [
            ["docker", "rm", "-f", "searxng"],
            ["docker", "run", "-d",
             "--name", "searxng", "--restart", "unless-stopped",
             "-p", f"{SEARXNG_PORT}:8080",
             "-v", f"{cfg_dir}/settings.yml:/etc/searxng/settings.yml:ro",
             "-e", f"SEARXNG_BASE_URL=http://localhost:{SEARXNG_PORT}/",
             "searxng/searxng:latest"],
        ]:
            try:
                subprocess.run(cmd, capture_output=True, timeout=60)
            except Exception as e:
                return False, str(e)

        for _ in range(30):
            time.sleep(1)
            try:
                if requests.get(SEARXNG_URL, timeout=1).status_code == 200:
                    return True, f"SearXNG live → {SEARXNG_URL}"
            except Exception:
                pass
        return False, "SearXNG still starting — check: docker logs searxng"

    # ── Log tailing — mirrors view_logs() options 1–4 ────────────────────────

    @staticmethod
    def tail_log(name: str, lines: int = 50) -> str:
        log_file = STACK_LOG_DIR / f"{name}.log"
        if not log_file.exists():
            return f"Log not found: {log_file}"
        try:
            r = subprocess.run(["tail", "-n", str(lines), str(log_file)],
                               capture_output=True, text=True, timeout=5)
            return r.stdout
        except Exception as e:
            return str(e)


# ============================================================================
# MODEL MANAGER — mirrors manage_models() + sub-menus
# ============================================================================
class ModelManager:

    @staticmethod
    def get_active_path() -> str:
        """
        Read MODEL_CONFIG, validate path exists, auto-detect first .gguf if missing.
        Mirrors _load_active_model() exactly.
        """
        if MODEL_CONFIG.exists():
            stored = MODEL_CONFIG.read_text().strip()
            if stored and Path(stored).exists():
                return stored
        found = sorted(MODEL_DIR.glob("*.gguf"))
        if found:
            path = str(found[0])
            MODEL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            MODEL_CONFIG.write_text(path)
            return path
        return ""

    @staticmethod
    def set_active(path: str) -> bool:
        """Write chosen path — mirrors: echo "$chosen" > "$MODEL_CONFIG" """
        try:
            MODEL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            MODEL_CONFIG.write_text(path)
            return True
        except Exception as e:
            logger.error(f"set_active: {e}")
            return False

    @staticmethod
    def list_installed() -> List[Dict]:
        if not MODEL_DIR.exists():
            return []
        active = ModelManager.get_active_path()
        out = []
        for f in sorted(MODEL_DIR.glob("*.gguf")):
            out.append({
                "name":      f.name,
                "path":      str(f),
                "size_gb":   round(f.stat().st_size / 1e9, 2),
                "size_human": f"{f.stat().st_size / 1e9:.1f} GB",
                "is_active": str(f) == active,
            })
        return out

    @staticmethod
    def download(filename: str, url: str) -> Tuple[bool, str]:
        """wget to MODEL_DIR — mirrors _download_model_menu()."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        dest = MODEL_DIR / filename
        if dest.exists():
            return True, f"Already downloaded: {filename}"
        try:
            r = subprocess.run(["wget", "-O", str(dest), url], timeout=3600)
            if r.returncode == 0 and dest.exists():
                return True, f"Downloaded: {filename} ({dest.stat().st_size / 1e9:.1f} GB)"
            dest.unlink(missing_ok=True)
            return False, "wget failed or was interrupted"
        except Exception as e:
            dest.unlink(missing_ok=True)
            return False, str(e)

    @staticmethod
    def delete(filename: str) -> Tuple[bool, str]:
        """Unlink and auto-select next model — mirrors _remove_model_menu()."""
        path = MODEL_DIR / filename
        if not path.exists():
            return False, "File not found"
        active = ModelManager.get_active_path()
        path.unlink()
        if active and Path(active).name == filename:
            MODEL_CONFIG.unlink(missing_ok=True)
            ModelManager.get_active_path()  # auto-select next
        return True, f"Deleted: {filename}"


# ============================================================================
# MEMORY — mem0 + ChromaDB REST API (:8000)
# ============================================================================
class MemoryManager:

    @staticmethod
    def memorize(messages: List[Dict], user_id: str) -> Dict:
        try:
            r = requests.post(f"{MEMORY_URL}/memorize",
                              json={"messages": messages, "user_id": user_id},
                              timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def retrieve(query: str, user_id: str, top_k: int = 5) -> List[Dict]:
        try:
            r = requests.post(f"{MEMORY_URL}/retrieve",
                              json={"query": query, "user_id": user_id, "top_k": top_k},
                              timeout=15)
            r.raise_for_status()
            data = r.json()
            return data.get("memories", data) if isinstance(data, dict) else data
        except Exception:
            return []

    @staticmethod
    def list_all(user_id: str) -> List[Dict]:
        try:
            r = requests.get(f"{MEMORY_URL}/memories",
                             params={"user_id": user_id}, timeout=10)
            r.raise_for_status()
            data = r.json()
            return data.get("memories", data) if isinstance(data, dict) else data
        except Exception:
            return []

    @staticmethod
    def delete(memory_id: str, user_id: str) -> bool:
        try:
            r = requests.delete(f"{MEMORY_URL}/memories/{memory_id}",
                                params={"user_id": user_id}, timeout=10)
            return r.status_code in (200, 204)
        except Exception:
            return False

    @staticmethod
    def build_context(query: str, user_id: str) -> str:
        mems = MemoryManager.retrieve(query, user_id)
        if not mems:
            return ""
        lines = ["## Relevant memories about this user:"]
        for m in mems:
            lines.append(f"- {m.get('memory', m.get('text', str(m)))}")
        return "\n".join(lines)


# ============================================================================
# INFERENCE — OpenAI-compatible /v1/chat/completions
# ============================================================================
class InferenceClient:
    @staticmethod
    def _hdr() -> Dict:
        return {"Authorization": f"Bearer {LLAMA_API_KEY}",
                "Content-Type": "application/json"}

    @staticmethod
    def chat(messages: List[Dict], use_proxy: bool = True,
             temperature: float = 0.7, max_tokens: int = 2048) -> Dict:
        """
        use_proxy=True  → try :8090 (search_proxy.py — adds SearXNG when intent detected)
                          auto-falls back to :8080 if proxy is not running
        use_proxy=False → :8080 direct (no search overhead)

        Sets st.session_state._last_endpoint so the UI can show which port was used.
        """
        payload = {
            "model": LLAMA_SERVER_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
            "stream": False,
        }
        headers = InferenceClient._hdr()

        endpoints: List[Tuple[str, str]] = []
        if use_proxy:
            endpoints.append((PROXY_URL, "proxy :8090"))
        endpoints.append((ENGINE_URL, "engine :8080"))

        last_err = ""
        for base, label in endpoints:
            try:
                r = requests.post(
                    f"{base}/v1/chat/completions",
                    json=payload, headers=headers, timeout=120,
                )
                r.raise_for_status()
                # Record which endpoint actually answered
                try:
                    st.session_state._last_endpoint = label
                    if use_proxy and label != "proxy :8090":
                        st.session_state._proxy_fallback = True
                    else:
                        st.session_state._proxy_fallback = False
                except Exception:
                    pass
                return r.json()
            except requests.exceptions.ConnectionError as e:
                last_err = str(e)
                logger.warning(f"InferenceClient: {label} unreachable, trying next")
                continue
            except Exception as e:
                last_err = str(e)
                break   # non-connection errors (4xx/5xx) — don't retry

        return {"error": f"All endpoints failed. Last error: {last_err}"}

    @staticmethod
    def reply(response: Dict) -> str:
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return response.get("error", "No response received.")


# ============================================================================
# OLLAMA — backward-compat fallback
# ============================================================================
class OllamaClient:
    BASE = "http://localhost:11434"

    @staticmethod
    def running() -> bool:
        try:
            return requests.get(f"{OllamaClient.BASE}/api/tags", timeout=2).status_code == 200
        except Exception:
            return False

    @staticmethod
    def models() -> List[str]:
        try:
            r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
            return [l.split()[0] for l in r.stdout.strip().split("\n")[1:] if l.strip()]
        except Exception:
            return []

    @staticmethod
    def chat(messages: List[Dict], model: str, temperature: float = 0.7) -> str:
        try:
            r = requests.post(
                f"{OllamaClient.BASE}/api/chat",
                json={"model": model, "messages": messages, "stream": False,
                      "options": {"temperature": temperature}},
                timeout=120,
            )
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "No response")
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def pull(name: str) -> Tuple[bool, str]:
        try:
            r = subprocess.run(["ollama", "pull", name], timeout=600,
                               capture_output=True, text=True)
            return r.returncode == 0, r.stdout or r.stderr
        except Exception as e:
            return False, str(e)


# ============================================================================
# SECURITY / RAG
# ============================================================================
class SecurityValidator:
    @staticmethod
    def validate_code(code: str) -> Tuple[bool, List[str]]:
        issues = []
        for pat in SECURITY_CONFIG.BLOCKED_PATTERNS:
            if re.search(pat, code, re.IGNORECASE):
                issues.append(f"Blocked pattern: {pat}")
        for imp in ["os", "subprocess", "shutil", "sys", "ctypes", "pickle"]:
            if re.search(rf"\bimport\s+{imp}\b|\bfrom\s+{imp}\s+import", code):
                issues.append(f"Dangerous import: {imp}")
        return len(issues) == 0, issues

    @staticmethod
    def sanitize(text: str, max_len: int = 10000) -> str:
        return "".join(c for c in text[:max_len] if c.isprintable() or c in "\n\t")


class RAGManager:
    @staticmethod
    def process(file_path: Path, file_name: str) -> Tuple[bool, str]:
        try:
            if file_path.suffix.lower() == ".pdf":
                try:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        content = "".join(p.extract_text() for p in PyPDF2.PdfReader(f).pages)
                except ImportError:
                    content = "PyPDF2 not installed: pip install PyPDF2"
            else:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            out  = RAG_DOCS_DIR / f"{file_name}.txt"
            meta = RAG_DOCS_DIR / f"{file_name}.meta.json"
            out.write_text(content, encoding="utf-8")
            meta.write_text(json.dumps({
                "filename": file_name, "uploaded": datetime.now().isoformat(),
                "size": len(content), "path": str(out),
            }, indent=2))
            return True, f"{len(content):,} chars"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def list_docs() -> List[Dict]:
        return sorted(
            [json.loads(m.read_text()) for m in RAG_DOCS_DIR.glob("*.meta.json")],
            key=lambda x: x.get("uploaded", ""), reverse=True,
        )

    @staticmethod
    def search(query: str, max_results: int = 3) -> List[Dict]:
        q, results = query.lower(), []
        for doc in RAG_DOCS_DIR.glob("*.txt"):
            try:
                content = doc.read_text(encoding="utf-8")
                score   = content.lower().count(q)
                if score:
                    idx  = content.lower().find(q)
                    s, e = max(0, idx - 250), min(len(content), idx + 250)
                    ctx  = ("..." if s else "") + content[s:e] + ("..." if e < len(content) else "")
                    results.append({"filename": doc.stem, "score": score, "context": ctx})
            except Exception:
                pass
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    @staticmethod
    def delete(filename: str):
        for sfx in (".txt", ".meta.json"):
            p = RAG_DOCS_DIR / f"{filename}{sfx}"
            if p.exists():
                p.unlink()


# ============================================================================
# STREAMLIT CONFIG
# ============================================================================
st.set_page_config(
    page_title="🦀 LLM Factory · rust-ai-kit",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown("""
<style>
.chat-message      { padding:1rem; border-radius:.5rem; margin-bottom:1rem; }
.user-message      { background:#e3f2fd; border-left:4px solid #2196f3; }
.assistant-message { background:#f5f5f5; border-left:4px solid #4caf50; }
.badge  { display:inline-block; border-radius:.3rem; padding:.15rem .45rem;
          font-size:.72rem; margin-right:.3rem; }
.b-mem  { background:#fff3e0; border:1px solid #ff9800; }
.b-rag  { background:#e8f5e9; border:1px solid #43a047; }
.b-web  { background:#e3f2fd; border:1px solid #1976d2; }
.ok     { color:#2e7d32; font-weight:bold; }
.err    { color:#c62828; font-weight:bold; }
.mono   { font-family:monospace; font-size:.85rem; }
.chat-header { font-weight:bold; margin-bottom:.35rem; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# AUTH
# ============================================================================
def check_auth() -> bool:
    return st.session_state.get("authenticated", False)


def show_login():
    st.title("🦀 LLM Factory — rust-ai-kit Edition")
    _, col, _ = st.columns([1, 2, 1])
    with col:
        if AuthManager.pam_available():
            st.info("🐧 **Sign in with your Linux system account**")
        else:
            st.info("🔑 **Local accounts active** — default: `admin` / `admin123`")
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("🔓 Login"):
                ok, role = AuthManager.authenticate(u, p)
                if ok:
                    st.session_state.update({
                        "authenticated": True, "username": u,
                        "role": role, "login_time": datetime.now(),
                    })
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials")


def init_session():
    defs = {
        "chat_history":  [],
        "system_prompt": "You are a helpful AI assistant.",
        "rag_enabled":   False,
        "mem_enabled":   True,
        "search_enabled": True,
        "backend":       BackendMode.RUSTAIKIT.value,
        "ollama_model":  "",
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================================
# MAIN
# ============================================================================
def main():
    if not check_auth():
        show_login()
        return
    init_session()

    with st.sidebar:
        st.title("🦀 LLM Factory")
        st.caption(f"**{st.session_state.username}** · {st.session_state.role.upper()}")
        if st.button("🚪 Logout"):
            audit_log(st.session_state.username, "LOGOUT", "")
            for k in list(st.session_state):
                del st.session_state[k]
            st.rerun()

        st.divider()
        backend = st.radio("Engine", [BackendMode.RUSTAIKIT.value, BackendMode.OLLAMA.value],
                           index=0 if st.session_state.backend == BackendMode.RUSTAIKIT.value else 1,
                           horizontal=True)
        st.session_state.backend = backend

        st.divider()
        st.subheader("🤖 Active Model")

        if backend == BackendMode.RUSTAIKIT.value:
            active_path = ModelManager.get_active_path()
            active_name = Path(active_path).name if active_path else "none"
            if active_path:
                st.success(f"**{active_name}**")
            else:
                st.error("No model — use Model Manager")
            st.session_state.search_enabled = st.toggle(
                "🌐 Web search (:8090)",
                value=st.session_state.search_enabled,
                help="Routes via search_proxy.py which auto-injects SearXNG results",
            )
            st.session_state.mem_enabled = st.toggle(
                "🧠 Persistent memory",
                value=st.session_state.mem_enabled,
                help="Retrieves mem0 facts and prepends them to the system prompt",
            )
        else:
            if OllamaClient.running():
                st.success("✅ Ollama running")
                models = OllamaClient.models()
                st.session_state.ollama_model = (
                    st.selectbox("Model", models) if models
                    else st.text_input("Model:", "llama3")
                )
            else:
                st.error("❌ Ollama offline")
                st.code("ollama serve")
                st.session_state.ollama_model = st.text_input("Model:", "llama3")

        st.divider()
        st.subheader("⚙️ Generation")
        temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
        max_tokens  = st.slider("Max tokens",  256, 4096, 2048, 128)

        st.session_state.rag_enabled = st.checkbox(
            "📄 Local RAG", value=st.session_state.rag_enabled,
            help="Keyword search over uploaded documents"
        )
        if st.session_state.rag_enabled:
            st.caption(f"📚 {len(RAGManager.list_docs())} docs")

        with st.expander("System prompt"):
            sp = st.text_area("", value=st.session_state.system_prompt, height=100)
            if st.button("Update"):
                st.session_state.system_prompt = sp
                st.success("Updated")

        st.divider()
        st.subheader("💾 Conversation")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()
        with c2:
            if st.button("💾 Save", use_container_width=True):
                if st.session_state.chat_history:
                    d = CHAT_HISTORY_DIR / st.session_state.username
                    d.mkdir(exist_ok=True)
                    fn = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    (d / fn).write_text(json.dumps(st.session_state.chat_history, indent=2))
                    st.success("Saved")

    tabs = st.tabs([
        "💬 Chat", "🦀 Stack", "🧠 Memory", "🤖 Models",
        "📚 RAG", "💻 Code", "📊 Benchmark", "🛡️ Security", "👥 Users", "📜 Logs",
    ])
    with tabs[0]: tab_chat(temperature, max_tokens)
    with tabs[1]: tab_stack()
    with tabs[2]: tab_memory()
    with tabs[3]: tab_models()
    with tabs[4]: tab_rag()
    with tabs[5]: tab_code(temperature)
    with tabs[6]: tab_benchmark()
    with tabs[7]: tab_security()
    with tabs[8]: tab_users()
    with tabs[9]: tab_logs()


# ============================================================================
# TAB: CHAT
# ============================================================================
def _send(user_input: str, temperature: float, max_tokens: int):
    username  = st.session_state.username
    sanitized = SecurityValidator.sanitize(user_input)
    is_rak    = st.session_state.backend == BackendMode.RUSTAIKIT.value
    rag_ctx   = mem_ctx = ""
    web_used  = False

    if st.session_state.rag_enabled:
        docs = RAGManager.search(sanitized)
        if docs:
            rag_ctx = "\n\n".join(f"[Doc: {d['filename']}]\n{d['context']}" for d in docs)

    if is_rak and st.session_state.mem_enabled:
        try:
            mem_ctx = MemoryManager.build_context(sanitized, username)
        except Exception:
            pass

    sys_parts = [st.session_state.system_prompt]
    if mem_ctx:
        sys_parts.append(mem_ctx)
    if rag_ctx:
        sys_parts.append(f"## Context from local documents:\n{rag_ctx}")

    messages = [{"role": "system", "content": "\n\n".join(sys_parts)}]
    for m in st.session_state.chat_history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": sanitized})

    # ── Pre-flight: check engine is reachable before touching history ──────────
    if is_rak and not StackManager.engine_running():
        st.session_state._engine_down = True
        return   # tab_chat will show the actionable banner; nothing added to history

    st.session_state._engine_down = False

    with st.spinner("🤔 Thinking…"):
        if is_rak:
            use_proxy = st.session_state.search_enabled
            resp  = InferenceClient.chat(messages, use_proxy, temperature, max_tokens)
            # If both endpoints failed, surface as a UI error — not in chat history
            if "error" in resp:
                st.session_state._last_error = resp["error"]
                st.session_state._engine_down = True
                return
            reply = InferenceClient.reply(resp)
            web_used = use_proxy
        else:
            if not OllamaClient.running():
                st.session_state._engine_down = True
                return
            reply = OllamaClient.chat(messages, st.session_state.ollama_model, temperature)

    # Only write to history on success
    st.session_state.chat_history.append({"role": "user", "content": sanitized})
    st.session_state.chat_history.append({
        "role": "assistant", "content": reply,
        "rag": bool(rag_ctx), "mem": bool(mem_ctx), "web": web_used,
    })

    if is_rak and st.session_state.mem_enabled and StackManager.memory_running():
        try:
            MemoryManager.memorize(
                [{"role": "user", "content": sanitized},
                 {"role": "assistant", "content": reply}],
                username,
            )
        except Exception:
            pass

    # Clear any previous error state on success
    st.session_state._engine_down = False
    st.session_state.pop("_last_error", None)
    audit_log(username, "CHAT", f"backend={st.session_state.backend}")


def tab_chat(temperature: float, max_tokens: int):
    st.header("💬 Chat")

    is_rak = st.session_state.backend == BackendMode.RUSTAIKIT.value
    active_name = (Path(ModelManager.get_active_path()).name
                   if is_rak and ModelManager.get_active_path()
                   else st.session_state.ollama_model or "—")

    # ── Engine health banner ──────────────────────────────────────────────────
    if is_rak:
        engine_ok = StackManager.engine_running()
        proxy_ok  = StackManager.proxy_running()
    else:
        engine_ok = OllamaClient.running()
        proxy_ok  = True  # not applicable

    if not engine_ok:
        st.error(
            "🔴 **Engine offline** — llama-server is not running on "
            f"`localhost:{ENGINE_PORT}`."
        )
        active = ModelManager.get_active_path() if is_rak else ""
        if active:
            c1, c2 = st.columns([2, 5])
            with c1:
                if st.button("▶️ Start engine now", type="primary"):
                    gpu_layers = GPUDetector.gpu_layers()
                    with st.spinner(
                        f"Starting llama-server  (GPU layers={gpu_layers}, up to 90s)…"
                    ):
                        ok, msg = StackManager.start_engine(active, gpu_layers)
                    if ok:
                        st.success(msg)
                        st.session_state._engine_down = False
                        st.session_state.pop("_last_error", None)
                        st.rerun()
                    else:
                        st.error(msg)
                        st.caption(
                            f"Check: `tail -f {STACK_LOG_DIR}/engine.log`  \n"
                            "Common cause: not in `render` group — log out and back in."
                        )
            with c2:
                st.caption(
                    f"Model: `{Path(active).name}`  \n"
                    "Or start the full stack from the **🦀 Stack** tab."
                )
        else:
            st.warning("No model selected. Go to the **🤖 Models** tab to download one.")
        # Show any diagnostic from the last failed attempt
        if st.session_state.get("_last_error"):
            with st.expander("🔍 Connection error detail"):
                st.code(st.session_state["_last_error"])
        # Still render history (read-only) but block input below
        chat_input_disabled = True
    else:
        chat_input_disabled = False
        st.session_state._engine_down = False

    # ── Status strip ──────────────────────────────────────────────────────────
    c = st.columns(5)
    c[0].info(f"**Model:** {active_name[:30]}")
    c[1].info(f"**Backend:** {st.session_state.backend}")
    c[2].info(f"**Temp:** {temperature}")
    c[3].info("🌐 Search ON" if st.session_state.get("search_enabled") and is_rak else "Search OFF")
    c[4].info("🧠 Memory ON" if st.session_state.get("mem_enabled") and is_rak else "Memory OFF")

    # Warn if proxy was down and we fell back to direct engine
    if not chat_input_disabled and is_rak and not proxy_ok and st.session_state.get("search_enabled"):
        st.warning(
            "⚠️ Search proxy (:8090) is offline — sending directly to engine (:8080). "
            "Web search is **disabled**. Start the proxy from the **🦀 Stack** tab."
        )
    elif st.session_state.get("_proxy_fallback"):
        st.warning(
            "⚠️ Last message used direct engine (:8080) — proxy was unreachable. "
            "Web search was disabled for that reply."
        )

    if not st.session_state.chat_history:
        st.markdown(
            "<div style='text-align:center;padding:2rem;color:#888'>"
            "<h3>👋 Start a conversation</h3></div>",
            unsafe_allow_html=True,
        )
    else:
        for msg in st.session_state.chat_history:
            role = msg["role"]
            with st.chat_message(role, avatar="👤" if role == "user" else "🤖"):
                # Render content as markdown — handles code blocks, lists, newlines etc.
                st.markdown(msg["content"])
                # Show augmentation badges below assistant messages
                if role == "assistant":
                    tags = []
                    if msg.get("mem"): tags.append("🧠 mem0")
                    if msg.get("rag"): tags.append("📄 RAG")
                    if msg.get("web"): tags.append("🌐 web")
                    if tags:
                        st.caption("  ·  ".join(tags))

    # st.chat_input stays pinned to the bottom of the page and handles
    # Enter-to-send natively — no rerun key conflicts.
    placeholder = "Type your message…" if not chat_input_disabled else "⚠️ Engine offline — start it above first"
    user_input = st.chat_input(placeholder, disabled=chat_input_disabled)
    if user_input and user_input.strip() and not chat_input_disabled:
        _send(user_input, temperature, max_tokens)
        st.rerun()

    st.divider()
    if st.button("📄 Export as Markdown") and st.session_state.chat_history:
        md = "# Chat Export\n\n"
        for m in st.session_state.chat_history:
            md += f"## {'User' if m['role']=='user' else 'Assistant'}\n\n{m['content']}\n\n"
        st.download_button("⬇️ Download", md,
                           file_name=f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")


# ── Per-service inline controls ───────────────────────────────────────────────

def _svc(label: str, ok: bool, url: str, note: str = "",
         start_fn=None, log_name: str = ""):
    """
    Render one service row.
    When offline AND start_fn is provided, show an inline ▶️ Start button
    and a collapsible log tail for instant diagnosis.
    """
    icon  = "🟢" if ok else "🔴"
    state_html = "<span class='ok'>running</span>" if ok else "<span class='err'>offline</span>"
    st.markdown(
        f"{icon} **{label}** &ensp; <span class='mono'>{url}</span>"
        f" &ensp; {state_html}"
        + (f" &ensp; <small>{note}</small>" if note else ""),
        unsafe_allow_html=True,
    )
    if not ok and start_fn is not None:
        col_btn, col_log = st.columns([1, 4])
        with col_btn:
            if st.button(f"▶️ Start {label}", key=f"start_{label}"):
                with st.spinner(f"Starting {label}…"):
                    ok2, msg = start_fn()
                if ok2:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with col_log:
            if log_name and STACK_LOG_DIR.exists():
                log_path = STACK_LOG_DIR / f"{log_name}.log"
                if log_path.exists():
                    tail = ""
                    try:
                        r = subprocess.run(
                            ["tail", "-n", "8", str(log_path)],
                            capture_output=True, text=True, timeout=3,
                        )
                        tail = r.stdout.strip()
                    except Exception:
                        pass
                    if tail:
                        with st.expander(f"📋 Last lines of {log_name}.log"):
                            st.code(tail, language="bash")
                else:
                    st.caption(f"No log yet: `{log_path}`")


def tab_stack():
    st.header("🦀 rust-ai-kit Stack")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.info("Switch to **rust-ai-kit** in the sidebar to use this tab.")
        return

    if st.button("🔄 Refresh status"):
        st.rerun()

    status = StackManager.full_status()
    st.subheader("Service health")

    active = ModelManager.get_active_path()
    gpu_layers = GPUDetector.gpu_layers()

    _svc("llama-server (SYCL)", status["engine"], f":{ENGINE_PORT}",
         "Direct inference — no web search",
         start_fn=(lambda: StackManager.start_engine(active, gpu_layers)) if active else None,
         log_name="engine")
    _svc("search proxy", status["proxy"], f":{PROXY_PORT}",
         "Point AnythingLLM here — adds SearXNG transparently",
         start_fn=StackManager.start_search_proxy,
         log_name="proxy")
    _svc("memory server", status["memory"], f":{MEMORY_PORT}",
         "mem0 + ChromaDB persistent facts",
         start_fn=StackManager.start_memory_server,
         log_name="memory")
    _svc("SearXNG", status["searxng"], f":{SEARXNG_PORT}",
         "Private Docker metasearch",
         start_fn=StackManager.setup_searxng,
         log_name="")

    if all(status.values()):
        st.success("✅ All four services online")
    else:
        st.error(f"⚠️ Offline: {', '.join(k for k, v in status.items() if not v)}")

    st.divider()

    # GPU (mirrors check_status)
    st.subheader("🖥️ Intel Arc A770")
    gpu_ok = GPUDetector.clinfo_visible()
    if gpu_ok:
        st.success("✅ GPU visible (level-zero / OpenCL) — SYCL will use GPU")
        xpu = GPUDetector.xpu_smi_line()
        if xpu:
            st.code(xpu)
        freq = GPUDetector.arc_freq_mhz()
        if freq:
            st.caption(f"Core freq: {freq} MHz")
    else:
        st.error("❌ GPU not visible — `render` group membership required")
        st.code("groups   # 'render' must appear\n# If missing: log out + back in\n"
                "dpkg -l libze-intel-gpu1  # must be installed")

    st.divider()

    # Active model
    st.subheader("🤖 Active model")
    active = ModelManager.get_active_path()
    if active:
        st.code(active)
        p = Path(active)
        if p.exists():
            st.caption(f"✅ File present · {p.stat().st_size / 1e9:.2f} GB")
    else:
        st.warning("No model — use Model Manager tab or option 14 in `ai_stack_manager.sh`")

    st.divider()

    # Stack controls (options 2 / 3 / 4)
    st.subheader("⚙️ Stack controls")
    st.caption(
        "Replicates options **2 (Start) / 3 (Stop) / 4 (Restart)** from "
        "`ai_stack_manager.sh` — same SYCL env, same process patterns."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶️ Start engine"):
            if not active:
                st.error("No model set")
            else:
                with st.spinner(f"Starting… GPU layers={gpu_layers} (up to 90s)"):
                    ok, msg = StackManager.start_engine(active, gpu_layers)
                st.success(msg) if ok else st.error(msg)
                audit_log(st.session_state.username, "START_ENGINE", msg, ok)

    with c2:
        if st.button("⏹ Stop all"):
            msgs = StackManager.stop_all()
            for m in msgs:
                st.success(m)
            audit_log(st.session_state.username, "STOP_ALL", "; ".join(msgs))

    with c3:
        if st.button("🔄 Restart"):
            if not active:
                st.error("No model set")
            else:
                with st.spinner("Restarting…"):
                    results = StackManager.restart(active, gpu_layers)
                for svc, (ok, msg) in results.items():
                    (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {svc}: {msg}")
                audit_log(st.session_state.username, "RESTART", str(results))

    st.divider()

    # Systemd (options 6 / 7)
    st.subheader("🕒 Auto-start on boot")
    st.caption(
        "Writes `~/.config/systemd/user/llamaedge.service` — identical unit to "
        "option 6. Reads `~/.ai_stack/.active_model` at each boot."
    )
    enabled = StackManager.systemd_enabled()
    st.info(f"llamaedge.service: **{'enabled' if enabled else 'disabled'}**")
    c6, c7 = st.columns(2)
    with c6:
        if st.button("✅ Enable auto-start"):
            ok, msg = StackManager.enable_systemd()
            st.success(msg) if ok else st.error(msg)
    with c7:
        if st.button("❌ Disable auto-start"):
            ok, msg = StackManager.disable_systemd()
            st.success(msg) if ok else st.error(msg)

    st.divider()

    # SearXNG setup (option 9)
    st.subheader("🔍 SearXNG setup")
    st.caption(
        "Writes `~/searxng-config/settings.yml` with `format: json` enabled "
        "and launches the Docker container — same as option 9."
    )
    if st.button("🚀 Setup / restart SearXNG"):
        with st.spinner("Setting up SearXNG Docker container…"):
            ok, msg = StackManager.setup_searxng()
        st.success(msg) if ok else st.error(msg)
        audit_log(st.session_state.username, "SETUP_SEARXNG", msg, ok)

    # Proxy health detail
    if status["proxy"]:
        st.divider()
        st.subheader("🌐 Search proxy /health")
        try:
            r = requests.get(f"{PROXY_URL}/health", timeout=3)
            st.json(r.json())
        except Exception as e:
            st.error(str(e))

    # AnythingLLM connection guide (option 8)
    with st.expander("📋 AnythingLLM connection guide (option 8)"):
        st.markdown(f"""
**LLM Provider setup:**
1. Open AnythingLLM → ⚙️ Settings → AI Providers → LLM
2. Provider: **Generic OpenAI**
3. Base URL: `http://localhost:{PROXY_PORT}/v1` ← search proxy **(not {ENGINE_PORT})**
4. API Key: `{LLAMA_API_KEY}`
5. Model Name: `{LLAMA_SERVER_MODEL}`
6. Token Limit: `8192`

> Port **{PROXY_PORT}** adds live web search. Port **{ENGINE_PORT}** is llama-server direct — no search.

**Memory API (mem0):**
```bash
# Store a conversation
curl -X POST http://localhost:{MEMORY_PORT}/memorize \\
  -H "Content-Type: application/json" \\
  -d '{{"messages":[{{"role":"user","content":"I prefer dark mode"}}],"user_id":"me"}}'

# Semantic search
curl -X POST http://localhost:{MEMORY_PORT}/retrieve \\
  -H "Content-Type: application/json" \\
  -d '{{"query":"display preferences","user_id":"me"}}'

# List all
curl http://localhost:{MEMORY_PORT}/memories?user_id=me

# Swagger UI
open http://localhost:{MEMORY_PORT}/docs
```
""")


# ============================================================================
# TAB: MEMORY
# ============================================================================
def tab_memory():
    st.header("🧠 Persistent Memory  (mem0 + ChromaDB)")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.info("Memory requires the rust-ai-kit backend.")
        return
    if not StackManager.memory_running():
        st.error("Memory server offline — start it from the Stack tab.")
        return

    username = st.session_state.username
    mtabs    = st.tabs(["📋 All Memories", "🔍 Semantic Search", "➕ Manual Store"])

    with mtabs[0]:
        if st.button("🔄 Refresh"):
            st.rerun()
        mems = MemoryManager.list_all(username)
        if not mems:
            st.info("No memories yet. Chat with Memory enabled to build them up.")
        else:
            st.success(f"{len(mems)} fact(s) stored for **{username}**")
            for i, m in enumerate(mems):
                text   = m.get("memory", m.get("text", str(m)))
                mem_id = m.get("id", m.get("memory_id", ""))
                with st.expander(f"💡 {text[:90]}{'…' if len(text) > 90 else ''}"):
                    st.write(text)
                    if m.get("created_at"):
                        st.caption(f"Stored: {m['created_at']}")
                    if mem_id and st.button("🗑️ Delete", key=f"delmem_{i}"):
                        if MemoryManager.delete(mem_id, username):
                            st.success("Deleted")
                            st.rerun()

    with mtabs[1]:
        st.caption(
            "Uses sentence-transformers CPU embeddings (~50ms retrieval). "
            "Finds semantically similar facts even if wording differs."
        )
        q     = st.text_input("Search query:")
        top_k = st.slider("Top results", 1, 20, 5)
        if st.button("🔍 Search", type="primary") and q:
            with st.spinner("Searching…"):
                results = MemoryManager.retrieve(q, username, top_k)
            if results:
                for r in results:
                    text  = r.get("memory", r.get("text", str(r)))
                    score = r.get("score", r.get("similarity", ""))
                    prefix = f"**Score:** `{score:.4f}`  \n" if isinstance(score, float) else ""
                    st.markdown(prefix + text)
                    st.divider()
            else:
                st.warning("No matching memories found.")

    with mtabs[2]:
        st.caption(
            "mem0 sends the conversation to llama-server for fact extraction "
            "(one full inference pass, ~25s), then stores distilled facts in ChromaDB."
        )
        u_msg = st.text_area("User turn:", height=80)
        a_msg = st.text_area("Assistant turn:", height=80)
        if st.button("🧠 Store", type="primary") and u_msg.strip():
            with st.spinner("Extracting facts (~25s)…"):
                res = MemoryManager.memorize(
                    [{"role": "user",      "content": u_msg},
                     {"role": "assistant", "content": a_msg or "Noted."}],
                    username,
                )
            if "error" in res:
                st.error(res["error"])
            else:
                st.success("✅ Memories stored")
                st.json(res)


# ============================================================================
# TAB: MODEL MANAGER  (mirrors manage_models + sub-menus)
# ============================================================================
def tab_models():
    st.header("🤖 Model Manager")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.subheader("Ollama Models")
        for m in OllamaClient.models():
            c1, c2 = st.columns([5, 1])
            c1.write(m)
        st.divider()
        custom = st.text_input("Pull model:")
        if st.button("📥 Pull") and custom:
            with st.spinner(f"Pulling {custom}…"):
                ok, msg = OllamaClient.pull(custom)
            st.success(msg) if ok else st.error(msg)
        return

    active_name = Path(ModelManager.get_active_path()).name if ModelManager.get_active_path() else "none"
    st.info(f"🟢 **Active:** `{active_name}`  &ensp; config: `{MODEL_CONFIG}`")

    mtabs = st.tabs(["📋 Installed", "⬇️ Download", "🔄 Switch", "🗑️ Remove"])

    with mtabs[0]:  # mirrors installed listing in manage_models()
        installed = ModelManager.list_installed()
        if not installed:
            st.warning(f"No .gguf files in `{MODEL_DIR}`")
            st.info("Use the Download tab or `ai_stack_manager.sh` option 14.")
        else:
            st.success(f"{len(installed)} model(s) in `{MODEL_DIR}`")
            for m in installed:
                marker = "🟢 **" + m["name"] + "**" if m["is_active"] else "⚪ " + m["name"]
                c1, c2 = st.columns([6, 1])
                c1.markdown(marker)
                c2.caption(m["size_human"])

    with mtabs[1]:  # mirrors _download_model_menu()
        st.caption(
            f"All models verified on Intel Arc A770 (16 GB).  \n"
            f"Destination: `{MODEL_DIR}`  \n"
            f"Source: HuggingFace (bartowski GGUF collection)"
        )
        idx = st.selectbox(
            "Select model:",
            range(len(MODEL_CATALOGUE)),
            format_func=lambda i: (
                f"{MODEL_CATALOGUE[i]['name']}  —  {MODEL_CATALOGUE[i]['vram']} GB VRAM"
            ),
        )
        m    = MODEL_CATALOGUE[idx]
        dest = MODEL_DIR / m["file"]
        st.markdown(
            f"**File:** `{m['file']}`  \n"
            f"**VRAM:** {m['vram']} GB  \n"
            f"**Description:** {m['desc']}"
        )
        if dest.exists():
            st.success(f"Already downloaded ({dest.stat().st_size / 1e9:.1f} GB)")
            if st.button("Set as active"):
                ModelManager.set_active(str(dest))
                st.success(f"Active → `{m['file']}`")
                st.warning("⚠️ Restart the engine (Stack tab) to load it.")
        else:
            if st.button("⬇️ Download", type="primary"):
                with st.spinner(f"Downloading {m['file']}… (may take several minutes)"):
                    ok, msg = ModelManager.download(m["file"], m["url"])
                if ok:
                    st.success(msg)
                    audit_log(st.session_state.username, "MODEL_DOWNLOAD", m["file"], True)
                    if st.button("Set as active now"):
                        ModelManager.set_active(str(MODEL_DIR / m["file"]))
                        st.rerun()
                else:
                    st.error(msg)

    with mtabs[2]:  # mirrors _switch_model_menu()
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No installed models.")
        else:
            opts = {m["name"]: m["path"] for m in installed}
            choice = st.selectbox("Switch to:", list(opts.keys()))
            if st.button("✅ Set active"):
                ModelManager.set_active(opts[choice])
                st.success(f"Active model → `{choice}`")
                st.warning(
                    "⚠️ Restart the engine (Stack tab) to load the new model — "
                    "same as `ai_stack_manager.sh` option 4."
                )
                audit_log(st.session_state.username, "MODEL_SWITCH", choice)

    with mtabs[3]:  # mirrors _remove_model_menu()
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No models to remove.")
        else:
            opts  = {f"{m['name']} ({m['size_human']})": m["name"] for m in installed}
            label = st.selectbox("Remove:", list(opts.keys()))
            fname = opts[label]
            is_active = any(m["is_active"] and m["name"] == fname for m in installed)
            if is_active:
                st.warning("⚠️ This is the active model. Removing will auto-select the next one.")
            if st.button("🗑️ Confirm delete", type="primary"):
                ok, msg = ModelManager.delete(fname)
                st.success(msg) if ok else st.error(msg)
                audit_log(st.session_state.username, "MODEL_DELETE", fname, ok)
                if ok:
                    st.rerun()


# ============================================================================
# TAB: RAG
# ============================================================================
def tab_rag():
    st.header("📚 Local RAG Documents")
    rtabs = st.tabs(["📤 Upload", "📋 Manage", "🔍 Search Test"])

    with rtabs[0]:
        files = st.file_uploader("Upload documents", accept_multiple_files=True,
                                 type=["txt", "md", "pdf", "json", "yaml"])
        if files and st.button("Process all", type="primary"):
            bar = st.progress(0)
            for i, f in enumerate(files):
                tmp = APP_WORKSPACE / f.name
                tmp.write_bytes(f.getbuffer())
                ok, msg = RAGManager.process(tmp, f.name)
                tmp.unlink(missing_ok=True)
                (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {f.name}: {msg}")
                audit_log(st.session_state.username, "RAG_UPLOAD", f.name, ok)
                bar.progress((i + 1) / len(files))

    with rtabs[1]:
        docs = RAGManager.list_docs()
        if not docs:
            st.info("No documents yet.")
        for doc in docs:
            with st.expander(f"📄 {doc['filename']}"):
                c1, c2 = st.columns([4, 1])
                c1.markdown(
                    f"Uploaded: {doc.get('uploaded','?')}  \n"
                    f"Size: {doc.get('size',0):,} chars"
                )
                with c2:
                    if st.button("🗑️ Delete", key=f"deldoc_{doc['filename']}"):
                        RAGManager.delete(doc["filename"])
                        st.rerun()

    with rtabs[2]:
        q = st.text_input("Test query:")
        if st.button("🔍 Search") and q:
            for r in RAGManager.search(q, max_results=5):
                st.markdown(f"**{r['filename']}** — score {r['score']}")
                st.info(r["context"])
                st.divider()
            if not RAGManager.search(q, max_results=1):
                st.warning("No matches found.")


# ============================================================================
# TAB: CODE GENERATION
# ============================================================================
def tab_code(temperature: float):
    st.header("💻 Code Generation")
    c_in, c_out = st.columns(2)

    with c_in:
        prompt = st.text_area("What code do you need?", height=200)
        lang   = st.selectbox("Language",
                              ["Python", "Rust", "Bash", "JavaScript", "Go", "C++", "TypeScript"])
        if st.button("🚀 Generate", type="primary") and prompt:
            msgs = [
                {"role": "system",
                 "content": "You are an expert programmer. Reply with only the code, no prose."},
                {"role": "user",
                 "content": f"Write clean, well-commented {lang} code for:\n{prompt}"},
            ]
            with st.spinner("Generating…"):
                if st.session_state.backend == BackendMode.RUSTAIKIT.value:
                    # Always use direct engine for code gen (no search overhead)
                    resp  = InferenceClient.chat(msgs, use_proxy=False,
                                                 temperature=temperature)
                    reply = InferenceClient.reply(resp)
                else:
                    reply = OllamaClient.chat(msgs, st.session_state.ollama_model,
                                              temperature)
            st.session_state.generated_code = reply
            st.session_state.code_lang      = lang
            st.rerun()

    with c_out:
        if "generated_code" in st.session_state:
            code = st.session_state.generated_code
            lang = st.session_state.get("code_lang", "python")
            st.code(code, language=lang.lower())
            ok, issues = SecurityValidator.validate_code(code)
            if ok:
                st.success("✅ Security scan: pass")
            else:
                st.error(f"🚨 {len(issues)} issue(s):")
                for iss in issues:
                    st.warning(iss)
            fname = st.text_input("Filename:", "output.py")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Save to workspace"):
                    (APP_WORKSPACE / fname).write_text(code)
                    st.success(f"Saved: {APP_WORKSPACE / fname}")
            with c2:
                st.download_button("📥 Download", code, file_name=fname)


# ============================================================================
# TAB: BENCHMARK  (mirrors benchmark() / option 12)
# ============================================================================
def tab_benchmark():
    st.header("📊 GPU Benchmark")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.info("Benchmark targets the rust-ai-kit llama-server.")
        return

    st.info(
        "Replicates **option 12** from `ai_stack_manager.sh`:  \n"
        f"POSTs a 200-token completion to `:{ENGINE_PORT}/v1/completions` "
        "and calculates tokens/second.  \n"
        "**Expected on Intel Arc A770 (SYCL):** ~25–45 tok/s for 8B Q4_K_M"
    )

    if not StackManager.engine_running():
        st.error("Engine offline — start it from the Stack tab first.")
        return

    if st.button("🚀 Run Benchmark", type="primary"):
        with st.spinner("Running 200-token completion…"):
            result = StackManager.benchmark()

        if not result.get("ok"):
            st.error(f"Benchmark failed: {result.get('error', 'unknown error')}")
            st.caption(f"Check: `tail -f {STACK_LOG_DIR}/engine.log`")
            return

        tps = result["tps"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Tokens generated", result["tokens"])
        c2.metric("Elapsed",          f"{result['elapsed_ms']:,} ms")
        c3.metric("Throughput",        f"{tps} tok/s")

        if isinstance(tps, (int, float)) and tps > 0:
            if tps < 10:
                st.error(
                    "⚠️ Below 10 tok/s — SYCL GPU acceleration likely NOT active.  \n"
                    "Check the Stack tab: GPU must be visible and engine started with "
                    f"`--n-gpu-layers 99`.  \n"
                    f"Verify: `clinfo -l | grep -i intel`"
                )
            elif tps < 25:
                st.warning("Throughput below expected range — partial CPU offload likely.")
            else:
                st.success(f"✅ {tps} tok/s — GPU acceleration confirmed")

        if result.get("text"):
            with st.expander("Generated text"):
                st.write(result["text"])

        audit_log(st.session_state.username, "BENCHMARK",
                  f"tps={tps} tokens={result['tokens']}", True)


# ============================================================================
# TAB: SECURITY
# ============================================================================
def tab_security():
    st.header("🛡️ Security")
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Code Scanner")
        code = st.text_area("Paste code to scan:", height=200)
        if st.button("🔍 Scan") and code:
            ok, issues = SecurityValidator.validate_code(code)
            if ok:
                st.success("✅ No issues detected")
            else:
                st.error(f"🚨 {len(issues)} issue(s):")
                for iss in issues:
                    st.warning(iss)

    with c2:
        st.subheader("Audit statistics")
        if AUDIT_LOG.exists():
            lines    = AUDIT_LOG.read_text().splitlines()
            total    = len(lines)
            failures = sum(1 for l in lines if "FAILURE" in l)
            st.metric("Total actions", total)
            st.metric("Failures",      failures)
            if total:
                st.metric("Success rate", f"{(total - failures) / total * 100:.1f}%")
        else:
            st.info("No audit log yet.")


# ============================================================================
# TAB: USERS  (admin only)
# ============================================================================
def tab_users():
    st.header("👥 User Management")

    is_admin = st.session_state.get("role") == SecurityLevel.ADMIN.value
    if not is_admin:
        st.warning("🔒 Admin access required.")
        return

    # PAM status
    pam_ok = AuthManager.pam_available()
    if pam_ok:
        st.success(
            "✅ **PAM active** — users log in with their Linux system credentials.  \n"
            "Any user account on this machine can log in. Role is determined by "
            "OS group membership (`sudo`/`admin` → admin, everyone else → user)."
        )
    else:
        st.warning(
            "⚠️ **PAM unavailable** — falling back to local `config/users.json`.  \n"
            "Install `python-pam` and ensure the process user is in the `shadow` group "
            "to enable OS-level authentication.  \n"
            "```bash\npip install python-pam\nsudo usermod -aG shadow $USER\n"
            "# then log out and back in\n```"
        )

    st.divider()

    # Show OS users who could log in (those with login shells)
    if pam_ok:
        st.subheader("🐧 OS users with login shells")
        st.caption("These accounts can authenticate directly with their system password.")
        try:
            shell_users = []
            for pw in _pwd.getpwall():
                if (pw.pw_shell not in ("/bin/false", "/usr/sbin/nologin", "")
                        and pw.pw_uid >= 1000):
                    groups = [g.gr_name for g in _grp.getgrall() if pw.pw_name in g.gr_mem]
                    role = "admin" if set(groups) & {"sudo", "admin", "wheel"} else "user"
                    shell_users.append({
                        "Username": pw.pw_name,
                        "UID": pw.pw_uid,
                        "Role in app": role,
                        "OS Groups": ", ".join(sorted(groups)[:6]),
                    })
            if shell_users:
                import pandas as pd
                st.dataframe(pd.DataFrame(shell_users), use_container_width=True)
            else:
                st.info("No regular user accounts found.")
        except Exception as e:
            st.error(f"Could not enumerate users: {e}")

    st.divider()

    # Local JSON users (fallback accounts)
    st.subheader("📋 Local fallback accounts  (`config/users.json`)")
    st.caption(
        "These are used when PAM is unavailable, or as override accounts "
        "(e.g. a service account that has no OS login)."
    )

    local_users = AuthManager.list_local_users()
    if local_users:
        for u in local_users:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(f"**{u['username']}**")
            c2.write(u["role"])
            c3.caption(u["created"][:10] if u["created"] else "")
            with c4:
                if u["username"] != st.session_state.username:  # can't delete yourself
                    if st.button("🗑️", key=f"delusr_{u['username']}"):
                        if AuthManager.delete_local_user(u["username"]):
                            st.success(f"Deleted {u['username']}")
                            st.rerun()
    else:
        st.info("No local accounts.")

    st.divider()

    # Add local user
    st.subheader("➕ Add local fallback account")
    with st.form("add_user_form"):
        new_u = st.text_input("Username")
        new_p = st.text_input("Password", type="password")
        new_p2 = st.text_input("Confirm password", type="password")
        new_r = st.selectbox("Role", [SecurityLevel.USER.value, SecurityLevel.ADMIN.value])
        if st.form_submit_button("Add user"):
            if not new_u or not new_p:
                st.error("Username and password required.")
            elif new_p != new_p2:
                st.error("Passwords do not match.")
            elif len(new_p) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                if AuthManager.add_local_user(new_u, new_p, new_r):
                    st.success(f"Added local account: {new_u} ({new_r})")
                    audit_log(st.session_state.username, "USER_ADDED", new_u)
                    st.rerun()
                else:
                    st.error("Failed to save user.")


# ============================================================================
# TAB: LOGS  (mirrors view_logs() options 1–4)
# ============================================================================
def tab_logs():
    st.header("📜 Logs")
    ltabs = st.tabs(["Audit (app)", "engine.log", "memory.log", "proxy.log"])

    with ltabs[0]:
        if AUDIT_LOG.exists():
            n = st.slider("Lines", 10, 200, 50, key="audit_n")
            lines = AUDIT_LOG.read_text().splitlines()
            st.text_area("", "\n".join(reversed(lines[-n:])), height=400)
        else:
            st.info("No audit log yet.")

    for i, name in enumerate(["engine", "memory", "proxy"]):
        with ltabs[i + 1]:
            n = st.slider("Lines", 20, 300, 80, key=f"logn_{name}")
            if st.session_state.backend == BackendMode.RUSTAIKIT.value:
                out = StackManager.tail_log(name, n)
                st.text_area("", out, height=400)
                st.caption(f"`{STACK_LOG_DIR}/{name}.log`")
            else:
                st.info("Stack logs only available in rust-ai-kit mode.")


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    main()
