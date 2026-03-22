# ui/tab_rag.py — Local RAG Documents tab (admin-aware)
import streamlit as st

from core.config       import (
    APP_WORKSPACE, ADMIN_ALLOWED_EXTENSIONS, SecurityLevel
)
from core.auth         import audit_log
from core.security_rag import RAGManager


def _is_admin() -> bool:
    return st.session_state.get("role") == SecurityLevel.ADMIN.value


def tab_rag():
    st.header("📚 Local RAG Documents")

    is_admin = _is_admin()
    if is_admin:
        st.info(
            "🔓 **Admin mode** — all file types accepted, "
            "up to 100 MB per file, extended search options enabled."
        )

    rtabs = st.tabs(["📤 Upload", "📋 Manage", "🔍 Search Test"])

    # ── Upload ────────────────────────────────────────────────────────────────
    with rtabs[0]:
        if is_admin:
            st.caption(
                "Admin: any file type accepted. "
                "Jupyter notebooks, archives, code files, binaries all supported."
            )
            # Admin: unrestricted file types
            files = st.file_uploader(
                "Upload documents",
                accept_multiple_files=True,
                # No `type=` restriction for admin
            )
            raw_mode = st.checkbox(
                "⚡ Raw mode",
                value=False,
                help="Skip content sanitisation — store file content exactly as-is. "
                     "Useful for binary files, proprietary formats, or logs."
            )
        else:
            st.caption("Accepted: PDF, Markdown, plain text, JSON, YAML.")
            files = st.file_uploader(
                "Upload documents",
                accept_multiple_files=True,
                type=["txt", "md", "pdf", "json", "yaml"],
            )
            raw_mode = False

        if files and st.button("Process all", type="primary"):
            bar = st.progress(0)
            results = []
            for i, f in enumerate(files):
                tmp = APP_WORKSPACE / f.name
                tmp.write_bytes(f.getbuffer())
                ok, msg = RAGManager.process(tmp, f.name, is_admin=is_admin)
                tmp.unlink(missing_ok=True)
                results.append((f.name, ok, msg))
                bar.progress((i + 1) / len(files))

            for name, success, msg in results:
                if success:
                    st.success(f"✅ {name}: {msg}")
                else:
                    st.error(f"❌ {name}: {msg}")
                audit_log(st.session_state.get("username", "?"), "RAG_UPLOAD", name, success)

    # ── Manage ────────────────────────────────────────────────────────────────
    with rtabs[1]:
        docs = RAGManager.list_docs()
        if not docs:
            st.info("No documents yet.")
        else:
            st.success(f"{len(docs)} document(s) stored")

            # Admin: bulk-select checkboxes + bulk delete
            if is_admin:
                st.caption("Admin: select documents and bulk-delete, or re-index all.")
                selected = []
                for doc in docs:
                    col_chk, col_info, col_del = st.columns([0.5, 5, 1])
                    with col_chk:
                        if st.checkbox("", key=f"chk_{doc['filename']}"):
                            selected.append(doc["filename"])
                    with col_info:
                        st.markdown(
                            f"**{doc['filename']}**  "
                            f"— {doc.get('size', 0):,} chars  "
                            f"— {doc.get('uploaded', '')[:10]}"
                            + (" *(admin upload)*" if doc.get("is_admin") else "")
                        )
                    with col_del:
                        if st.button("🗑️", key=f"deldoc_{doc['filename']}"):
                            RAGManager.delete(doc["filename"])
                            audit_log(
                                st.session_state.get("username", "?"),
                                "RAG_DELETE", doc["filename"]
                            )
                            st.rerun()

                col_bulk, col_reindex = st.columns(2)
                with col_bulk:
                    if selected and st.button(
                        f"🗑️ Delete {len(selected)} selected", type="primary"
                    ):
                        ok_n, fail_n = RAGManager.bulk_delete(selected)
                        st.success(f"Deleted {ok_n} document(s)")
                        if fail_n:
                            st.warning(f"{fail_n} failed")
                        audit_log(
                            st.session_state.get("username", "?"),
                            "RAG_BULK_DELETE", f"{ok_n} files"
                        )
                        st.rerun()
                with col_reindex:
                    if st.button("🔄 Re-index all"):
                        ok_n, fail_n = RAGManager.reindex_all(is_admin=True)
                        st.success(f"Re-indexed {ok_n} document(s)")
                        if fail_n:
                            st.warning(f"{fail_n} failed")
            else:
                # Standard user — simple list with individual delete
                for doc in docs:
                    with st.expander(f"📄 {doc['filename']}"):
                        c1, c2 = st.columns([4, 1])
                        c1.markdown(
                            f"Uploaded: {doc.get('uploaded', '?')}  \n"
                            f"Size: {doc.get('size', 0):,} chars"
                        )
                        with c2:
                            if st.button("🗑️ Delete", key=f"deldoc_{doc['filename']}"):
                                RAGManager.delete(doc["filename"])
                                audit_log(
                                    st.session_state.get("username", "?"),
                                    "RAG_DELETE", doc["filename"]
                                )
                                st.rerun()

    # ── Search Test ───────────────────────────────────────────────────────────
    with rtabs[2]:
        q = st.text_input("Test query:")

        col_res, col_full = st.columns([2, 1])
        with col_res:
            max_r = st.slider(
                "Max results", 1, 50 if is_admin else 10,
                5 if is_admin else 3,
                help="Admin can retrieve up to 50 results."
            )
        with col_full:
            show_full = False
            if is_admin:
                show_full = st.checkbox(
                    "Show full content",
                    value=False,
                    help="Admin: display the complete document text, not just the matched snippet."
                )

        if st.button("🔍 Search") and q:
            results = RAGManager.search(
                q, max_results=max_r, full_content=show_full
            )
            if results:
                st.success(f"{len(results)} result(s)")
                for r in results:
                    fname = r["filename"]
                    score = r["score"]
                    st.markdown(f"**{fname}** — score {score}")
                    st.info(r["context"])
                    if show_full and r.get("full_content"):
                        with st.expander("Full document content"):
                            st.text(r["full_content"][:20000])
                    st.divider()
            else:
                st.warning("No matches found.")
