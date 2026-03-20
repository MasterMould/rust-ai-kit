# ui/tab_code.py — Code Generation tab
import streamlit as st

from core.config       import BackendMode, APP_WORKSPACE
from core.inference    import InferenceClient, OllamaClient
from core.security_rag import SecurityValidator

def tab_code(temperature: float):
    st.header("💻 Code Generation")
    c_in, c_out = st.columns(2)

    with c_in:
        prompt = st.text_area("What code do you need?", height=200)
        lang   = st.selectbox("Language",
                              ["Python", "Rust", "Bash", "JavaScript", "Go", "C++", "TypeScript"])
        if st.button("🚀 Generate", type="primary") and prompt:
            msgs = [
                {"role": "system",
                 "content": "You are an expert programmer. Reply with only the code, no prose."},
                {"role": "user",
                 "content": f"Write clean, well-commented {lang} code for:\n{prompt}"},
            ]
            with st.spinner("Generating…"):
                if st.session_state.backend == BackendMode.RUSTAIKIT.value:
                    # Always use direct engine for code gen (no search overhead)
                    resp  = InferenceClient.chat(msgs, use_proxy=False,
                                                 temperature=temperature)
                    reply = InferenceClient.reply(resp)
                else:
                    reply = OllamaClient.chat(msgs, st.session_state.ollama_model,
                                              temperature)
            st.session_state.generated_code = reply
            st.session_state.code_lang      = lang
            st.rerun()

    with c_out:
        if "generated_code" in st.session_state:
            code = st.session_state.generated_code
            lang = st.session_state.get("code_lang", "python")
            st.code(code, language=lang.lower())
            ok, issues = SecurityValidator.validate_code(code)
            if ok:
                st.success("✅ Security scan: pass")
            else:
                st.error(f"🚨 {len(issues)} issue(s):")
                for iss in issues:
                    st.warning(iss)
            fname = st.text_input("Filename:", "output.py")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Save to workspace"):
                    (APP_WORKSPACE / fname).write_text(code)
                    st.success(f"Saved: {APP_WORKSPACE / fname}")
            with c2:
                st.download_button("📥 Download", code, file_name=fname)


# ============================================================================
# TAB: BENCHMARK  (mirrors benchmark() / option 12)
# ============================================================================
