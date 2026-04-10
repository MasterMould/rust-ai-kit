# ui/tab_code.py — Code Generation: generate, explain, fix, history, streaming
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from core.config       import BackendMode, APP_WORKSPACE, APP_LOG_DIR
from core.inference    import InferenceClient, OllamaClient
from core.security_rag import SecurityValidator
from core.auth         import audit_log

_HISTORY_FILE = APP_LOG_DIR / "code_history.json"
_LANGUAGES    = ["Python", "Rust", "Bash", "JavaScript", "TypeScript",
                 "Go", "C++", "C", "SQL", "HTML/CSS", "Dockerfile", "YAML"]
_MODES = {
    "✨ Generate":  "Write clean, well-commented {lang} code for:\n{prompt}",
    "🔍 Explain":  "Explain the following {lang} code clearly, line by line where needed:\n\n```{lang_lower}\n{prompt}\n```",
    "🐛 Fix":      "Find and fix all bugs in the following {lang} code. "
                   "Show only the corrected code with brief comments explaining each fix:\n\n"
                   "```{lang_lower}\n{prompt}\n```",
    "🧪 Add tests":"Write thorough unit tests for the following {lang} code using the "
                   "standard testing framework for that language:\n\n"
                   "```{lang_lower}\n{prompt}\n```",
    "📝 Document": "Add clear docstrings, type hints (where applicable), and inline "
                   "comments to the following {lang} code:\n\n"
                   "```{lang_lower}\n{prompt}\n```",
}

# ── History ───────────────────────────────────────────────────────────────────

