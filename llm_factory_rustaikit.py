"""
rust-ai-kit LLM Factory — entry point.
Usage:
    python3 llm_factory_rustaikit.py   ← auto-relaunches via venv/bin/streamlit
    make run                           ← recommended
    ./launch.sh                        ← start everything + open browser
"""
import sys
import os
import subprocess
from pathlib import Path

_here     = Path(__file__).parent.resolve()
_venv_st  = _here / "venv" / "bin" / "streamlit"
_streamlit = str(_venv_st) if _venv_st.exists() else "streamlit"


def _inside_streamlit() -> bool:
    """
    Detect whether this module is executing inside a running Streamlit session.
    Uses the official Streamlit API — returns True only when the ScriptRunner
    thread-local context is active (i.e. streamlit has already set us up).
    Falls back to False on any import error so older Streamlit versions work.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        pass
    # Older streamlit (<1.12) used a different path
    try:
        from streamlit.script_run_context import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if not _inside_streamlit():
    # ── Not inside Streamlit yet — re-exec via streamlit run ─────────────────
    try:
        sys.exit(
            subprocess.call(
                [_streamlit, "run", str(Path(__file__).resolve())] + sys.argv[1:]
            )
        )
    except FileNotFoundError:
        print(
            f"\n  ❌  Streamlit not found at: {_streamlit}\n"
            f"\n  Fix:\n"
            f"    cd {_here}\n"
            f"    make setup\n"
            f"    make run\n",
            file=sys.stderr,
        )
        sys.exit(1)
else:
    # ── Inside Streamlit — import and run the app ─────────────────────────────
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))

    try:
        from ui.app import main
        main()
    except ModuleNotFoundError as exc:
        # core/ and ui/ packages missing — refactor not yet applied.
        # Fall back to the monolith .bak if available.
        _bak = _here / "llm_factory_rustaikit.py.bak"
        if _bak.exists():
            import importlib.util as _ilu
            import streamlit as st
            st.warning(
                f"⚠️ `core/` and `ui/` packages not found — loading monolith backup.  \n"
                f"Run `python3 refactor.py --apply` to complete the split."
            )
            _spec = _ilu.spec_from_file_location("_monolith", str(_bak))
            _mod  = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
        else:
            import streamlit as st
            st.error(
                f"**Import failed:** `{exc}`  \n\n"
                f"The `core/` and `ui/` packages are missing.  \n"
                f"Run:  `python3 refactor.py --apply`  \n"
                f"Or restore the monolith:  "
                f"`cp llm_factory_rustaikit.py.bak llm_factory_rustaikit.py`"
            )
