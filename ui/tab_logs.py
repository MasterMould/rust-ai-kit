# ui/tab_logs.py — Log viewer tab (audit + engine/memory/proxy)
import streamlit as st

from core.config import BackendMode, STACK_LOG_DIR
from core.auth   import AUDIT_LOG
from core.stack  import StackManager

def tab_logs():
    st.header("📜 Logs")
    ltabs = st.tabs(["Audit (app)", "engine.log", "memory.log", "proxy.log"])

    with ltabs[0]:
        if AUDIT_LOG.exists():
            n = st.slider("Lines", 10, 200, 50, key="audit_n")
            lines = AUDIT_LOG.read_text().splitlines()
            st.text_area("", "\n".join(reversed(lines[-n:])), height=400)
        else:
            st.info("No audit log yet.")

    for i, name in enumerate(["engine", "memory", "proxy"]):
        with ltabs[i + 1]:
            n = st.slider("Lines", 20, 300, 80, key=f"logn_{name}")
            if st.session_state.backend == BackendMode.RUSTAIKIT.value:
                out = StackManager.tail_log(name, n)
                st.text_area("", out, height=400)
                st.caption(f"`{STACK_LOG_DIR}/{name}.log`")
            else:
                st.info("Stack logs only available in rust-ai-kit mode.")


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    main()
