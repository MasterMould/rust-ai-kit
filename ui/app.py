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

st.set_page_config(
    page_title="🦀 LLM Factory · rust-ai-kit",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown("""
<style>
.chat-message      { padding:1rem; border-radius:.5rem; margin-bottom:1rem; }
.user-message      { background:#e3f2fd; border-left:4px solid #2196f3; }
.assistant-message { background:#f5f5f5; border-left:4px solid #4caf50; }
.badge  { display:inline-block; border-radius:.3rem; padding:.15rem .45rem;
          font-size:.72rem; margin-right:.3rem; }
.b-mem  { background:#fff3e0; border:1px solid #ff9800; }
.b-rag  { background:#e8f5e9; border:1px solid #43a047; }
.b-web  { background:#e3f2fd; border:1px solid #1976d2; }
.ok     { color:#2e7d32; font-weight:bold; }
.err    { color:#c62828; font-weight:bold; }
.mono   { font-family:monospace; font-size:.85rem; }
.chat-header { font-weight:bold; margin-bottom:.35rem; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# AUTH
# ============================================================================
def check_auth() -> bool:
    return st.session_state.get("authenticated", False)


def show_login():
    st.title("🦀 LLM Factory — rust-ai-kit Edition")
    _, col, _ = st.columns([1, 2, 1])
    with col:
        if AuthManager.pam_available():
            st.info("🐧 **Sign in with your Linux system account**")
        else:
            st.info("🔑 **Local accounts active** — default: `admin` / `admin123`")
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("🔓 Login"):
                ok, role = AuthManager.authenticate(u, p)
                if ok:
                    st.session_state.update({
                        "authenticated": True, "username": u,
                        "role": role, "login_time": datetime.now(),
                    })
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials")


def init_session():
    defs = {
        "chat_history":  [],
        "system_prompt": "You are a helpful AI assistant.",
        "rag_enabled":   False,
        "mem_enabled":   True,
        "search_enabled": True,
        "backend":       BackendMode.RUSTAIKIT.value,
        "ollama_model":  "",
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================================
# MAIN
# ============================================================================
def main():
    if not check_auth():
        show_login()
        return
    init_session()

    with st.sidebar:
        st.title("🦀 LLM Factory")
        st.caption(f"**{st.session_state.username}** · {st.session_state.role.upper()}")
        if st.button("🚪 Logout"):
            audit_log(st.session_state.username, "LOGOUT", "")
            for k in list(st.session_state):
                del st.session_state[k]
            st.rerun()

        st.divider()
        backend = st.radio("Engine", [BackendMode.RUSTAIKIT.value, BackendMode.OLLAMA.value],
                           index=0 if st.session_state.backend == BackendMode.RUSTAIKIT.value else 1,
                           horizontal=True)
        st.session_state.backend = backend

        st.divider()
        st.subheader("🤖 Active Model")

        if backend == BackendMode.RUSTAIKIT.value:
            active_path = ModelManager.get_active_path()
            active_name = Path(active_path).name if active_path else "none"
            if active_path:
                st.success(f"**{active_name}**")
            else:
                st.error("No model — use Model Manager")
            st.session_state.search_enabled = st.toggle(
                "🌐 Web search (:8090)",
                value=st.session_state.search_enabled,
                help="Routes via search_proxy.py which auto-injects SearXNG results",
            )
            st.session_state.mem_enabled = st.toggle(
                "🧠 Persistent memory",
                value=st.session_state.mem_enabled,
                help="Retrieves mem0 facts and prepends them to the system prompt",
            )
        else:
            if OllamaClient.running():
                st.success("✅ Ollama running")
                models = OllamaClient.models()
                st.session_state.ollama_model = (
                    st.selectbox("Model", models) if models
                    else st.text_input("Model:", "llama3")
                )
            else:
                st.error("❌ Ollama offline")
                st.code("ollama serve")
                st.session_state.ollama_model = st.text_input("Model:", "llama3")

        st.divider()
        st.subheader("⚙️ Generation")
        temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
        max_tokens  = st.slider("Max tokens",  256, 4096, 2048, 128)

        st.session_state.rag_enabled = st.checkbox(
            "📄 Local RAG", value=st.session_state.rag_enabled,
            help="Keyword search over uploaded documents"
        )
        if st.session_state.rag_enabled:
            st.caption(f"📚 {len(RAGManager.list_docs())} docs")

        with st.expander("System prompt"):
            sp = st.text_area("", value=st.session_state.system_prompt, height=100)
            if st.button("Update"):
                st.session_state.system_prompt = sp
                st.success("Updated")

        st.divider()
        st.subheader("💾 Conversation")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()
        with c2:
            if st.button("💾 Save", use_container_width=True):
                if st.session_state.chat_history:
                    d = CHAT_HISTORY_DIR / st.session_state.username
                    d.mkdir(exist_ok=True)
                    fn = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    (d / fn).write_text(json.dumps(st.session_state.chat_history, indent=2))
                    st.success("Saved")

    tabs = st.tabs([
        "💬 Chat", "🦀 Stack", "🧠 Memory", "🤖 Models",
        "📚 RAG", "💻 Code", "📊 Benchmark", "🛡️ Security", "👥 Users", "📜 Logs",
    ])
    with tabs[0]: tab_chat(temperature, max_tokens)
    with tabs[1]: tab_stack()
    with tabs[2]: tab_memory()
    with tabs[3]: tab_models()
    with tabs[4]: tab_rag()
    with tabs[5]: tab_code(temperature)
    with tabs[6]: tab_benchmark()
    with tabs[7]: tab_security()
    with tabs[8]: tab_users()
    with tabs[9]: tab_logs()


# ============================================================================
# TAB: CHAT
# ============================================================================
