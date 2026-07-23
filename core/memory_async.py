# ---------------------------------------------------------------------------
# Async Memory Management System with Ranking (ChromaDB REST Client)
# ---------------------------------------------------------------------------
import logging
import time
from typing import Dict, List, Optional
import httpx

from core.config import MEMORY_URL, API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = httpx.Timeout(5.0, read=15.0)
LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=20)
DEBUG_MEMORY = False


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class MemoryManagerError(Exception):
    pass


class AuthenticationError(MemoryManagerError):
    pass


class RateLimitError(MemoryManagerError):
    pass


# ---------------------------------------------------------------------------
# Ranking Engine (recency + importance)
# ---------------------------------------------------------------------------
def _score_memory(m: Dict) -> float:
    base_score = m.get("score", 1.0)

    # Recency decay (soft decay over time)
    ts = m.get("timestamp")
    if ts:
        age = time.time() - ts
        decay = 1 / (1 + age / 86400)  # ~1 day decay curve
    else:
        decay = 1.0

    # Importance weighting
    importance = m.get("importance", 1.0)

    return base_score * decay * importance


# ---------------------------------------------------------------------------
# Normalization + deduplication
# ---------------------------------------------------------------------------
def _normalize_memories(data) -> List[Dict]:
    memories = data.get("memories", data) if isinstance(data, dict) else data

    if not isinstance(memories, list):
        logger.warning("⚠️ Unexpected memory format: %s", type(memories))
        return []

    seen = set()
    filtered = []

    for m in memories:
        key = (
            m.get("id")
            or m.get("memory")
            or m.get("text")
            or str(m)
        )

        if key not in seen:
            seen.add(key)
            filtered.append(m)

    return filtered


# ---------------------------------------------------------------------------
# Async Memory Manager
# ---------------------------------------------------------------------------
class AsyncMemoryManager:

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=MEMORY_URL,
            headers={
                "X-API-Key": API_KEY,
                "User-Agent": "AsyncMemoryManager/2.0"
            },
            timeout=DEFAULT_TIMEOUT,
            limits=LIMITS
        )

    # -----------------------------------------------------------------------
    # Internal handler
    # -----------------------------------------------------------------------
    async def _handle(self, resp: httpx.Response, ctx: str):
        if DEBUG_MEMORY:
            logger.info("📡 %s → %s", ctx, resp.status_code)

        if resp.status_code == 401:
            raise AuthenticationError(f"Unauthorized: {ctx}")

        if resp.status_code == 429:
            raise RateLimitError(f"Rate limit exceeded: {ctx}")

        try:
            resp.raise_for_status()
        except Exception as e:
            logger.exception("❌ HTTP error during %s", ctx)
            raise MemoryManagerError(str(e)) from e

        try:
            return resp.json()
        except Exception as e:
            logger.exception("❌ JSON decode failed during %s", ctx)
            raise MemoryManagerError("Invalid JSON response") from e

    # -----------------------------------------------------------------------
    # STORE MEMORY
    # -----------------------------------------------------------------------
    async def memorize(
        self,
        messages: List[Dict],
        user_id: str,
        session_id: Optional[str] = None
    ) -> Dict:
        payload = {
            "messages": messages,
            "user_id": user_id,
            "session_id": session_id
        }

        try:
            if DEBUG_MEMORY:
                logger.info("📡 POST /memorize | %s", payload)

            r = await self.client.post("/memorize", json=payload)
            return await self._handle(r, "memorize")

        except Exception as e:
            logger.exception("❌ Async memorize failed")
            raise MemoryManagerError(str(e)) from e

    # -----------------------------------------------------------------------
    # RETRIEVE MEMORY (ranked)
    # -----------------------------------------------------------------------
    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        session_id: Optional[str] = None
    ) -> List[Dict]:
        payload = {
            "query": query,
            "user_id": user_id,
            "top_k": top_k,
            "session_id": session_id
        }

        try:
            if DEBUG_MEMORY:
                logger.info("📡 POST /retrieve | %s", payload)

            r = await self.client.post("/retrieve", json=payload)
            data = await self._handle(r, "retrieve")

            memories = _normalize_memories(data)

            # 🧠 Apply ranking
            memories.sort(key=_score_memory, reverse=True)

            return memories

        except Exception as e:
            logger.exception("❌ Async retrieve failed")
            raise MemoryManagerError(str(e)) from e

    # -----------------------------------------------------------------------
    # BUILD CONTEXT (LLM-ready)
    # -----------------------------------------------------------------------
    async def build_context(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        max_chars: int = 1000,
        session_id: Optional[str] = None
    ) -> str:
        try:
            memories = await self.retrieve(
                query=query,
                user_id=user_id,
                top_k=top_k,
                session_id=session_id
            )

            if not memories:
                return ""

            lines = ["## Relevant memories about this user:"]
            seen = set()
            total_chars = 0

            for m in memories:
                text = (
                    m.get("memory")
                    or m.get("text")
                    or str(m)
                ).strip()

                if text in seen:
                    continue
                seen.add(text)

                score = _score_memory(m)
                prefix = f"[{round(score, 3)}] "

                line = f"- {prefix}{text}"
                line_len = len(line) + 1

                if total_chars + line_len > max_chars:
                    break

                lines.append(line)
                total_chars += line_len

            return "\n".join(lines)

        except Exception as e:
            logger.exception("❌ Context build failed")
            raise MemoryManagerError(str(e)) from e

    # -----------------------------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------------------------
    async def close(self):
        await self.client.aclose()


# ---------------------------------------------------------------------------
# Async Test / Example
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def main():
        mm = AsyncMemoryManager()
        user_id = "test_user"

        print("=== Memorize ===")
        await mm.memorize(
            [{"role": "user", "content": "I love fast Rust systems"}],
            user_id=user_id
        )

        print("\n=== Concurrent Retrieval ===")
        queries = [
            "What do I like?",
            "What technologies do I use?",
            "What have I said before?"
        ]

        results = await asyncio.gather(*[
            mm.build_context(q, user_id) for q in queries
        ])

        for r in results:
            print(r)

        await mm.close()

    asyncio.run(main())
