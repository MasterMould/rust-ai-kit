# ui/tab_rag.py — Local RAG Documents tab
import streamlit as st

from core.config       import APP_WORKSPACE
from core.auth         import audit_log
from core.security_rag import RAGManager

def tab_rag():
    st.header("📚 Local RAG Documents")
    rtabs = st.tabs(["📤 Upload", "📋 Manage", "🔍 Search Test"])

    with rtabs[0]:
        files = st.file_uploader("Upload documents", accept_multiple_files=True,
                                 type=["txt", "md", "pdf", "json", "yaml"])
        if files and st.button("Process all", type="primary"):
            bar = st.progress(0)
            for i, f in enumerate(files):
                tmp = APP_WORKSPACE / f.name
                tmp.write_bytes(f.getbuffer())
                ok, msg = RAGManager.process(tmp, f.name)
                tmp.unlink(missing_ok=True)
                (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {f.name}: {msg}")
                audit_log(st.session_state.username, "RAG_UPLOAD", f.name, ok)
                bar.progress((i + 1) / len(files))

    with rtabs[1]:
        docs = RAGManager.list_docs()
        if not docs:
            st.info("No documents yet.")
        for doc in docs:
            with st.expander(f"📄 {doc['filename']}"):
                c1, c2 = st.columns([4, 1])
                c1.markdown(
                    f"Uploaded: {doc.get('uploaded','?')}  \n"
                    f"Size: {doc.get('size',0):,} chars"
                )
                with c2:
                    if st.button("🗑️ Delete", key=f"deldoc_{doc['filename']}"):
                        RAGManager.delete(doc["filename"])
                        st.rerun()

    with rtabs[2]:
        q = st.text_input("Test query:")
        if st.button("🔍 Search") and q:
            for r in RAGManager.search(q, max_results=5):
                st.markdown(f"**{r['filename']}** — score {r['score']}")
                st.info(r["context"])
                st.divider()
            if not RAGManager.search(q, max_results=1):
                st.warning("No matches found.")


# ============================================================================
# TAB: CODE GENERATION
# ============================================================================
