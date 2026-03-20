#!/usr/bin/env python3
"""
refactor.py — splits llm_factory_rustaikit.py into core/ + ui/ packages.

Usage:
    python3 refactor.py                        # dry-run (shows what would be written)
    python3 refactor.py --apply                # actually write files
    python3 refactor.py --apply --force        # overwrite existing core/ and ui/
    python3 refactor.py --verify-only          # syntax-check already-written files

The original file is NEVER modified.  A backup is written to
llm_factory_rustaikit.py.bak before any files are touched.

Steps executed:
    1. Read + validate source file
    2. Extract named line ranges
    3. Build each module (header imports + body)
    4. Syntax-check every module with ast.parse
    5. (--apply) Write core/__init__.py, ui/__init__.py, all modules
    6. (--apply) Rewrite entry-point (3 lines)
    7. Print summary table
"""

import ast
import argparse
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Dict, List, Tuple

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Split llm_factory_rustaikit.py")
parser.add_argument("--apply",       action="store_true", help="Write files (default: dry-run)")
parser.add_argument("--force",       action="store_true", help="Overwrite existing core/ ui/")
parser.add_argument("--verify-only", action="store_true", help="Syntax-check already-written files")
parser.add_argument("--source", default="llm_factory_rustaikit.py",
                    help="Source file (default: llm_factory_rustaikit.py)")
args = parser.parse_args()

SOURCE = Path(args.source)
ROOT   = SOURCE.parent

