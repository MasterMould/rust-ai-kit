# ui/tab_chat.py — Chat tab with streaming, edit/regenerate, copy, timestamps, search
import json
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as _components

from core.config       import BackendMode, ENGINE_PORT, STACK_LOG_DIR
from core.auth         import audit_log
from core.gpu          import GPUDetector
from core.stack        import StackManager
from core.models       import ModelManager, ModelConfigManager
from core.memory       import MemoryManager
from core.inference    import InferenceClient, OllamaClient
from core.security_rag import SecurityValidator, RAGManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _active_model_name() -> str:
    if st.session_state.backend == BackendMode.RUSTAIKIT.value:
        p = ModelManager.get_active_path()
        return Path(p).stem if p else "—"
    return st.session_state.get("ollama_model") or "—"


def _copy_button(text: str, key: str):
    """Inline JS clipboard button — no server round-trip."""
    payload = json.dumps(text)   # json.dumps handles all special chars / quotes
    _components.html(
        f"""<button id="cb_{key}"
            onclick="navigator.clipboard.writeText({payload}).then(
                ()=>{{this.innerHTML='&#x2705;';setTimeout(()=>this.innerHTML='&#x1F4CB;',2000)}},
                ()=>this.innerHTML='&#x274C;'
            )"
            style="background:transparent;border:1px solid #bbb;border-radius:4px;
                   padding:1px 7px;cursor:pointer;font-size:0.78rem;color:#555;
                   line-height:1.6">&#x1F4CB;</button>""",
        height=30,
    )


def _build_messages(user_text: str):
    """
    Returns (messages_list, rag_ctx, mem_ctx, web_will_be_used).
    Builds full [system, …history…, user] payload without mutating session state.
    """
    username = st.session_state.username
    is_rak   = st.session_state.backend == BackendMode.RUSTAIKIT.value
    rag_ctx = mem_ctx = ""

    if st.session_state.get("rag_enabled"):
        docs = RAGManager.search(user_text)
        if docs:
            rag_ctx = "\n\n".join(
                f"[Doc: {d['filename']}]\n{d['context']}" for d in docs
            )

    if is_rak and st.session_state.get("mem_enabled"):
        try:
            mem_ctx = MemoryManager.build_context(user_text, username)
        except Exception:
            pass

    sys_parts = [st.session_state.get("system_prompt", "You are a helpful AI assistant.")]
    if mem_ctx:
        sys_parts.append(mem_ctx)
    if rag_ctx:
        sys_parts.append(f"## Context from local documents:\n{rag_ctx}")

    messages = [{"role": "system", "content": "\n\n".join(sys_parts)}]
    for m in st.session_state.chat_history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})

    web_flag = is_rak and st.session_state.get("search_enabled", True)
    return messages, rag_ctx, mem_ctx, web_flag


def _render_message(msg: dict, idx: int, total: int):
    """Render one chat bubble with metadata strip and action buttons."""
    role   = msg["role"]
    avatar = "👤" if role == "user" else "🤖"

    with st.chat_message(role, avatar=avatar):
        st.markdown(msg["content"])

        # metadata strip
        meta = []
        if msg.get("timestamp"):
            meta.append(f"🕐 {msg['timestamp']}")
        if msg.get("model"):
            meta.append(f"🤖 {msg['model']}")
        if role == "assistant":
            if msg.get("mem"):    meta.append("🧠 mem0")
            if msg.get("rag"):    meta.append("📄 RAG")
            if msg.get("web"):    meta.append("🌐 web")
            if msg.get("tokens"): meta.append(f"~{msg['tokens']} tok")
        if meta:
            st.caption("  ·  ".join(meta))

        # action buttons
        btn_cols = st.columns([0.45, 0.45, 0.45, 10])

        with btn_cols[0]:
            _copy_button(msg["content"], f"m{idx}")

        is_last_assistant = role == "assistant" and idx == total - 1
        is_user_msg       = role == "user"

        if is_last_assistant:
            with btn_cols[1]:
                if st.button("🔄", key=f"regen_{idx}", help="Regenerate response"):
                    st.session_state.chat_history.pop()   # remove last assistant
                    if (st.session_state.chat_history and
                            st.session_state.chat_history[-1]["role"] == "user"):
                        last_user = st.session_state.chat_history.pop()
                        st.session_state._pending = last_user["content"]
                    st.rerun()

        if is_user_msg:
            with btn_cols[1]:
                if st.button("✏️", key=f"edit_{idx}", help="Edit & resend"):
                    st.session_state.chat_history = st.session_state.chat_history[:idx]
                    st.session_state._edit_prefill = msg["content"]
                    st.rerun()


# ── Streaming execution ───────────────────────────────────────────────────────

