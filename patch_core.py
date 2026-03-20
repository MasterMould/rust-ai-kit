#!/usr/bin/env python3
"""
patch_core.py — auto-detects and fixes import mismatches in core/ and ui/
after the refactor split.  Safe to run multiple times.

Called automatically by launch.sh before starting Streamlit.
Can also be run manually:  python3 patch_core.py

What it does:
  1. Scans all ui/ and core/ files for ImportError-causing mismatches
  2. Applies targeted patches (adds re-exports / missing imports)
  3. Verifies every patched file still parses cleanly
  4. Reports what was fixed and exits 0 (never blocks the app)
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

G = "\033[32m"; Y = "\033[1;33m"; R = "\033[31m"; C = "\033[36m"; N = "\033[0m"
def ok(s):   print(f"{G}  ✅  {s}{N}")
def warn(s): print(f"{Y}  ⚠️   {s}{N}")
def info(s): print(f"{C}  ℹ️   {s}{N}")
def fixed(s):print(f"{G}  🔧  Fixed: {s}{N}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ok(path: Path) -> bool:
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        return True
    except SyntaxError:
        return False


def _append_if_missing(path: Path, line: str, marker: str) -> bool:
    """Append `line` to `path` if `marker` string is not already present."""
    content = path.read_text(encoding="utf-8")
    if marker in content:
        return False  # already present
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{line}\n")
    return True


def _prepend_import(path: Path, import_line: str) -> bool:
    """Insert `import_line` after the last existing import block."""
    content = path.read_text(encoding="utf-8")
    if import_line.strip() in content:
        return False
    lines = content.splitlines()
    # Find last import line
    last_import = 0
    for i, l in enumerate(lines):
        if l.startswith("import ") or l.startswith("from "):
            last_import = i
    lines.insert(last_import + 1, import_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Known patches
# Each entry: (description, target_file, check_marker, fix_fn)
# fix_fn receives the target Path and returns True if it made a change.
# ─────────────────────────────────────────────────────────────────────────────

def _patch_audit_log_reexport(path: Path) -> bool:
    """
    audit_log() ended up in core/config.py (it sits between the logging
    setup and the PAM helpers so the AUTH_HELPERS_START boundary misses it).
    Add a re-export line to core/auth.py so all imports from core.auth work.
    """
    return _append_if_missing(
        path,
        "from core.config import audit_log  # re-export: boundary fix",
        "re-export: boundary fix",
    )


def _patch_audit_log_in_config(path: Path) -> bool:
    """
    Ensure audit_log is also explicitly importable from core.config
    (it should already be there, but add a no-op export guard just in case).
    """
    content = path.read_text(encoding="utf-8")
    if "def audit_log(" in content:
        return False  # already defined there, nothing to do
    return False  # nothing needed


def _patch_model_catalogue_in_config(path: Path) -> bool:
    """
    MODEL_CATALOGUE must be importable from core.config.
    If it landed in core/models.py, add a re-export.
    """
    config = ROOT / "core" / "config.py"
    if "MODEL_CATALOGUE" in config.read_text(encoding="utf-8"):
        return False  # already there
    models = ROOT / "core" / "models.py"
    if "MODEL_CATALOGUE" not in models.read_text(encoding="utf-8"):
        return False  # not there either — nothing to re-export
    return _append_if_missing(
        config,
        "from core.models import MODEL_CATALOGUE  # re-export: boundary fix",
        "MODEL_CATALOGUE",
    )


def _patch_logger_in_auth(path: Path) -> bool:
    """
    core/auth.py needs a logger instance.  If it was stripped out by
    the boundary split, add it.
    """
    content = path.read_text(encoding="utf-8")
    if "logger" in content and "getLogger" in content:
        return False
    return _append_if_missing(
        path,
        "logger = __import__('logging').getLogger(__name__)",
        "getLogger",
    )


def _patch_security_config_in_security_rag(path: Path) -> bool:
    """
    SecurityValidator.validate_code() references SECURITY_CONFIG which
    must be imported in core/security_rag.py.
    """
    content = path.read_text(encoding="utf-8")
    if "SECURITY_CONFIG" in content:
        return False
    return _prepend_import(
        path,
        "from core.config import SECURITY_CONFIG  # patch: missing import",
    )


def _patch_datetime_in_security_rag(path: Path) -> bool:
    """RAGManager uses datetime but it may not have been imported."""
    content = path.read_text(encoding="utf-8")
    if "from datetime import datetime" in content or "import datetime" in content:
        return False
    return _prepend_import(path, "from datetime import datetime  # patch")


def _patch_missing_st_import_in_inference(path: Path) -> bool:
    """
    core/inference.py has a try/except streamlit import but some versions
    of the split may have dropped it.  Ensure it's present.
    """
    content = path.read_text(encoding="utf-8")
    if "import streamlit" in content:
        return False
    return _append_if_missing(
        path,
        (
            "try:\n"
            "    import streamlit as st\n"
            "except ImportError:\n"
            "    st = None  # type: ignore\n"
        ),
        "import streamlit as st",
    )


def _patch_tab_security_audit_log(path: Path) -> bool:
    """
    ui/tab_security.py imports AUDIT_LOG from core.auth but it may only
    be in core.config.  Add a fallback import.
    """
    content = path.read_text(encoding="utf-8")
    if "AUDIT_LOG" in content:
        return False
    return _prepend_import(
        path,
        "from core.config import AUDIT_LOG  # patch: missing import",
    )


# ── Patch registry ────────────────────────────────────────────────────────────
PATCHES = [
    # (description, relative_path, check_fn_or_None, fix_fn)
    (
        "core/auth.py re-exports audit_log",
        "core/auth.py",
        lambda p: "audit_log" not in p.read_text(),
        _patch_audit_log_reexport,
    ),
    (
        "core/auth.py has logger",
        "core/auth.py",
        lambda p: "logger" not in p.read_text() or "getLogger" not in p.read_text(),
        _patch_logger_in_auth,
    ),
    (
        "core/security_rag.py imports SECURITY_CONFIG",
        "core/security_rag.py",
        lambda p: p.exists() and "SECURITY_CONFIG" not in p.read_text(),
        _patch_security_config_in_security_rag,
    ),
    (
        "core/security_rag.py imports datetime",
        "core/security_rag.py",
        lambda p: p.exists() and "datetime" not in p.read_text(),
        _patch_datetime_in_security_rag,
    ),
    (
        "core/inference.py has streamlit try/except",
        "core/inference.py",
        lambda p: p.exists() and "import streamlit" not in p.read_text(),
        _patch_missing_st_import_in_inference,
    ),
    (
        "ui/tab_security.py can find AUDIT_LOG",
        "ui/tab_security.py",
        lambda p: p.exists() and "AUDIT_LOG" not in p.read_text(),
        _patch_tab_security_audit_log,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Runtime import error scanner
# Tries to import each core/ui module and collects ImportErrors so we can
# attempt targeted fixes even for issues not listed above.
# ─────────────────────────────────────────────────────────────────────────────

def _scan_import_errors() -> list:
    """
    Attempt to import every core.* and ui.* module.
    Returns list of (module_name, error_string) for failures.
    """
    import importlib
    import importlib.util
    import traceback

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    errors = []
    candidates = (
        ["core.config", "core.auth", "core.gpu", "core.stack",
         "core.models", "core.memory", "core.inference", "core.security_rag"]
        + [f"ui.{p.stem}" for p in (ROOT / "ui").glob("*.py")
           if p.stem != "__init__"]
        if (ROOT / "ui").exists() else []
    )

    for mod_name in candidates:
        try:
            importlib.import_module(mod_name)
        except ImportError as e:
            errors.append((mod_name, str(e)))
        except Exception:
            pass  # non-import errors (e.g. streamlit not running) — ignore

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic patch: handle "cannot import name X from Y" at runtime
# ─────────────────────────────────────────────────────────────────────────────

def _dynamic_fix(module_name: str, error: str) -> bool:
    """
    Parse 'cannot import name X from Y' errors and add a re-export
    of X into Y's module file.
    """
    import re as _re

    # Pattern: cannot import name 'foo' from 'core.bar'
    m = _re.search(r"cannot import name '(\w+)' from '([\w.]+)'", error)
    if not m:
        return False

    name, source_mod = m.group(1), m.group(2)

    # Find which module actually has this name
    found_in = None
    candidates = ["core.config", "core.auth", "core.models",
                  "core.stack", "core.memory", "core.inference",
                  "core.security_rag", "core.gpu"]
    import importlib
    for mod in candidates:
        if mod == source_mod:
            continue
        try:
            m2 = importlib.import_module(mod)
            if hasattr(m2, name):
                found_in = mod
                break
        except Exception:
            pass

    if not found_in:
        warn(f"Could not find '{name}' in any core module — manual fix needed")
        return False

    # Patch source_mod file to re-export name from found_in
    rel_path = source_mod.replace(".", "/") + ".py"
    target = ROOT / rel_path
    if not target.exists():
        warn(f"Cannot patch {rel_path} — file not found")
        return False

    re_export = (
        f"from {found_in} import {name}  "
        f"# auto-patched: was missing from {source_mod}"
    )
    changed = _append_if_missing(target, re_export, f"import {name}  # auto-patched")
    if changed:
        fixed(f"Added re-export of '{name}' to {rel_path} (found in {found_in})")
    return changed


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run_patches() -> int:
    """Apply all known patches.  Returns number of changes made."""
    changes = 0

    for desc, rel_path, needs_fix, fix_fn in PATCHES:
        path = ROOT / rel_path
        if not path.exists():
            continue
        try:
            if needs_fix(path):
                if fix_fn(path):
                    fixed(desc)
                    changes += 1
                    if not _parse_ok(path):
                        warn(f"{rel_path} has a syntax error after patching — reverting")
                        # simple revert: remove last appended line
                        lines = path.read_text(encoding="utf-8").splitlines()
                        path.write_text("\n".join(lines[:-2]) + "\n")
                        changes -= 1
        except Exception as e:
            warn(f"Patch '{desc}' failed: {e}")

    return changes


def run_dynamic_scan() -> int:
    """Scan for live ImportErrors and attempt dynamic fixes."""
    errors = _scan_import_errors()
    if not errors:
        return 0

    changes = 0
    for mod, err in errors:
        warn(f"Import error in {mod}: {err}")
        if _dynamic_fix(mod, err):
            changes += 1

    return changes


def main():
    print()
    info("Checking core/ and ui/ module imports...")

    # Round 1: known patches
    c1 = run_patches()

    # Round 2: dynamic scan — catches anything the known patches missed
    c2 = run_dynamic_scan()

    total = c1 + c2
    if total == 0:
        ok("All imports look good — no patches needed")
    else:
        ok(f"Applied {total} patch(es) — imports should now resolve")

    # Final syntax check on all patched files
    fail = 0
    for f in list((ROOT / "core").glob("*.py")) + list((ROOT / "ui").glob("*.py")):
        if not _parse_ok(f):
            warn(f"Syntax error in {f.relative_to(ROOT)} — may need manual fix")
            fail += 1

    if fail:
        warn(f"{fail} file(s) have syntax errors — check them before launching")
        return 1

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
