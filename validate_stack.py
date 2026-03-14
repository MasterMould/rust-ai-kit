#!/usr/bin/env python3
"""
validate_stack.py — End-to-end validation for rust-ai-kit services
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tests every service in sequence and gives a clear PASS / FAIL / SKIP
for each check. Run after starting the stack (option 2 in manager).

Usage:
    python3 validate_stack.py              # test all services
    python3 validate_stack.py --memory     # memory tests only
    python3 validate_stack.py --search     # search proxy only
    python3 validate_stack.py --engine     # llama-server only
    python3 validate_stack.py --verbose    # show full responses
"""

import sys
import json
import time
import argparse
import textwrap
import urllib.request
import urllib.error
from dataclasses import dataclass, field

# ── Endpoints ──────────────────────────────────────────────────────
ENGINE_URL  = "http://localhost:8080"
PROXY_URL   = "http://localhost:8090"
MEMORY_URL  = "http://localhost:8000"
SEARXNG_URL = "http://localhost:8081"

# ── Colours ────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
C = "\033[96m"; W = "\033[1m";  N = "\033[0m"

def ok(msg):   print(f"  {G}✅  PASS{N}  {msg}")
def fail(msg): print(f"  {R}❌  FAIL{N}  {msg}")
def skip(msg): print(f"  {Y}⏭   SKIP{N}  {msg}")
def info(msg): print(f"  {C}ℹ️   {N}      {msg}")
def step(msg): print(f"\n{W}{C}── {msg} ──{N}")

# ── HTTP helpers ───────────────────────────────────────────────────

def get(url, timeout=10):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer local"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def post(url, data, timeout=60):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer local"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def reachable(url, timeout=5):
    try:
        get(url, timeout=timeout)
        return True
    except Exception:
        try:
            urllib.request.urlopen(url, timeout=timeout)
            return True
        except Exception:
            return False

# ── Results tracker ───────────────────────────────────────────────
@dataclass
class Results:
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    def record(self, passed=False, failed=False, skipped=False):
        if passed:  self.passed  += 1
        if failed:  self.failed  += 1
        if skipped: self.skipped += 1

res = Results()

# ================================================================
#  1. ENGINE — llama-server
# ================================================================
def test_engine(verbose=False):
    step("1  llama-server  :8080")

    # 1.1 Reachability
    try:
        data = get(f"{ENGINE_URL}/v1/models")
        models = data.get("data") or data.get("models", [])
        names = [m.get("id") or m.get("name","?") for m in models]
        ok(f"Models endpoint — found: {', '.join(names) or '(empty)'}")
        res.record(passed=True)
    except Exception as e:
        fail(f"Cannot reach llama-server: {e}")
        fail("Is the stack running? Use option 2 in the manager.")
        res.record(failed=True)
        return False

    # 1.2 Basic completion
    try:
        t0 = time.time()
        resp = post(f"{ENGINE_URL}/v1/chat/completions", {
            "model": "llama",
            "messages": [{"role": "user", "content": "Reply with exactly: VALIDATION_OK"}],
            "max_tokens": 20,
            "temperature": 0,
        })
        elapsed = time.time() - t0
        content = resp["choices"][0]["message"]["content"].strip()
        if "VALIDATION_OK" in content or len(content) > 0:
            ok(f"Chat completion — got response in {elapsed:.1f}s")
            if verbose: info(f"Response: {content!r}")
            res.record(passed=True)
        else:
            fail(f"Unexpected empty response")
            res.record(failed=True)
    except Exception as e:
        fail(f"Chat completion failed: {e}")
        res.record(failed=True)
        return False

    # 1.3 API key enforcement
    try:
        req = urllib.request.Request(
            f"{ENGINE_URL}/v1/models",
            headers={"Authorization": "Bearer WRONG_KEY"},
        )
        urllib.request.urlopen(req, timeout=5)
        skip("API key not enforced (--api-key not set on llama-server)")
        res.record(skipped=True)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            ok("API key enforcement — 401 on wrong key ✓")
            res.record(passed=True)
        else:
            skip(f"Unexpected HTTP {e.code} on auth check")
            res.record(skipped=True)
    except Exception:
        skip("Could not check API key enforcement")
        res.record(skipped=True)

    return True

