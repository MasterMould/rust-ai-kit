# ui/tab_rag.py — Local RAG Documents: upload, manage, search, preview
import streamlit as st

from core.config       import APP_WORKSPACE, RAG_DOCS_DIR
from core.auth         import audit_log
from core.security_rag import RAGManager

_ACCEPTED = ["txt", "md", "pdf", "json", "yaml", "yml", "csv", "py", "rst"]


def tab_rag():
    st.header("📚 Local RAG Documents")

    docs = RAGManager.list_docs()
    c1, c2, c3 = st.columns(3)
    c1.metric("Documents indexed", len(docs))
    c2.metric("Total chunks", sum(d.get("chunk_count", 0) for d in docs))
    c3.metric("Total size", _human(sum(d.get("size", 0) for d in docs)))

    st.divider()
    rtabs = st.tabs(["📤 Upload", "📋 Manage & Preview", "🔍 Search"])

    # ── Upload ────────────────────────────────────────────────────────────────
    with rtabs[0]:
        st.caption(
            f"Accepted: {', '.join(f'`.{e}`' for e in _ACCEPTED)}  \n"
            "Uploaded documents are chunked (~400 chars) and indexed for keyword retrieval. "
            "They are injected into chat prompts when **📄 Local RAG** is enabled in the sidebar."
        )
        files = st.file_uploader(
            "Drop files here or click to browse",
            accept_multiple_files=True,
            type=_ACCEPTED,
            label_visibility="collapsed",
        )

        if files:
            already = {d["filename"] for d in docs}
            new_files  = [f for f in files if f.name not in already]
            dupe_files = [f for f in files if f.name in already]

            if dupe_files:
                with st.expander(f"⚠️ {len(dupe_files)} file(s) already indexed"):
                    for f in dupe_files:
                        st.caption(f"• `{f.name}` — already exists, will be replaced if you proceed")

            col_proc, col_skip, _ = st.columns([1, 1, 4])
            with col_proc:
                do_all = st.button(
                    f"✅ Process {len(files)} file(s)",
                    type="primary",
                    disabled=not files,
                )
            with col_skip:
                do_new = st.button(
                    f"➕ New only ({len(new_files)})",
                    disabled=not new_files,
                )

            to_process = files if do_all else (new_files if do_new else [])
            if to_process:
                bar = st.progress(0, text="Processing…")
                for i, f in enumerate(to_process):
                    tmp = APP_WORKSPACE / f.name
                    tmp.write_bytes(f.getbuffer())
                    ok, msg = RAGManager.process(tmp, f.name)
                    tmp.unlink(missing_ok=True)
                    if ok:
                        st.success(f"✅ `{f.name}` — {msg}")
                    else:
                        st.error(f"❌ `{f.name}` — {msg}")
                    audit_log(st.session_state.username, "RAG_UPLOAD", f.name, ok)
                    bar.progress((i + 1) / len(to_process),
                                 text=f"Processed {i+1}/{len(to_process)}…")
                bar.progress(1.0, text="Done!")
                st.rerun()

    # ── Manage & Preview ──────────────────────────────────────────────────────
    with rtabs[1]:
        if not docs:
            st.info("No documents indexed yet. Upload some in the **Upload** tab.")
        else:
            # Sort control
            sort_by = st.selectbox(
                "Sort by", ["Newest first", "Oldest first", "Name A→Z", "Largest first"],
                label_visibility="collapsed",
            )
            sorted_docs = _sort_docs(docs, sort_by)

            for doc in sorted_docs:
                fname  = doc["filename"]
                size   = _human(doc.get("size", 0))
                chunks = doc.get("chunk_count", "?")
                ts     = doc.get("uploaded", "")[:16].replace("T", " ")
                sfx    = doc.get("suffix", "")

                with st.expander(f"{_file_icon(sfx)} **{fname}**  ·  {size}  ·  {chunks} chunks"):
                    col_meta, col_actions = st.columns([3, 1])
                    with col_meta:
                        st.caption(f"Uploaded: {ts}  ·  Suffix: `{sfx}`")

                    with col_actions:
                        if st.button("🗑️ Delete", key=f"del_{fname}"):
                            RAGManager.delete(fname)
                            audit_log(st.session_state.username, "RAG_DELETE", fname)
                            st.rerun()
                        st.download_button(
                            "⬇️ Download",
                            data=RAGManager.get_content(fname).encode(),
                            file_name=fname,
                            mime="text/plain",
                            key=f"dl_{fname}",
                        )

                    # Full text preview
                    content = RAGManager.get_content(fname)
                    if content:
                        preview_lines = st.slider(
                            "Preview lines", 5, 100, 20,
                            key=f"prev_{fname}",
                        )
                        preview = "\n".join(content.splitlines()[:preview_lines])
                        st.text_area(
                            "", value=preview, height=200,
                            label_visibility="collapsed",
                            key=f"ta_{fname}",
                        )
                        if len(content.splitlines()) > preview_lines:
                            st.caption(
                                f"Showing first {preview_lines} of "
                                f"{len(content.splitlines())} lines."
                            )

    # ── Search ────────────────────────────────────────────────────────────────
    with rtabs[2]:
        st.caption(
            "TF-IDF ranked search across all indexed documents. "
            "Results show the most relevant chunk from each document, "
            "with relevance score. This is the same search used during chat."
        )
        col_q, col_n = st.columns([4, 1])
        with col_q:
            q = st.text_input(
                "Search query",
                placeholder="e.g. quarterly revenue, installation steps, API key…",
                label_visibility="collapsed",
            )
        with col_n:
            max_r = st.number_input("Max results", 1, 20, 5, label_visibility="collapsed")

        if st.button("🔍 Search", type="primary", disabled=not q) and q:
            with st.spinner("Searching…"):
                results = RAGManager.search(q, max_results=int(max_r))

            if not results:
                st.warning("No matching chunks found. Try broader terms or check your documents.")
            else:
                st.success(f"Found {len(results)} result(s) for `{q}`")
                for i, r in enumerate(results):
                    score_pct = min(int(r["score"] * 1000), 100)
                    with st.expander(
                        f"#{i+1}  📄 **{r['filename']}**  "
                        f"·  chunk {r['chunk_idx']+1}/{r['total_chunks']}  "
                        f"·  relevance {score_pct}%"
                    ):
                        st.markdown(r["context"])
                        st.caption(f"Raw TF-IDF score: `{r['score']}`")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _human(n: int) -> str:
    if n < 1024:      return f"{n} B"
    if n < 1_048_576: return f"{n/1024:.1f} KB"
    return f"{n/1_048_576:.1f} MB"


def _file_icon(suffix: str) -> str:
    return {
        ".pdf": "📕", ".md": "📝", ".txt": "📄", ".py": "🐍",
        ".json": "🔧", ".yaml": "🔧", ".yml": "🔧",
        ".csv": "📊", ".rst": "📄",
    }.get(suffix.lower(), "📄")


def _sort_docs(docs, by: str) -> list:
    if by == "Newest first":   return docs  # already sorted newest first
    if by == "Oldest first":   return list(reversed(docs))
    if by == "Name A→Z":       return sorted(docs, key=lambda d: d["filename"].lower())
    if by == "Largest first":  return sorted(docs, key=lambda d: d.get("size", 0), reverse=True)
    return docs
