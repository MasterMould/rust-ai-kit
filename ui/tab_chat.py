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

def _send(user_input: str, temperature: float, max_tokens: int):
    username  = st.session_state.username
    sanitized = SecurityValidator.sanitize(user_input)
    is_rak    = st.session_state.backend == BackendMode.RUSTAIKIT.value
    rag_ctx   = mem_ctx = ""
    web_used  = False

    if st.session_state.rag_enabled:
        docs = RAGManager.search(sanitized)
        if docs:
            rag_ctx = "\n\n".join(f"[Doc: {d['filename']}]\n{d['context']}" for d in docs)

    if is_rak and st.session_state.mem_enabled:
        try:
            mem_ctx = MemoryManager.build_context(sanitized, username)
        except Exception:
            pass

    sys_parts = [st.session_state.system_prompt]
    if mem_ctx:
        sys_parts.append(mem_ctx)
    if rag_ctx:
        sys_parts.append(f"## Context from local documents:\n{rag_ctx}")

    messages = [{"role": "system", "content": "\n\n".join(sys_parts)}]
    for m in st.session_state.chat_history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": sanitized})

    # ── Pre-flight: check engine is reachable before touching history ──────────
    if is_rak and not StackManager.engine_running():
        st.session_state._engine_down = True
        return   # tab_chat will show the actionable banner; nothing added to history

    st.session_state._engine_down = False

    with st.spinner("🤔 Thinking…"):
        if is_rak:
            use_proxy = st.session_state.search_enabled
            resp  = InferenceClient.chat(messages, use_proxy, temperature, max_tokens)
            # If both endpoints failed, surface as a UI error — not in chat history
            if "error" in resp:
                st.session_state._last_error = resp["error"]
                st.session_state._engine_down = True
                return
            reply = InferenceClient.reply(resp)
            web_used = use_proxy
        else:
            if not OllamaClient.running():
                st.session_state._engine_down = True
                return
            reply = OllamaClient.chat(messages, st.session_state.ollama_model, temperature)

    # Only write to history on success
    st.session_state.chat_history.append({"role": "user", "content": sanitized})
    st.session_state.chat_history.append({
        "role": "assistant", "content": reply,
        "rag": bool(rag_ctx), "mem": bool(mem_ctx), "web": web_used,
    })

    if is_rak and st.session_state.mem_enabled and StackManager.memory_running():
        try:
            MemoryManager.memorize(
                [{"role": "user", "content": sanitized},
                 {"role": "assistant", "content": reply}],
                username,
            )
        except Exception:
            pass

    # Clear any previous error state on success
    st.session_state._engine_down = False
    st.session_state.pop("_last_error", None)
    audit_log(username, "CHAT", f"backend={st.session_state.backend}")


def tab_chat(temperature: float, max_tokens: int):
    st.header("💬 Chat")

    is_rak = st.session_state.backend == BackendMode.RUSTAIKIT.value
    active_name = (Path(ModelManager.get_active_path()).name
                   if is_rak and ModelManager.get_active_path()
                   else st.session_state.ollama_model or "—")

    # ── Engine health banner ──────────────────────────────────────────────────
    if is_rak:
        engine_ok = StackManager.engine_running()
        proxy_ok  = StackManager.proxy_running()
    else:
        engine_ok = OllamaClient.running()
        proxy_ok  = True  # not applicable

    if not engine_ok:
        st.error(
            "🔴 **Engine offline** — llama-server is not running on "
            f"`localhost:{ENGINE_PORT}`."
        )
        active = ModelManager.get_active_path() if is_rak else ""
        if active:
            c1, c2 = st.columns([2, 5])
            with c1:
                if st.button("▶️ Start engine now", type="primary"):
                    gpu_layers = GPUDetector.gpu_layers()
                    with st.spinner(
                        f"Starting llama-server  (GPU layers={gpu_layers}, up to 90s)…"
                    ):
                        ok, msg = StackManager.start_engine(active, gpu_layers)
                    if ok:
                        st.success(msg)
                        st.session_state._engine_down = False
                        st.session_state.pop("_last_error", None)
                        st.rerun()
                    else:
                        st.error(msg)
                        st.caption(
                            f"Check: `tail -f {STACK_LOG_DIR}/engine.log`  \n"
                            "Common cause: not in `render` group — log out and back in."
                        )
            with c2:
                st.caption(
                    f"Model: `{Path(active).name}`  \n"
                    "Or start the full stack from the **🦀 Stack** tab."
                )
        else:
            st.warning("No model selected. Go to the **🤖 Models** tab to download one.")
        # Show any diagnostic from the last failed attempt
        if st.session_state.get("_last_error"):
            with st.expander("🔍 Connection error detail"):
                st.code(st.session_state["_last_error"])
        # Still render history (read-only) but block input below
        chat_input_disabled = True
    else:
        chat_input_disabled = False
        st.session_state._engine_down = False

    # ── Status strip ──────────────────────────────────────────────────────────
    c = st.columns(5)
    c[0].info(f"**Model:** {active_name[:30]}")
    c[1].info(f"**Backend:** {st.session_state.backend}")
    c[2].info(f"**Temp:** {temperature}")
    c[3].info("🌐 Search ON" if st.session_state.get("search_enabled") and is_rak else "Search OFF")
    c[4].info("🧠 Memory ON" if st.session_state.get("mem_enabled") and is_rak else "Memory OFF")

    # Warn if proxy was down and we fell back to direct engine
    if not chat_input_disabled and is_rak and not proxy_ok and st.session_state.get("search_enabled"):
        st.warning(
            "⚠️ Search proxy (:8090) is offline — sending directly to engine (:8080). "
            "Web search is **disabled**. Start the proxy from the **🦀 Stack** tab."
        )
    elif st.session_state.get("_proxy_fallback"):
        st.warning(
            "⚠️ Last message used direct engine (:8080) — proxy was unreachable. "
            "Web search was disabled for that reply."
        )

    if not st.session_state.chat_history:
        st.markdown(
            "<div style='text-align:center;padding:2rem;color:#888'>"
            "<h3>👋 Start a conversation</h3></div>",
            unsafe_allow_html=True,
        )
    else:
        for msg in st.session_state.chat_history:
            role = msg["role"]
            with st.chat_message(role, avatar="👤" if role == "user" else "🤖"):
                # Render content as markdown — handles code blocks, lists, newlines etc.
                st.markdown(msg["content"])
                # Show augmentation badges below assistant messages
                if role == "assistant":
                    tags = []
                    if msg.get("mem"): tags.append("🧠 mem0")
                    if msg.get("rag"): tags.append("📄 RAG")
                    if msg.get("web"): tags.append("🌐 web")
                    if tags:
                        st.caption("  ·  ".join(tags))

    # st.chat_input stays pinned to the bottom of the page and handles
    # Enter-to-send natively — no rerun key conflicts.
    placeholder = "Type your message…" if not chat_input_disabled else "⚠️ Engine offline — start it above first"
    user_input = st.chat_input(placeholder, disabled=chat_input_disabled)
    if user_input and user_input.strip() and not chat_input_disabled:
        _send(user_input, temperature, max_tokens)
        st.rerun()

    st.divider()
    if st.button("📄 Export as Markdown") and st.session_state.chat_history:
        md = "# Chat Export\n\n"
        for m in st.session_state.chat_history:
            md += f"## {'User' if m['role']=='user' else 'Assistant'}\n\n{m['content']}\n\n"
        st.download_button("⬇️ Download", md,
                           file_name=f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")


# ── Per-service inline controls ───────────────────────────────────────────────
