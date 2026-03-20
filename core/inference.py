# core/inference.py — InferenceClient (proxy→engine fallback) + OllamaClient
# InferenceClient.chat() writes st.session_state metadata for UI feedback;
# the writes are wrapped in try/except so this module is safe to import
# without Streamlit running (e.g. unit tests, CLI tools).
import logging
import subprocess
from typing import Dict, List, Tuple

import requests

from core.config import (
    ENGINE_URL, PROXY_URL,
    LLAMA_SERVER_MODEL, LLAMA_API_KEY,
)

logger = logging.getLogger(__name__)

# Streamlit is optional — if absent, session-state writes silently no-op
try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore[assignment]

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
