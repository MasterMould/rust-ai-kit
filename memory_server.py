#!/usr/bin/env python3
"""
memory_server.py — Local persistent memory service for rust-ai-kit
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Architecture:
  mem0ai   — extracts facts from conversations, deduplicates memories
  ChromaDB — SQLite-backed vector store (no Docker, no server process)
  sentence-transformers — local CPU embeddings (all-MiniLM-L6-v2, 22 MB)
  FastAPI  — REST API on port 8000

Endpoints:
  GET  /health              — liveness check
  POST /memorize            — store conversation, extract facts
  POST /retrieve            — semantic search over stored memories
  GET  /memories            — list all stored memories
  DELETE /memories          — clear all memories (with confirmation)

Environment variables (all optional):
  LLAMA_BASE_URL  — llama-server API base  (default: http://localhost:8080/v1)
  LLAMA_API_KEY   — llama-server API key   (default: local)
  LLAMA_MODEL     — model name             (default: llama)
  MEMORY_DB_PATH  — where to store memory DB (default: ~/.ai_stack/memory)
  MEMORY_PORT     — port to listen on      (default: 8000)
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Any

# ── FastAPI ────────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# ── mem0 ───────────────────────────────────────────────────────────
from mem0 import Memory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("memory_server")

# ── Configuration from environment ────────────────────────────────
LLAMA_BASE_URL = os.environ.get("LLAMA_BASE_URL", "http://localhost:8080/v1")
LLAMA_API_KEY  = os.environ.get("LLAMA_API_KEY",  "local")
LLAMA_MODEL    = os.environ.get("LLAMA_MODEL",    "llama")
MEMORY_DB_PATH = os.environ.get("MEMORY_DB_PATH",
                                 str(Path.home() / ".ai_stack" / "memory"))
MEMORY_PORT    = int(os.environ.get("MEMORY_PORT", "8000"))

Path(MEMORY_DB_PATH).mkdir(parents=True, exist_ok=True)

# ── mem0 configuration ─────────────────────────────────────────────
# Uses our local llama-server for fact extraction and
# sentence-transformers for embeddings (CPU, no GPU required).
MEM0_CONFIG = {
    "llm": {
        "provider": "openai",
        "config": {
            "model":           LLAMA_MODEL,
            "openai_base_url": LLAMA_BASE_URL,
            "api_key":         LLAMA_API_KEY,
            "temperature":     0.1,
            "max_tokens":      1000,
        },
    },
    "embedder": {
        # sentence-transformers runs entirely on CPU — no GPU, no API key
        "provider": "huggingface",
        "config": {
            "model": "multi-qa-MiniLM-L6-cos-v1",  # 22 MB, fast, good retrieval
        },
    },
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "ai_stack_memories",
            "path":             MEMORY_DB_PATH,
        },
    },
    "history_db_path": str(Path(MEMORY_DB_PATH) / "history.db"),
}

log.info("Initialising mem0 memory layer…")
log.info(f"  LLM:        {LLAMA_BASE_URL}  model={LLAMA_MODEL}")
log.info(f"  Embedder:   sentence-transformers (CPU)")
log.info(f"  Vector DB:  ChromaDB @ {MEMORY_DB_PATH}")

try:
    memory = Memory.from_config(MEM0_CONFIG)
    log.info("mem0 initialised ✓")
except Exception as exc:
    log.error(f"Failed to initialise mem0: {exc}")
    log.error("Is llama-server running? Try: curl http://localhost:8080/v1/models")
    sys.exit(1)

# ── Request / response models ──────────────────────────────────────

class Message(BaseModel):
    role: str                  # "user" or "assistant"
    content: str

class MemorizeRequest(BaseModel):
    messages:  list[Message]
    user_id:   str = "default"
    agent_id:  str | None = None

class MemorizeResponse(BaseModel):
    memories_added: int
    results:        list[dict[str, Any]]

class RetrieveRequest(BaseModel):
    query:    str
    user_id:  str = "default"
    agent_id: str | None = None
    limit:    int = 5

class RetrieveResponse(BaseModel):
    query:    str
    memories: list[dict[str, Any]]

# ── FastAPI app ────────────────────────────────────────────────────

app = FastAPI(
    title="rust-ai-kit Memory Service",
    description="Persistent memory layer — mem0 + ChromaDB + sentence-transformers",
    version="1.0.0",
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "memory_server",
            "llm": LLAMA_BASE_URL, "model": LLAMA_MODEL}


@app.post("/memorize", response_model=MemorizeResponse)
async def memorize(req: MemorizeRequest):
    """
    Extract and store facts from a conversation.
    Pass the full message list (user + assistant turns).
    mem0 automatically deduplicates against existing memories.

    Example:
        POST /memorize
        {
          "messages": [
            {"role": "user",      "content": "I prefer dark mode everywhere."},
            {"role": "assistant", "content": "Noted! I'll remember that."}
          ],
          "user_id": "first"
        }
    """
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        kwargs: dict[str, Any] = {"user_id": req.user_id}
        if req.agent_id:
            kwargs["agent_id"] = req.agent_id
        result = memory.add(msgs, **kwargs)
        # mem0 returns {"results": [...]} or a list depending on version
        if isinstance(result, dict):
            results = result.get("results", [])
        else:
            results = result if isinstance(result, list) else []
        return MemorizeResponse(memories_added=len(results), results=results)
    except Exception as exc:
        log.error(f"memorize error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest):
    """
    Semantic search over stored memories.

    Example:
        POST /retrieve
        {"query": "what are my display preferences?", "user_id": "first"}
    """
    try:
        kwargs: dict[str, Any] = {"user_id": req.user_id}
        if req.agent_id:
            kwargs["agent_id"] = req.agent_id
        results = memory.search(req.query, limit=req.limit, **kwargs)
        memories = results.get("results", results) if isinstance(results, dict) else results
        return RetrieveResponse(query=req.query,
                                memories=memories if isinstance(memories, list) else [])
    except Exception as exc:
        log.error(f"retrieve error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/memories")
async def list_memories(user_id: str = "default"):
    """List all stored memories for a user."""
    try:
        results = memory.get_all(user_id=user_id)
        memories = results.get("results", results) if isinstance(results, dict) else results
        return {"user_id": user_id,
                "count": len(memories),
                "memories": memories}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/memories")
async def clear_memories(user_id: str = "default", confirm: bool = False):
    """Delete all memories for a user. Pass ?confirm=true to proceed."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Pass ?confirm=true to delete all memories for this user."
        )
    try:
        memory.delete_all(user_id=user_id)
        return {"status": "cleared", "user_id": user_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(f"Starting memory server on port {MEMORY_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=MEMORY_PORT, log_level="warning")