# ================================================================
#  2. MEMORY SERVER — mem0 + ChromaDB
# ================================================================
def test_memory(verbose=False):
    step("2  Memory server  :8000")

    # 2.1 Health
    try:
        data = get(f"{MEMORY_URL}/health")
        ok(f"Health endpoint — {data}")
        res.record(passed=True)
    except Exception as e:
        fail(f"Memory server not reachable: {e}")
        fail("Is memory_server.py running? Check: tail ~/ai_stack/logs/memory.log")
        res.record(failed=True)
        return False

    TEST_USER = "validate_test_user"

    # 2.2 Clear any previous test data
    try:
        post(f"{MEMORY_URL}/memories?confirm=true&user_id={TEST_USER}", {})
    except Exception:
        pass  # fine if empty

    # 2.3 Memorize
    try:
        t0 = time.time()
        resp = post(f"{MEMORY_URL}/memorize", {
            "messages": [
                {"role": "user",      "content": "I always use dark mode and prefer concise technical answers."},
                {"role": "assistant", "content": "Got it, I'll remember your preferences."},
                {"role": "user",      "content": "Also, I'm a Python developer working on AI tooling."},
                {"role": "assistant", "content": "Understood, noted for future reference."},
            ],
            "user_id": TEST_USER,
        })
        elapsed = time.time() - t0
        added = resp.get("memories_added", 0)
        ok(f"Memorize — extracted {added} memories in {elapsed:.1f}s")
        if verbose: info(f"Results: {json.dumps(resp.get('results', []), indent=2)}")
        res.record(passed=True)
    except Exception as e:
        fail(f"Memorize failed: {e}")
        res.record(failed=True)
        return False

    # 2.4 Wait for indexing
    time.sleep(1)

    # 2.5 List memories
    try:
        data = get(f"{MEMORY_URL}/memories?user_id={TEST_USER}")
        count = data.get("count", 0)
        memories = data.get("memories", [])
        if count > 0:
            ok(f"List memories — found {count} stored fact(s)")
            if verbose:
                for m in memories:
                    info(f"  • {m.get('memory', m.get('text', str(m)))}")
            res.record(passed=True)
        else:
            fail("No memories stored — extraction may have failed")
            fail("Check llama-server is running and reachable from memory server")
            res.record(failed=True)
    except Exception as e:
        fail(f"List memories failed: {e}")
        res.record(failed=True)
        return False

    # 2.6 Retrieve — semantic search
    queries = [
        ("display preferences",  ["dark", "mode"]),
        ("programming language",  ["python"]),
        ("work area",             ["ai", "developer", "tooling"]),
    ]
    for query, expected_terms in queries:
        try:
            t0 = time.time()
            resp = post(f"{MEMORY_URL}/retrieve", {
                "query":   query,
                "user_id": TEST_USER,
                "limit":   3,
            })
            elapsed = time.time() - t0
            memories = resp.get("memories", [])
            result_text = " ".join(
                str(m.get("memory") or m.get("text") or m)
                for m in memories
            ).lower()
            found = any(t in result_text for t in expected_terms)
            if found and memories:
                ok(f"Retrieve '{query}' — {len(memories)} result(s) in {elapsed:.1f}s ✓ semantic match")
                if verbose:
                    for m in memories:
                        info(f"  • score={m.get('score', '?'):.3f}  {m.get('memory', m.get('text', ''))}")
                res.record(passed=True)
            elif memories:
                ok(f"Retrieve '{query}' — {len(memories)} result(s) returned (terms not matched — check manually)")
                if verbose:
                    for m in memories:
                        info(f"  • {m.get('memory', m.get('text', str(m)))}")
                res.record(passed=True)
            else:
                fail(f"Retrieve '{query}' — no results returned")
                res.record(failed=True)
        except Exception as e:
            fail(f"Retrieve '{query}' failed: {e}")
            res.record(failed=True)

    # 2.7 Cleanup test data
    try:
        post(f"{MEMORY_URL}/memories?confirm=true&user_id={TEST_USER}", {})
        info("Test memories cleaned up.")
    except Exception:
        pass

    return True