def _load_history() -> list:
    if _HISTORY_FILE.exists():
        try:
            return json.loads(_HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def _save_entry(mode: str, lang: str, prompt: str, code: str):
    hist = _load_history()
    hist.append({
        "time":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode":   mode,
        "lang":   lang,
        "prompt": prompt[:200],
        "code":   code,
    })
    try:
        _HISTORY_FILE.write_text(json.dumps(hist[-30:], indent=2))
    except Exception:
        pass


# ── Main tab ──────────────────────────────────────────────────────────────────

def tab_code(temperature: float):
    st.header("💻 Code Generation")

    ctabs = st.tabs(["⚡ Generate / Edit", "🕑 History", "🗂️ Workspace"])

    # ── Generate / Edit ───────────────────────────────────────────────────────
    with ctabs[0]:
        col_opts, col_out = st.columns([1, 1])

        with col_opts:
            mode = st.radio(
                "Mode", list(_MODES.keys()),
                horizontal=True,
                help="Generate: write new code.  Explain: break down existing code.  "
                     "Fix: find & patch bugs.  Tests: write unit tests.  "
                     "Document: add docstrings & comments.",
            )
            lang = st.selectbox("Language", _LANGUAGES, key="code_lang_sel")

            is_explain_mode = mode in ("🔍 Explain", "🐛 Fix", "🧪 Add tests", "📝 Document")
            placeholder = (
                "Paste your code here…" if is_explain_mode
                else f"Describe the {lang} code you need…"
            )
            prompt = st.text_area(
                "Input",
                height=250,
                placeholder=placeholder,
                label_visibility="collapsed",
                key="code_prompt",
            )

            col_btn, col_temp = st.columns([1, 1])
            with col_btn:
                go = st.button("🚀 Run", type="primary", disabled=not prompt.strip())
            with col_temp:
                code_temp = st.slider(
                    "Creativity", 0.0, 1.0,
                    0.1 if is_explain_mode else 0.2,
                    0.05,
                    help="Lower = more deterministic code. Higher = more creative.",
                )

        with col_out:
            if go and prompt.strip():
                lang_lower = lang.lower().replace("/", "_").replace(" ", "_")
                user_content = _MODES[mode].format(
                    lang=lang, lang_lower=lang_lower, prompt=prompt.strip()
                )
                msgs = [
                    {"role": "system",
                     "content": "You are an expert programmer. Reply with only the requested output — "
                                "no preamble, no prose, no markdown wrapper unless it is the result itself."},
                    {"role": "user", "content": user_content},
                ]

                reply_box = st.empty()
                full_reply = ""

                with st.spinner(f"Running {mode}…"):
                    is_rak = st.session_state.backend == BackendMode.RUSTAIKIT.value
                    if is_rak:
                        for delta in InferenceClient.stream(
                            msgs, use_proxy=False,
                            temperature=code_temp, max_tokens=2048,
                        ):
                            full_reply += delta
                            # Show as code block while streaming
                            reply_box.code(full_reply, language=lang_lower)
                    else:
                        full_reply = OllamaClient.chat(
                            msgs, st.session_state.get("ollama_model", "llama3"),
                            code_temp,
                        )
                        reply_box.code(full_reply, language=lang_lower)

                # Strip accidental markdown fences if model wrapped anyway
                clean = _strip_fences(full_reply)
                st.session_state["_code_result"] = clean
                st.session_state["_code_lang"]   = lang
                st.session_state["_code_mode"]   = mode

                _save_entry(mode, lang, prompt.strip(), clean)
                audit_log(
                    st.session_state.get("username", "system"),
                    "CODE_GEN", f"mode={mode} lang={lang}", True,
                )
                st.rerun()   # re-render so action buttons appear

            elif "  _code_result" in st.session_state or "_code_result" in st.session_state:
                code    = st.session_state.get("_code_result", "")
                disp_lang = st.session_state.get("_code_lang", lang).lower()
                disp_mode = st.session_state.get("_code_mode", mode)

                st.code(code, language=disp_lang)

                # Security scan (only relevant for generative modes)
                if disp_mode in ("✨ Generate", "🐛 Fix", "📝 Document"):
                    ok, issues = SecurityValidator.validate_code(code)
                    if ok:
                        st.success("✅ Security scan: no issues")
                    else:
                        st.error(f"🚨 {len(issues)} security issue(s):")
                        for iss in issues:
                            st.warning(iss)

                # Save / download row
                fname_default = f"output.{_ext(disp_lang)}"
                fname = st.text_input("Save as", fname_default, key="code_fname")
                ca, cb, cc = st.columns(3)
                with ca:
                    if st.button("💾 Save to workspace"):
                        (APP_WORKSPACE / fname).write_text(code)
                        st.success(f"Saved to `{APP_WORKSPACE / fname}`")
                with cb:
                    st.download_button("📥 Download", code, file_name=fname, key="dl_code")
                with cc:
                    if st.button("🔄 Clear"):
                        for k in ("_code_result", "_code_lang", "_code_mode"):
                            st.session_state.pop(k, None)
                        st.rerun()
            else:
                st.info(
                    "Enter a prompt on the left and click **🚀 Run** to generate code.  \n"
                    "For **Explain / Fix / Tests / Document** modes, paste your existing code "
                    "into the input box."
                )

    # ── History ───────────────────────────────────────────────────────────────
    with ctabs[1]:
        hist = _load_history()
        if not hist:
            st.info("No code generation history yet.")
        else:
            st.caption(f"{len(hist)} entries (last 30 kept)")
            col_s, col_clear = st.columns([4, 1])
            with col_s:
                search = st.text_input("Filter history", placeholder="language, mode, prompt…",
                                       label_visibility="collapsed")
            with col_clear:
                if st.button("🗑️ Clear all"):
                    _HISTORY_FILE.unlink(missing_ok=True)
                    st.rerun()

            filtered = [
                h for h in reversed(hist)
                if not search or search.lower() in json.dumps(h).lower()
            ]
            if not filtered:
                st.warning(f"No entries match `{search}`.")
            for i, h in enumerate(filtered):
                label = (f"#{len(filtered)-i}  {h['time']}  ·  {h['mode']}  ·  "
                         f"{h['lang']}  ·  {h['prompt'][:60]}…")
                with st.expander(label):
                    st.code(h["code"], language=h["lang"].lower())
                    if st.button("♻️ Reload into editor", key=f"reload_{i}"):
                        st.session_state["_code_result"] = h["code"]
                        st.session_state["_code_lang"]   = h["lang"]
                        st.session_state["_code_mode"]   = h["mode"]
                        st.rerun()

    # ── Workspace ─────────────────────────────────────────────────────────────
    with ctabs[2]:
        st.caption(f"Files in `{APP_WORKSPACE}`")
        files = sorted(APP_WORKSPACE.glob("*"))
        if not files:
            st.info("Workspace is empty — save code from the Generate tab to see it here.")
        else:
            for f in files:
                if f.is_file():
                    size = f.stat().st_size
                    with st.expander(f"📄 `{f.name}`  ·  {size:,} bytes"):
                        content = f.read_text(errors="replace")
                        lang_guess = _ext_to_lang(f.suffix)
                        st.code(content, language=lang_guess)
                        col_dl, col_del, _ = st.columns([1, 1, 4])
                        with col_dl:
                            st.download_button(
                                "⬇️ Download", content, file_name=f.name,
                                key=f"wdl_{f.name}",
                            )
                        with col_del:
                            if st.button("🗑️ Delete", key=f"wdel_{f.name}"):
                                f.unlink()
                                st.rerun()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove leading/trailing ``` fences that models sometimes add."""
    text = text.strip()
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _ext(lang: str) -> str:
    return {
        "python": "py", "rust": "rs", "bash": "sh", "javascript": "js",
        "typescript": "ts", "go": "go", "c++": "cpp", "c": "c",
        "sql": "sql", "html/css": "html", "dockerfile": "dockerfile",
        "yaml": "yaml",
    }.get(lang.lower(), "txt")


def _ext_to_lang(suffix: str) -> str:
    return {
        ".py": "python", ".rs": "rust", ".sh": "bash", ".js": "javascript",
        ".ts": "typescript", ".go": "go", ".cpp": "cpp", ".c": "c",
        ".sql": "sql", ".html": "html", ".yaml": "yaml", ".yml": "yaml",
    }.get(suffix.lower(), "text")