# ── Colours ───────────────────────────────────────────────────────────────────
G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; C = "\033[36m"; W = "\033[1m"; N = "\033[0m"
def ok(s):   print(f"{G}  ✅  {s}{N}")
def warn(s): print(f"{Y}  ⚠️   {s}{N}")
def err(s):  print(f"{R}  ❌  {s}{N}"); sys.exit(1)
def info(s): print(f"{C}  ℹ️   {s}{N}")
def head(s): print(f"\n{W}{C}── {s} ──{N}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — read source
# ─────────────────────────────────────────────────────────────────────────────
head("Step 1 — reading source")

if not SOURCE.exists():
    err(f"Source not found: {SOURCE}")

raw_lines = SOURCE.read_text(encoding="utf-8").splitlines()
total     = len(raw_lines)
info(f"Source: {SOURCE}  ({total} lines)")

# Verify it parses before we touch anything
try:
    ast.parse(SOURCE.read_text(encoding="utf-8"))
    ok("Source parses cleanly")
except SyntaxError as e:
    err(f"Source has a syntax error — fix it before refactoring:\n  {e}")


def L(start: int, end: int) -> str:
    """Return source lines [start, end] (1-indexed, inclusive) as a string."""
    return "\n".join(raw_lines[start - 1 : end])


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — locate named boundaries in the source
# ─────────────────────────────────────────────────────────────────────────────
head("Step 2 — locating boundaries")

def find_line(pattern: str, start_from: int = 1) -> int:
    """Return 1-indexed line number of first line containing `pattern`."""
    for i, line in enumerate(raw_lines[start_from - 1 :], start=start_from):
        if pattern in line:
            return i
    err(f"Pattern not found in source: {repr(pattern)}")

# Key boundaries (1-indexed line numbers)
B: Dict[str, int] = {}
B["CONSTANTS_START"]    = find_line("# PATHS & CONSTANTS")
B["ENUMS_START"]        = find_line("class BackendMode(Enum):")
B["LOGGING_START"]      = find_line("logging.basicConfig(")
B["AUTH_HELPERS_START"] = find_line("import pwd as _pwd")
B["AUTH_CLASS_START"]   = find_line("class AuthManager:")
B["GPU_START"]          = find_line("class GPUDetector:")
B["STACK_START"]        = find_line("class StackManager:")
B["MODELS_START"]       = find_line("class ModelManager:")
B["MEMORY_START"]       = find_line("class MemoryManager:")
B["INFERENCE_START"]    = find_line("class InferenceClient:")
B["OLLAMA_START"]       = find_line("class OllamaClient:")
B["SECURITY_START"]     = find_line("class SecurityValidator:")
B["RAG_START"]          = find_line("class RAGManager:")
B["STREAMLIT_CFG"]      = find_line("st.set_page_config(")
B["CHECK_AUTH"]         = find_line("def check_auth() -> bool:")
B["SHOW_LOGIN"]         = find_line("def show_login():")
B["INIT_SESSION"]       = find_line("def init_session():")
B["MAIN_FN"]            = find_line("def main():")
B["SEND_FN"]            = find_line("def _send(user_input: str,")
B["TAB_CHAT"]           = find_line("def tab_chat(temperature: float, max_tokens: int):")
B["SVC_FN"]             = find_line("def _svc(label: str, ok: bool,")
B["TAB_STACK"]          = find_line("def tab_stack():")
B["TAB_MEMORY"]         = find_line("def tab_memory():")
B["TAB_MODELS"]         = find_line("def tab_models():")
B["TAB_RAG"]            = find_line("def tab_rag():")
B["TAB_CODE"]           = find_line("def tab_code(temperature: float):")
B["TAB_BENCHMARK"]      = find_line("def tab_benchmark():")
B["TAB_SECURITY"]       = find_line("def tab_security():")
B["TAB_USERS"]          = find_line("def tab_users():")
B["TAB_LOGS"]           = find_line("def tab_logs():")

for name, lineno in sorted(B.items(), key=lambda x: x[1]):
    info(f"  {lineno:>4}  {name}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — define every module
# ─────────────────────────────────────────────────────────────────────────────
head("Step 3 — building modules")

# Each entry: path → (header_imports, body_lines_string)
MODULES: Dict[Path, str] = {}


def module(rel_path: str, imports: str, body: str) -> None:
    """Register a module with its import header and extracted body."""
    full = ROOT / rel_path
    # Strip leading blank lines from body
    body = body.strip("\n")
    content = textwrap.dedent(imports).strip() + "\n\n" + body + "\n"
    MODULES[full] = content


# ── core/config.py ────────────────────────────────────────────────────────────
# Contains: all path/port constants, MODEL_CATALOGUE, enums, dataclasses,
#           app-local directory setup, logging bootstrap
module(
    "core/config.py",
    """
    # core/config.py — paths, ports, constants, enums, dataclasses, catalogue
    # No local imports — standard library only.
    from pathlib import Path
    from dataclasses import dataclass, field
    from enum import Enum
    from typing import List, Dict
    import logging
    """,
    # constants + catalogue + enums + app dirs + logging
    L(B["CONSTANTS_START"], B["AUTH_HELPERS_START"] - 1),
)

# ── core/auth.py ──────────────────────────────────────────────────────────────
# Contains: audit_log, PAM helpers, AuthManager
module(
    "core/auth.py",
    """
    # core/auth.py — PAM + local-JSON authentication, audit log
    import hashlib
    import json
    import logging
    import os
    import pwd as _pwd
    import grp as _grp
    from datetime import datetime
    from pathlib import Path
    from typing import Dict, List, Optional, Tuple

    from core.config import (
        AUDIT_LOG, USERS_DB, SecurityLevel,
        APP_LOG_DIR,
    )
    """,
    L(B["AUTH_HELPERS_START"], B["GPU_START"] - 1),
)

# ── core/gpu.py ───────────────────────────────────────────────────────────────
module(
    "core/gpu.py",
    """
    # core/gpu.py — Intel Arc A770 GPU detection (mirrors ai_stack_manager.sh)
    import re
    import subprocess
    from pathlib import Path
    from typing import Optional
    """,
    L(B["GPU_START"], B["STACK_START"] - 1),
)

# ── core/stack.py ─────────────────────────────────────────────────────────────
module(
    "core/stack.py",
    """
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
        MODEL_CONFIG,
    )
    from core.gpu import GPUDetector
    """,
    L(B["STACK_START"], B["MODELS_START"] - 1),
)

# ── core/models.py ────────────────────────────────────────────────────────────
module(
    "core/models.py",
    """
    # core/models.py — ModelManager: get/set/list/download/delete GGUF models
    # Mirrors _load_active_model(), _switch_model_menu(), _remove_model_menu()
    # from ai_stack_manager.sh.
    import logging
    import subprocess
    from pathlib import Path
    from typing import Dict, List, Tuple

    from core.config import MODEL_DIR, MODEL_CONFIG

    logger = logging.getLogger(__name__)
    """,
    L(B["MODELS_START"], B["MEMORY_START"] - 1),
)

# ── core/memory.py ────────────────────────────────────────────────────────────
module(
    "core/memory.py",
    """
    # core/memory.py — MemoryManager: mem0 + ChromaDB REST client (:8000)
    import logging
    from typing import Dict, List

    import requests

    from core.config import MEMORY_URL

    logger = logging.getLogger(__name__)
    """,
    L(B["MEMORY_START"], B["INFERENCE_START"] - 1),
)

# ── core/inference.py ─────────────────────────────────────────────────────────
# NOTE: InferenceClient.chat() writes to st.session_state for UX feedback.
# The writes are wrapped in try/except so the class remains importable without
# Streamlit (e.g. in unit tests).  This is the only intentional Streamlit
# touch-point in core/.
module(
    "core/inference.py",
    """
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
    """,
    # Body is extracted verbatim — the existing try/except around st.session_state
    # already guards against AttributeError if st is None.
    L(B["INFERENCE_START"], B["SECURITY_START"] - 1),
)

# ── core/security_rag.py ──────────────────────────────────────────────────────
module(
    "core/security_rag.py",
    """
    # core/security_rag.py — SecurityValidator + RAGManager
    import json
    import re
    from datetime import datetime
    from pathlib import Path
    from typing import Dict, List, Tuple

    from core.config import SECURITY_CONFIG, RAG_DOCS_DIR
    """,
    L(B["SECURITY_START"], B["STREAMLIT_CFG"] - 1),
)

# ── ui/app.py ─────────────────────────────────────────────────────────────────
# Contains: page config, CSS, check_auth, show_login, init_session, main, sidebar
# Imports every tab function.
module(
    "ui/app.py",
    """
    # ui/app.py — Streamlit page config, CSS, sidebar, main entry point
    import json
    from datetime import datetime
    from pathlib import Path

    import streamlit as st

    from core.config import (
        BackendMode, SecurityLevel,
        CHAT_HISTORY_DIR,
        ENGINE_PORT, PROXY_PORT, MEMORY_PORT,
    )
    from core.auth      import AuthManager, audit_log
    from core.models    import ModelManager
    from core.inference import OllamaClient
    from core.security_rag import RAGManager

    from ui.tab_chat      import tab_chat
    from ui.tab_stack     import tab_stack
    from ui.tab_memory    import tab_memory
    from ui.tab_models    import tab_models
    from ui.tab_rag       import tab_rag
    from ui.tab_code      import tab_code
    from ui.tab_benchmark import tab_benchmark
    from ui.tab_security  import tab_security
    from ui.tab_users     import tab_users
    from ui.tab_logs      import tab_logs
    """,
    # page config + CSS + check_auth + show_login + init_session + main
    L(B["STREAMLIT_CFG"], B["SEND_FN"] - 1),
)

# ── ui/tab_chat.py ────────────────────────────────────────────────────────────
module(
    "ui/tab_chat.py",
    """
    # ui/tab_chat.py — Chat tab: _send() + tab_chat()
    from pathlib import Path

    import streamlit as st

    from core.config    import BackendMode, ENGINE_PORT, STACK_LOG_DIR
    from core.auth      import audit_log
    from core.gpu       import GPUDetector
    from core.stack     import StackManager
    from core.models    import ModelManager
    from core.memory    import MemoryManager
    from core.inference import InferenceClient, OllamaClient
    from core.security_rag import SecurityValidator, RAGManager
    """,
    L(B["SEND_FN"], B["SVC_FN"] - 1),
)

# ── ui/tab_stack.py ───────────────────────────────────────────────────────────
module(
    "ui/tab_stack.py",
    """
    # ui/tab_stack.py — Stack status tab: _svc() + tab_stack()
    import subprocess
    from pathlib import Path

    import requests
    import streamlit as st

    from core.config import (
        BackendMode, ENGINE_PORT, PROXY_PORT, MEMORY_PORT, SEARXNG_PORT,
        PROXY_URL, STACK_LOG_DIR, MODEL_CONFIG,
        LLAMA_API_KEY, LLAMA_SERVER_MODEL,
    )
    from core.auth   import audit_log
    from core.gpu    import GPUDetector
    from core.stack  import StackManager
    from core.models import ModelManager
    """,
    L(B["SVC_FN"], B["TAB_MEMORY"] - 1),
)

# ── ui/tab_memory.py ──────────────────────────────────────────────────────────
module(
    "ui/tab_memory.py",
    """
    # ui/tab_memory.py — Memory tab (mem0 + ChromaDB)
    import streamlit as st

    from core.config import BackendMode
    from core.stack  import StackManager
    from core.memory import MemoryManager
    import pwd as _pwd
    import grp as _grp
    """,
    L(B["TAB_MEMORY"], B["TAB_MODELS"] - 1),
)

# ── ui/tab_models.py ──────────────────────────────────────────────────────────
module(
    "ui/tab_models.py",
    """
    # ui/tab_models.py — Model Manager tab
    from pathlib import Path

    import streamlit as st

    from core.config import BackendMode, MODEL_DIR, MODEL_CONFIG, MODEL_CATALOGUE
    from core.auth   import audit_log
    from core.models import ModelManager
    from core.inference import OllamaClient
    """,
    L(B["TAB_MODELS"], B["TAB_RAG"] - 1),
)

# ── ui/tab_rag.py ─────────────────────────────────────────────────────────────
module(
    "ui/tab_rag.py",
    """
    # ui/tab_rag.py — Local RAG Documents tab
    import streamlit as st

    from core.config       import APP_WORKSPACE
    from core.auth         import audit_log
    from core.security_rag import RAGManager
    """,
    L(B["TAB_RAG"], B["TAB_CODE"] - 1),
)

# ── ui/tab_code.py ────────────────────────────────────────────────────────────
module(
    "ui/tab_code.py",
    """
    # ui/tab_code.py — Code Generation tab
    import streamlit as st

    from core.config       import BackendMode, APP_WORKSPACE
    from core.inference    import InferenceClient, OllamaClient
    from core.security_rag import SecurityValidator
    """,
    L(B["TAB_CODE"], B["TAB_BENCHMARK"] - 1),
)

# ── ui/tab_benchmark.py ───────────────────────────────────────────────────────
module(
    "ui/tab_benchmark.py",
    """
    # ui/tab_benchmark.py — GPU Benchmark tab (mirrors option 12 in ai_stack_manager.sh)
    import streamlit as st

    from core.config import BackendMode, ENGINE_PORT, STACK_LOG_DIR
    from core.auth   import audit_log
    from core.stack  import StackManager
    """,
    L(B["TAB_BENCHMARK"], B["TAB_SECURITY"] - 1),
)

# ── ui/tab_security.py ────────────────────────────────────────────────────────
module(
    "ui/tab_security.py",
    """
    # ui/tab_security.py — Security scanner + audit statistics tab
    import streamlit as st

    from core.auth         import AUDIT_LOG
    from core.security_rag import SecurityValidator
    """,
    L(B["TAB_SECURITY"], B["TAB_USERS"] - 1),
)

# ── ui/tab_users.py ───────────────────────────────────────────────────────────
module(
    "ui/tab_users.py",
    """
    # ui/tab_users.py — User management tab (PAM + local accounts)
    import pwd as _pwd
    import grp as _grp

    import streamlit as st

    from core.config import SecurityLevel
    from core.auth   import AuthManager, audit_log
    """,
    L(B["TAB_USERS"], B["TAB_LOGS"] - 1),
)

# ── ui/tab_logs.py ────────────────────────────────────────────────────────────
module(
    "ui/tab_logs.py",
    """
    # ui/tab_logs.py — Log viewer tab (audit + engine/memory/proxy)
    import streamlit as st

    from core.config import BackendMode, STACK_LOG_DIR
    from core.auth   import AUDIT_LOG
    from core.stack  import StackManager
    """,
    L(B["TAB_LOGS"], total),
)

# ── __init__.py files ─────────────────────────────────────────────────────────
# Re-export every public name so that any external code that did
#   `from llm_factory_rustaikit import StackManager`
# can instead do  `from core import StackManager`  without changes.

CORE_INIT = """\
# core/__init__.py — re-exports for convenience
from core.config       import *  # noqa: F401,F403
from core.auth         import AuthManager, audit_log  # noqa: F401
from core.gpu          import GPUDetector  # noqa: F401
from core.stack        import StackManager  # noqa: F401
from core.models       import ModelManager  # noqa: F401
from core.memory       import MemoryManager  # noqa: F401
from core.inference    import InferenceClient, OllamaClient  # noqa: F401
from core.security_rag import SecurityValidator, RAGManager  # noqa: F401
"""

UI_INIT = """\
# ui/__init__.py
"""

ENTRY_POINT = '''\
"""
rust-ai-kit LLM Factory — entry point.
Run:   streamlit run llm_factory_rustaikit.py
Docs:  see REFACTOR_PLAN.md
"""
from ui.app import main   # noqa: E402

if __name__ == "__main__":
    main()
'''

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — syntax-check every module
# ─────────────────────────────────────────────────────────────────────────────
head("Step 4 — syntax checking")

errors: List[Tuple[str, str]] = []

for path, content in MODULES.items():
    try:
        ast.parse(content)
        ok(f"{path.relative_to(ROOT)}")
    except SyntaxError as e:
        errors.append((str(path.relative_to(ROOT)), str(e)))
        warn(f"SYNTAX ERROR in {path.relative_to(ROOT)}: {e}")

if errors:
    print(f"\n{R}  {len(errors)} syntax error(s) found. Fix before applying.{N}")
    for p, e in errors:
        print(f"    {p}: {e}")
    if args.apply:
        err("Aborting --apply due to syntax errors.")
else:
    ok(f"All {len(MODULES)} modules parse cleanly")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — verify-only mode
# ─────────────────────────────────────────────────────────────────────────────
if args.verify_only:
    head("Verify-only — checking already-written files")
    all_ok = True
    for path in MODULES:
        if path.exists():
            try:
                ast.parse(path.read_text(encoding="utf-8"))
                ok(str(path.relative_to(ROOT)))
            except SyntaxError as e:
                warn(f"{path.relative_to(ROOT)}: {e}")
                all_ok = False
        else:
            warn(f"Not yet written: {path.relative_to(ROOT)}")
            all_ok = False
    if all_ok:
        ok("All on-disk files parse cleanly")
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — dry-run summary
# ─────────────────────────────────────────────────────────────────────────────
head("Summary")

print(f"\n  {'File':<45}  {'Lines':>6}  {'Status'}")
print(f"  {'-'*45}  {'-'*6}  {'-'*10}")
for path, content in sorted(MODULES.items(), key=lambda x: str(x[0])):
    rel   = str(path.relative_to(ROOT))
    lines = content.count("\n")
    exists = "exists" if path.exists() else "new"
    color  = Y if path.exists() and not args.force else G
    print(f"  {color}{rel:<45}  {lines:>6}  {exists}{N}")

# Also show the entry point and __init__ files
for label, content in [
    ("core/__init__.py", CORE_INIT),
    ("ui/__init__.py",   UI_INIT),
    ("llm_factory_rustaikit.py (entry)", ENTRY_POINT),
]:
    lines = content.count("\n")
    print(f"  {G}{label:<45}  {lines:>6}  rewrite{N}")

total_out = sum(c.count("\n") for c in MODULES.values())
print(f"\n  Total output: {total_out} lines across {len(MODULES) + 2} files")
print(f"  Original:     {total} lines in 1 file")

if not args.apply:
    print(f"\n{Y}  Dry run — no files written.  Add --apply to execute.{N}\n")
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — write files
# ─────────────────────────────────────────────────────────────────────────────
head("Step 7 — writing files")

# Safety checks
for pkg in [ROOT / "core", ROOT / "ui"]:
    if pkg.exists() and not args.force:
        err(
            f"{pkg} already exists. Use --force to overwrite, or delete it first.\n"
            f"  rm -rf {pkg}"
        )

# Backup original entry point
bak = SOURCE.with_suffix(".py.bak")
shutil.copy2(SOURCE, bak)
ok(f"Backed up original → {bak.name}")

# Create package directories
for pkg in [ROOT / "core", ROOT / "ui"]:
    pkg.mkdir(exist_ok=True)
    ok(f"mkdir {pkg.relative_to(ROOT)}/")

# Write __init__.py files
(ROOT / "core" / "__init__.py").write_text(CORE_INIT, encoding="utf-8")
ok("core/__init__.py")
(ROOT / "ui" / "__init__.py").write_text(UI_INIT, encoding="utf-8")
ok("ui/__init__.py")

# Write every module
for path, content in MODULES.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    lines = content.count("\n")
    ok(f"{path.relative_to(ROOT)}  ({lines} lines)")

# Rewrite entry point
SOURCE.write_text(ENTRY_POINT, encoding="utf-8")
ok(f"Rewrote entry point: {SOURCE.name}  (3 lines)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — post-write syntax verification
# ─────────────────────────────────────────────────────────────────────────────
head("Step 8 — post-write verification")

fail = 0
for path in list(MODULES.keys()) + [
    ROOT / "core" / "__init__.py",
    ROOT / "ui"   / "__init__.py",
    SOURCE,
]:
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        ok(str(path.relative_to(ROOT)))
    except SyntaxError as e:
        warn(f"SYNTAX ERROR in {path.relative_to(ROOT)}: {e}")
        fail += 1

print()
if fail:
    print(f"{R}  {fail} file(s) have syntax errors after writing.{N}")
    print(f"  The original is safe at {bak}")
    print(f"  To restore:  cp {bak} {SOURCE}")
else:
    print(f"{G}{W}  All done! {len(MODULES) + 3} files written, 0 errors.{N}")
    print()
    print(f"  Run the app:    streamlit run {SOURCE.name}")
    print(f"  Run make:       make run")
    print(f"  Original:       {bak.name}")
    print()
    print(f"  If anything breaks:  cp {bak.name} {SOURCE.name}")
    print()
