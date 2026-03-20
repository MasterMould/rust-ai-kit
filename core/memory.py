# core/memory.py — MemoryManager: mem0 + ChromaDB REST client (:8000)
import logging
from typing import Dict, List

import requests

from core.config import MEMORY_URL

logger = logging.getLogger(__name__)

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
