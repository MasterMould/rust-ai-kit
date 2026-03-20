# ui/tab_memory.py — Memory tab (mem0 + ChromaDB)
import streamlit as st

from core.config import BackendMode
from core.stack  import StackManager
from core.memory import MemoryManager
import pwd as _pwd
import grp as _grp

def tab_memory():
    st.header("🧠 Persistent Memory  (mem0 + ChromaDB)")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.info("Memory requires the rust-ai-kit backend.")
        return
    if not StackManager.memory_running():
        st.error("Memory server offline — start it from the Stack tab.")
        return

    username = st.session_state.username
    mtabs    = st.tabs(["📋 All Memories", "🔍 Semantic Search", "➕ Manual Store"])

    with mtabs[0]:
        if st.button("🔄 Refresh"):
            st.rerun()
        mems = MemoryManager.list_all(username)
        if not mems:
            st.info("No memories yet. Chat with Memory enabled to build them up.")
        else:
            st.success(f"{len(mems)} fact(s) stored for **{username}**")
            for i, m in enumerate(mems):
                text   = m.get("memory", m.get("text", str(m)))
                mem_id = m.get("id", m.get("memory_id", ""))
                with st.expander(f"💡 {text[:90]}{'…' if len(text) > 90 else ''}"):
                    st.write(text)
                    if m.get("created_at"):
                        st.caption(f"Stored: {m['created_at']}")
                    if mem_id and st.button("🗑️ Delete", key=f"delmem_{i}"):
                        if MemoryManager.delete(mem_id, username):
                            st.success("Deleted")
                            st.rerun()

    with mtabs[1]:
        st.caption(
            "Uses sentence-transformers CPU embeddings (~50ms retrieval). "
            "Finds semantically similar facts even if wording differs."
        )
        q     = st.text_input("Search query:")
        top_k = st.slider("Top results", 1, 20, 5)
        if st.button("🔍 Search", type="primary") and q:
            with st.spinner("Searching…"):
                results = MemoryManager.retrieve(q, username, top_k)
            if results:
                for r in results:
                    text  = r.get("memory", r.get("text", str(r)))
                    score = r.get("score", r.get("similarity", ""))
                    prefix = f"**Score:** `{score:.4f}`  \n" if isinstance(score, float) else ""
                    st.markdown(prefix + text)
                    st.divider()
            else:
                st.warning("No matching memories found.")

    with mtabs[2]:
        st.caption(
            "mem0 sends the conversation to llama-server for fact extraction "
            "(one full inference pass, ~25s), then stores distilled facts in ChromaDB."
        )
        u_msg = st.text_area("User turn:", height=80)
        a_msg = st.text_area("Assistant turn:", height=80)
        if st.button("🧠 Store", type="primary") and u_msg.strip():
            with st.spinner("Extracting facts (~25s)…"):
                res = MemoryManager.memorize(
                    [{"role": "user",      "content": u_msg},
                     {"role": "assistant", "content": a_msg or "Noted."}],
                    username,
                )
            if "error" in res:
                st.error(res["error"])
            else:
                st.success("✅ Memories stored")
                st.json(res)


# ============================================================================
# TAB: MODEL MANAGER  (mirrors manage_models + sub-menus)
# ============================================================================
