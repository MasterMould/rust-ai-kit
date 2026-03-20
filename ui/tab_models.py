# ui/tab_models.py — Model Manager tab
from pathlib import Path

import streamlit as st

from core.config import BackendMode, MODEL_DIR, MODEL_CONFIG, MODEL_CATALOGUE
from core.auth   import audit_log
from core.models import ModelManager
from core.inference import OllamaClient

def tab_models():
    st.header("🤖 Model Manager")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.subheader("Ollama Models")
        for m in OllamaClient.models():
            c1, c2 = st.columns([5, 1])
            c1.write(m)
        st.divider()
        custom = st.text_input("Pull model:")
        if st.button("📥 Pull") and custom:
            with st.spinner(f"Pulling {custom}…"):
                ok, msg = OllamaClient.pull(custom)
            st.success(msg) if ok else st.error(msg)
        return

    active_name = Path(ModelManager.get_active_path()).name if ModelManager.get_active_path() else "none"
    st.info(f"🟢 **Active:** `{active_name}`  &ensp; config: `{MODEL_CONFIG}`")

    mtabs = st.tabs(["📋 Installed", "⬇️ Download", "🔄 Switch", "🗑️ Remove"])

    with mtabs[0]:  # mirrors installed listing in manage_models()
        installed = ModelManager.list_installed()
        if not installed:
            st.warning(f"No .gguf files in `{MODEL_DIR}`")
            st.info("Use the Download tab or `ai_stack_manager.sh` option 14.")
        else:
            st.success(f"{len(installed)} model(s) in `{MODEL_DIR}`")
            for m in installed:
                marker = "🟢 **" + m["name"] + "**" if m["is_active"] else "⚪ " + m["name"]
                c1, c2 = st.columns([6, 1])
                c1.markdown(marker)
                c2.caption(m["size_human"])

    with mtabs[1]:  # mirrors _download_model_menu()
        st.caption(
            f"All models verified on Intel Arc A770 (16 GB).  \n"
            f"Destination: `{MODEL_DIR}`  \n"
            f"Source: HuggingFace (bartowski GGUF collection)"
        )
        idx = st.selectbox(
            "Select model:",
            range(len(MODEL_CATALOGUE)),
            format_func=lambda i: (
                f"{MODEL_CATALOGUE[i]['name']}  —  {MODEL_CATALOGUE[i]['vram']} GB VRAM"
            ),
        )
        m    = MODEL_CATALOGUE[idx]
        dest = MODEL_DIR / m["file"]
        st.markdown(
            f"**File:** `{m['file']}`  \n"
            f"**VRAM:** {m['vram']} GB  \n"
            f"**Description:** {m['desc']}"
        )
        if dest.exists():
            st.success(f"Already downloaded ({dest.stat().st_size / 1e9:.1f} GB)")
            if st.button("Set as active"):
                ModelManager.set_active(str(dest))
                st.success(f"Active → `{m['file']}`")
                st.warning("⚠️ Restart the engine (Stack tab) to load it.")
        else:
            if st.button("⬇️ Download", type="primary"):
                with st.spinner(f"Downloading {m['file']}… (may take several minutes)"):
                    ok, msg = ModelManager.download(m["file"], m["url"])
                if ok:
                    st.success(msg)
                    audit_log(st.session_state.username, "MODEL_DOWNLOAD", m["file"], True)
                    if st.button("Set as active now"):
                        ModelManager.set_active(str(MODEL_DIR / m["file"]))
                        st.rerun()
                else:
                    st.error(msg)

    with mtabs[2]:  # mirrors _switch_model_menu()
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No installed models.")
        else:
            opts = {m["name"]: m["path"] for m in installed}
            choice = st.selectbox("Switch to:", list(opts.keys()))
            if st.button("✅ Set active"):
                ModelManager.set_active(opts[choice])
                st.success(f"Active model → `{choice}`")
                st.warning(
                    "⚠️ Restart the engine (Stack tab) to load the new model — "
                    "same as `ai_stack_manager.sh` option 4."
                )
                audit_log(st.session_state.username, "MODEL_SWITCH", choice)

    with mtabs[3]:  # mirrors _remove_model_menu()
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No models to remove.")
        else:
            opts  = {f"{m['name']} ({m['size_human']})": m["name"] for m in installed}
            label = st.selectbox("Remove:", list(opts.keys()))
            fname = opts[label]
            is_active = any(m["is_active"] and m["name"] == fname for m in installed)
            if is_active:
                st.warning("⚠️ This is the active model. Removing will auto-select the next one.")
            if st.button("🗑️ Confirm delete", type="primary"):
                ok, msg = ModelManager.delete(fname)
                st.success(msg) if ok else st.error(msg)
                audit_log(st.session_state.username, "MODEL_DELETE", fname, ok)
                if ok:
                    st.rerun()


# ============================================================================
# TAB: RAG
# ============================================================================
