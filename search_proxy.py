#!/usr/bin/env python3
"""
search_proxy.py — Search-augmented OpenAI-compatible proxy for rust-ai-kit
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Architecture:
                        ┌──────────────┐
  AnythingLLM ──:8090──▶│ search_proxy │──▶ llama-server :8080
  any client             │              │──▶ SearXNG      :8081
                        └──────────────┘

The proxy is itself OpenAI-compatible — point any client at :8090 instead
of :8080 and web search is added transparently. llama-server at :8080 is
unchanged and still directly accessible if needed.

How it works:
  1. Receives /v1/chat/completions request
  2. Scans the last user message for search triggers
     (questions about current events, "search for", "look up", etc.)
  3. If triggered: queries SearXNG, extracts top results, prepends a
     [WEB SEARCH RESULTS] block to the system prompt
  4. Forwards the augmented request to llama-server
  5. Streams or returns the response unmodified

All other endpoints (/v1/models, /v1/completions, /health, etc.) are
transparently proxied to llama-server with no modification.

Environment variables:
  LLAMA_URL         llama-server base  (default: http://localhost:8080)
  LLAMA_API_KEY     API key            (default: local)
  SEARXNG_URL       SearXNG base       (default: http://localhost:8081)
  PROXY_PORT        port to listen on  (default: 8090)
  SEARCH_RESULTS    number of results  (default: 4)
  MAX_RESULT_CHARS  chars per result   (default: 400)
  DEBUG             set to 1 for verbose logging
"""

import os
import re
import json
import logging
import asyncio
from typing import Any
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import uvicorn

# ── Config ─────────────────────────────────────────────────────────
LLAMA_URL        = os.environ.get("LLAMA_URL",        "http://localhost:8080").rstrip("/")
LLAMA_API_KEY    = os.environ.get("LLAMA_API_KEY",    "local")
SEARXNG_URL      = os.environ.get("SEARXNG_URL",      "http://localhost:8081").rstrip("/")
PROXY_PORT       = int(os.environ.get("PROXY_PORT",   "8090"))
SEARCH_RESULTS   = int(os.environ.get("SEARCH_RESULTS", "4"))
MAX_RESULT_CHARS = int(os.environ.get("MAX_RESULT_CHARS", "400"))
DEBUG            = os.environ.get("DEBUG", "0") == "1"

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("search_proxy")