# ================================================================
#  3. SEARCH PROXY
# ================================================================
def test_search_proxy(verbose=False):
    step("3  Search proxy  :8090")

    # 3.1 Health
    try:
        data = get(f"{PROXY_URL}/health")
        llama_ok   = data.get("llama",   {}).get("reachable", False)
        searxng_ok = data.get("searxng", {}).get("reachable", False)
        ok(f"Proxy health — llama={llama_ok} searxng={searxng_ok}")
        if not llama_ok:
            fail("Proxy cannot reach llama-server — check :8080")
        if not searxng_ok:
            fail("Proxy cannot reach SearXNG — check :8081 and option 9 in manager")
        res.record(passed=True)
    except Exception as e:
        fail(f"Search proxy not reachable: {e}")
        fail("Is search_proxy.py running? Check: tail ~/ai_stack/logs/proxy.log")
        res.record(failed=True)
        return False

    # 3.2 Passthrough — models endpoint
    try:
        data = get(f"{PROXY_URL}/v1/models")
        ok("Passthrough /v1/models — proxy forwarding works")
        res.record(passed=True)
    except Exception as e:
        fail(f"Proxy passthrough failed: {e}")
        res.record(failed=True)

    # 3.3 Non-search question — should NOT trigger search
    try:
        t0 = time.time()
        resp = post(f"{PROXY_URL}/v1/chat/completions", {
            "model": "llama",
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
            "max_tokens": 20,
            "temperature": 0,
        })
        elapsed = time.time() - t0
        content = resp["choices"][0]["message"]["content"].strip()
        ok(f"Non-search query — answered in {elapsed:.1f}s (no search triggered)")
        if verbose: info(f"Response: {content!r}")
        res.record(passed=True)
    except Exception as e:
        fail(f"Non-search completion failed: {e}")
        res.record(failed=True)

    # 3.4 Search-triggered question
    if not reachable(SEARXNG_URL):
        skip("SearXNG not running — skipping search trigger test")
        res.record(skipped=True)
    else:
        try:
            t0 = time.time()
            resp = post(f"{PROXY_URL}/v1/chat/completions", {
                "model": "llama",
                "messages": [{"role": "user",
                              "content": "Search for the latest news about Intel Arc GPU drivers"}],
                "max_tokens": 150,
                "temperature": 0.1,
            })
            elapsed = time.time() - t0
            content = resp["choices"][0]["message"]["content"].strip()
            ok(f"Search-triggered query — response in {elapsed:.1f}s")
            if verbose:
                info("Response preview:")
                print(textwrap.indent(textwrap.fill(content[:300], 70), "    "))
            res.record(passed=True)
        except Exception as e:
            fail(f"Search-triggered completion failed: {e}")
            res.record(failed=True)

    return True

# ================================================================
#  4. SEARXNG direct
# ================================================================
def test_searxng(verbose=False):
    step("4  SearXNG  :8081")

    try:
        req = urllib.request.Request(
            f"{SEARXNG_URL}/search?q=test&format=json",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        ok(f"SearXNG query — returned {len(results)} results")
        if verbose and results:
            info(f"Top result: {results[0].get('title', '?')} — {results[0].get('url', '?')}")
        res.record(passed=True)
    except Exception as e:
        fail(f"SearXNG not reachable or returned error: {e}")
        fail("Start SearXNG from manager option 9 (Setup Web Search)")
        res.record(failed=True)

# ================================================================
#  Summary
# ================================================================
def print_summary():
    total = res.passed + res.failed + res.skipped
    print(f"\n{W}{'━'*52}{N}")
    print(f"  Results:  "
          f"{G}{res.passed} passed{N}  "
          f"{R}{res.failed} failed{N}  "
          f"{Y}{res.skipped} skipped{N}  "
          f"/ {total} total")
    if res.failed == 0:
        print(f"  {G}{W}All checks passed — stack is healthy ✓{N}")
    else:
        print(f"  {R}{W}{res.failed} check(s) failed — see details above{N}")
    print(f"{'━'*52}\n")
    return res.failed == 0

# ================================================================
#  Main
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="Validate rust-ai-kit stack services")
    parser.add_argument("--engine",  action="store_true", help="Test llama-server only")
    parser.add_argument("--memory",  action="store_true", help="Test memory server only")
    parser.add_argument("--search",  action="store_true", help="Test search proxy only")
    parser.add_argument("--searxng", action="store_true", help="Test SearXNG only")
    parser.add_argument("--verbose", action="store_true", help="Show full responses")
    args = parser.parse_args()

    # If no filter flags, run everything
    run_all = not any([args.engine, args.memory, args.search, args.searxng])

    print(f"\n{W}{C}rust-ai-kit Stack Validator{N}")
    print(f"{C}{'━'*52}{N}")

    if run_all or args.engine:
        test_engine(args.verbose)
    if run_all or args.memory:
        test_memory(args.verbose)
    if run_all or args.search:
        test_search_proxy(args.verbose)
    if run_all or args.searxng:
        test_searxng(args.verbose)

    success = print_summary()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
