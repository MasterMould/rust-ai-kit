# core/stack.py — StackManager: start/stop/restart/systemd/benchmark/SearXNG
# Mirrors ai_stack_manager.sh options 2/3/4/6/7/9/12 exactly.
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from core.config import (
    INSTALL_DIR, LLAMACPP_BIN, STACK_LOG_DIR, PID_FILE,
    MEM_DIR, PROXY_DIR, SYSTEMD_DIR,
    ENGINE_PORT, SEARXNG_PORT, MEMORY_PORT, PROXY_PORT,
    ENGINE_URL, PROXY_URL, MEMORY_URL, SEARXNG_URL,
    LLAMA_SERVER_MODEL, LLAMA_API_KEY,
    MODEL_CONFIG, HOME, ModelRunConfig,
)
from core.gpu import GPUDetector
from core.models import ModelManager, ModelConfigManager

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
    def start_engine(model_path: str,
                     gpu_layers: int = 99,
                     cfg: ModelRunConfig = None) -> Tuple[bool, str]:
        """
        Start llama-server using either a full ModelRunConfig (preferred)
        or just a model path + gpu_layers (legacy/fallback).
        """
        if not LLAMACPP_BIN.exists():
            return False, f"llama-server not found at {LLAMACPP_BIN} — run Install first"
        if not Path(model_path).exists():
            return False, f"Model not found: {model_path}"

        # Build the argument list
        if cfg is None:
            cfg = ModelRunConfig(n_gpu_layers=gpu_layers)

        server_args = ModelConfigManager.to_server_args(cfg, model_path)
        cmd = [
            str(LLAMACPP_BIN),
            *server_args,
            "--port",     str(ENGINE_PORT),
            "--host",     "0.0.0.0",
            "--api-key",  LLAMA_API_KEY,
        ]

        STACK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = open(STACK_LOG_DIR / "engine.log", "a")
        try:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                                    env=StackManager._sycl_env())
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
    def restart(model_path: str, gpu_layers: int = 99,
                cfg: ModelRunConfig = None) -> Dict[str, Tuple[bool, str]]:
        StackManager.stop_all()
        time.sleep(1)
        results: Dict[str, Tuple[bool, str]] = {}
        ok, msg = StackManager.start_engine(model_path, gpu_layers, cfg)
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