# ── Search trigger patterns ────────────────────────────────────────
# Matches questions likely to benefit from current information.
# Conservative by design — only obvious search intent is triggered.
_SEARCH_TRIGGERS = re.compile(
    r"""
    \b(
        search\s+for | look\s+up | find\s+out | what.s\s+the\s+latest |
        current(ly)? | today | right\s+now | as\s+of\s+(today|now|202\d) |
        recent(ly)? | news\s+(about|on) | who\s+is\s+the\s+(current|new) |
        what\s+is\s+the\s+(current|latest|newest|best) |
        how\s+much\s+does | price\s+of | stock\s+price |
        weather | forecast | score | standings | results\s+of |
        when\s+(is|was|did|does|will) | who\s+won | who\s+is\s+winning |
        released\s+(in\s+)?\d{4} | coming\s+out | available\s+now
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ── FastAPI app ────────────────────────────────────────────────────
app = FastAPI(title="Search-Augmented Proxy", version="1.0.0")

# Shared async HTTP client (connection pooled)
_http = httpx.AsyncClient(timeout=30.0)


async def _search(query: str) -> str:
    """Query SearXNG and return a formatted block of results."""
    try:
        resp = await _http.get(
            f"{SEARXNG_URL}/search",
            params={"q": query, "format": "json", "categories": "general"},
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning(f"SearXNG query failed: {exc}")
        return ""

    results = data.get("results", [])[:SEARCH_RESULTS]
    if not results:
        return ""

    lines = [f"[WEB SEARCH RESULTS for: {query}]"]
    for i, r in enumerate(results, 1):
        title   = r.get("title", "").strip()
        url     = r.get("url", "").strip()
        snippet = r.get("content", "").strip()
        # Truncate long snippets
        if len(snippet) > MAX_RESULT_CHARS:
            snippet = snippet[:MAX_RESULT_CHARS].rsplit(" ", 1)[0] + "…"
        lines.append(f"\n[{i}] {title}\n    {url}\n    {snippet}")

    lines.append("\n[Use the above search results to answer the question. "
                 "Cite sources where relevant. "
                 "If the results are not relevant, answer from your own knowledge.]\n")
    return "\n".join(lines)


def _extract_query(messages: list[dict]) -> str | None:
    """Extract the last user message text and return it if search is warranted."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):  # vision message format
                for part in content:
                    if part.get("type") == "text":
                        content = part.get("text", "")
                        break
            if isinstance(content, str) and _SEARCH_TRIGGERS.search(content):
                return content.strip()
    return None


def _inject_search_results(body: dict, search_block: str) -> dict:
    """Prepend search results to the system prompt (or add one if absent)."""
    messages = body.get("messages", [])
    if messages and messages[0].get("role") == "system":
        messages[0]["content"] = search_block + "\n\n" + messages[0]["content"]
    else:
        messages.insert(0, {"role": "system", "content": search_block})
    body["messages"] = messages
    return body


# ── Route: chat completions (the magic happens here) ───────────────
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    messages = body.get("messages", [])
    search_block = ""

    # Check if search is warranted
    query = _extract_query(messages)
    if query:
        log.info(f"Search triggered: {query[:80]}")
        search_block = await _search(query)
        if search_block:
            body = _inject_search_results(body, search_block)
            log.debug(f"Injected {len(search_block)} chars of search context")
        else:
            log.info("Search returned no results — answering from model knowledge")

    # Forward to llama-server
    is_stream = body.get("stream", False)
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {LLAMA_API_KEY}",
    }

    if is_stream:
        async def stream_gen():
            async with _http.stream(
                "POST",
                f"{LLAMA_URL}/v1/chat/completions",
                json=body,
                headers=headers,
            ) as r:
                async for chunk in r.aiter_raw():
                    yield chunk

        return StreamingResponse(stream_gen(), media_type="text/event-stream")
    else:
        resp = await _http.post(
            f"{LLAMA_URL}/v1/chat/completions",
            json=body,
            headers=headers,
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )


# ── Route: transparent passthrough for everything else ────────────
@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def passthrough(request: Request, path: str):
    """Forward all other requests to llama-server unchanged."""
    url = f"{LLAMA_URL}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers["Authorization"] = f"Bearer {LLAMA_API_KEY}"

    body = await request.body()

    resp = await _http.request(
        method  = request.method,
        url     = url,
        headers = headers,
        content = body,
    )
    return Response(
        content    = resp.content,
        status_code= resp.status_code,
        headers    = dict(resp.headers),
    )


# ── Health ─────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    # Check both backends
    llama_ok   = False
    searxng_ok = False
    try:
        r = await _http.get(f"{LLAMA_URL}/v1/models")
        llama_ok = r.status_code == 200
    except Exception:
        pass
    try:
        r = await _http.get(f"{SEARXNG_URL}/healthz", timeout=3)
        searxng_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status":   "ok",
        "proxy_port": PROXY_PORT,
        "llama":    {"url": LLAMA_URL,    "reachable": llama_ok},
        "searxng":  {"url": SEARXNG_URL,  "reachable": searxng_ok},
    }


# ── Entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("━" * 55)
    log.info(f"  Search-Augmented Proxy  :  port {PROXY_PORT}")
    log.info(f"  → llama-server          :  {LLAMA_URL}")
    log.info(f"  → SearXNG               :  {SEARXNG_URL}")
    log.info(f"  Search results per query:  {SEARCH_RESULTS}")
    log.info("━" * 55)
    log.info("  Point AnythingLLM at http://localhost:8090 (not 8080)")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT, log_level="warning")