def _execute_pending(user_text: str, temperature: float, max_tokens: int):
    """
    Called when _pending is set.
    Renders user bubble + streams assistant reply inline,
    writes both to chat_history, then reruns.
    """
    username   = st.session_state.username
    sanitized  = SecurityValidator.sanitize(user_text)
    ts         = datetime.now().strftime("%H:%M")
    model_name = _active_model_name()
    is_rak     = st.session_state.backend == BackendMode.RUSTAIKIT.value

    # Show user bubble right away
    with st.chat_message("user", avatar="👤"):
        st.markdown(sanitized)
        st.caption(f"🕐 {ts}")

    # Guard against engine going offline between input and send
    engine_live = StackManager.engine_running() if is_rak else OllamaClient.running()
    if not engine_live:
        st.session_state._engine_down = True
        st.session_state.chat_history.append(
            {"role": "user", "content": sanitized, "timestamp": ts, "model": model_name}
        )
        st.rerun()
        return

    messages, rag_ctx, mem_ctx, web_flag = _build_messages(sanitized)
    use_proxy = st.session_state.get("search_enabled", True)

    full_reply = ""
    with st.chat_message("assistant", avatar="🤖"):
        try:
            if is_rak:
                full_reply = st.write_stream(
                    InferenceClient.stream(messages, use_proxy, temperature, max_tokens)
                )
            else:
                with st.spinner("Thinking…"):
                    full_reply = OllamaClient.chat(
                        messages,
                        st.session_state.get("ollama_model", "llama3"),
                        temperature,
                    )
                st.markdown(full_reply)
        except Exception as e:
            full_reply = f"⚠️ Error: {e}"
            st.error(full_reply)

        tok_est = max(1, len(full_reply) // 4)
        meta = [f"🕐 {datetime.now().strftime('%H:%M')}", f"🤖 {model_name}"]
        if mem_ctx:              meta.append("🧠 mem0")
        if rag_ctx:              meta.append("📄 RAG")
        if web_flag and is_rak:  meta.append("🌐 web")
        meta.append(f"~{tok_est} tok")
        st.caption("  ·  ".join(meta))

    # Commit both turns to history
    st.session_state.chat_history.append(
        {"role": "user", "content": sanitized, "timestamp": ts, "model": model_name}
    )
    st.session_state.chat_history.append({
        "role":      "assistant",
        "content":   full_reply,
        "timestamp": datetime.now().strftime("%H:%M"),
        "model":     model_name,
        "rag":       bool(rag_ctx),
        "mem":       bool(mem_ctx),
        "web":       web_flag and is_rak,
        "tokens":    tok_est,
    })

    # Auto-title from first exchange
    if len(st.session_state.chat_history) == 2 and not st.session_state.get("_chat_title"):
        st.session_state._chat_title = (
            sanitized[:60] + ("…" if len(sanitized) > 60 else "")
        )

    # Persist conversation turn to mem0
    if is_rak and st.session_state.get("mem_enabled") and StackManager.memory_running():
        try:
            MemoryManager.memorize(
                [{"role": "user",      "content": sanitized},
                 {"role": "assistant", "content": full_reply}],
                username,
            )
        except Exception:
            pass

    audit_log(username, "CHAT", f"backend={st.session_state.backend} tokens={tok_est}")
    # Rerun so copy/regen buttons appear on the newly written messages
    st.rerun()


# ── Main tab ──────────────────────────────────────────────────────────────────

def tab_chat(temperature: float, max_tokens: int):
    st.header("💬 Chat")

    is_rak      = st.session_state.backend == BackendMode.RUSTAIKIT.value
    active_name = _active_model_name()

    # ── Engine health banner ──────────────────────────────────────────────────
    engine_ok = StackManager.engine_running() if is_rak else OllamaClient.running()
    proxy_ok  = StackManager.proxy_running()  if is_rak else True

    if not engine_ok:
        st.error(
            f"🔴 **Engine offline** — llama-server not running on `localhost:{ENGINE_PORT}`."
        )
        active = ModelManager.get_active_path() if is_rak else ""
        if active:
            c1, c2 = st.columns([2, 5])
            with c1:
                if st.button("▶️ Start engine now", type="primary"):
                    gpu_layers = GPUDetector.gpu_layers()
                    cfg = ModelConfigManager.load(active)
                    with st.spinner(f"Starting (GPU layers={gpu_layers}, up to 90 s)…"):
                        ok, msg = StackManager.start_engine(active, gpu_layers, cfg)
                    if ok:
                        st.success(msg)
                        st.session_state._engine_down = False
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
            st.warning("No model selected. Go to **🤖 Models** to download one.")
        if st.session_state.get("_last_error"):
            with st.expander("🔍 Connection error detail"):
                st.code(st.session_state["_last_error"])
        chat_input_disabled = True
    else:
        chat_input_disabled = False
        st.session_state._engine_down = False
        st.session_state.pop("_last_error", None)

    # ── Status strip ──────────────────────────────────────────────────────────
    cols = st.columns(5)
    cols[0].info(f"**Model:** {active_name[:28]}")
    cols[1].info(f"**Backend:** {st.session_state.backend}")
    cols[2].info(f"**Temp:** {temperature}")
    cols[3].info(
        "🌐 Search ON" if st.session_state.get("search_enabled") and is_rak
        else "Search OFF"
    )
    cols[4].info(
        "🧠 Memory ON" if st.session_state.get("mem_enabled") and is_rak
        else "Memory OFF"
    )

    if not chat_input_disabled and is_rak \
            and not proxy_ok and st.session_state.get("search_enabled"):
        st.warning(
            "⚠️ Search proxy (:8090) offline — web search disabled. "
            "Start it from the **🦀 Stack** tab."
        )
    elif st.session_state.get("_proxy_fallback"):
        st.warning(
            "⚠️ Last reply used direct engine (:8080) — proxy was unreachable. "
            "Web search was skipped for that message."
        )

    # ── Conversation title + inline search ───────────────────────────────────
    history = st.session_state.chat_history
    search_q = ""

    if history:
        col_title, col_search = st.columns([3, 1])
        with col_title:
            title     = st.session_state.get("_chat_title", "New conversation")
            new_title = st.text_input(
                "Conversation title",
                value=title,
                label_visibility="collapsed",
                key="_chat_title_input",
            )
            if new_title != title:
                st.session_state._chat_title = new_title
        with col_search:
            search_q = st.text_input(
                "Search",
                placeholder="🔍 Search messages…",
                label_visibility="collapsed",
                key="_chat_search",
            )

    # ── Message display ───────────────────────────────────────────────────────
    if search_q:
        hits = [(i, m) for i, m in enumerate(history)
                if search_q.lower() in m["content"].lower()]
        if hits:
            st.caption(f"Found **{len(hits)}** message(s) matching `{search_q}`")
            for i, msg in hits:
                _render_message(msg, i, len(history))
        else:
            st.info(f"No messages contain `{search_q}`.")
    elif not history:
        st.markdown(
            "<div style='text-align:center;padding:3rem 1rem;color:#999'>"
            "<h3 style='margin-bottom:.5rem'>👋 Start a conversation</h3>"
            "<p>Responses stream in real time — use ✏️ to edit any message, "
            "🔄 to regenerate the last reply</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        for i, msg in enumerate(history):
            _render_message(msg, i, len(history))

    # ── Execute any pending message (streaming) ───────────────────────────────
    if st.session_state.get("_pending") and not chat_input_disabled:
        user_text = st.session_state.pop("_pending")
        _execute_pending(user_text, temperature, max_tokens)
        # _execute_pending always calls st.rerun() — nothing below runs

    # ── Edit form ─────────────────────────────────────────────────────────────
    if st.session_state.get("_edit_prefill") is not None:
        st.divider()
        st.markdown("**✏️ Edit message**")
        edited = st.text_area(
            "Edit",
            value=st.session_state["_edit_prefill"],
            height=90,
            label_visibility="collapsed",
            key="_edit_area",
        )
        c_send, c_cancel, _ = st.columns([1, 1, 6])
        with c_send:
            if st.button("↩️ Resend", type="primary"):
                val = st.session_state.get("_edit_area", "").strip() or edited.strip()
                st.session_state.pop("_edit_prefill")
                st.session_state._pending = val
                st.rerun()
        with c_cancel:
            if st.button("✕ Cancel"):
                st.session_state.pop("_edit_prefill")
                st.rerun()

    # ── Chat input ────────────────────────────────────────────────────────────
    placeholder = (
        "Type your message…" if not chat_input_disabled
        else "⚠️ Engine offline — start it above first"
    )
    user_input = st.chat_input(placeholder, disabled=chat_input_disabled)
    if user_input and user_input.strip() and not chat_input_disabled:
        st.session_state.pop("_edit_prefill", None)
        st.session_state._pending = user_input.strip()
        st.rerun()

    # ── Footer ────────────────────────────────────────────────────────────────
    st.divider()
    col_md, col_json, col_stats = st.columns([1, 1, 3])

    with col_md:
        if st.button("📄 Export Markdown") and history:
            title  = st.session_state.get("_chat_title", "Chat")
            lines  = [f"# {title}\n"]
            for m in history:
                label    = "User" if m["role"] == "user" else "Assistant"
                ts_part  = f" _{m['timestamp']}_" if m.get("timestamp") else ""
                lines.append(f"## {label}{ts_part}\n\n{m['content']}\n")
            st.download_button(
                "⬇️ Download .md", "\n".join(lines),
                file_name=f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
            )

    with col_json:
        if st.button("📦 Export JSON") and history:
            st.download_button(
                "⬇️ Download .json",
                json.dumps(history, indent=2),
                file_name=f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

    with col_stats:
        if history:
            exchanges = sum(1 for m in history if m["role"] == "user")
            total_tok = sum(m.get("tokens", 0) for m in history)
            last_model = next(
                (m.get("model", "—") for m in reversed(history) if m.get("model")), "—"
            )
            st.caption(
                f"💬 {exchanges} exchange(s)  ·  "
                f"~{total_tok} total tokens  ·  "
                f"🤖 {last_model}"
            )
