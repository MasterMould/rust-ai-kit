# ui/tab_stack.py — Stack status tab: _svc() + tab_stack()
import subprocess
from pathlib import Path

import requests
import streamlit as st

from core.config import (
    BackendMode, ENGINE_PORT, PROXY_PORT, MEMORY_PORT, SEARXNG_PORT,
    PROXY_URL, STACK_LOG_DIR, MODEL_CONFIG,
    LLAMA_API_KEY, LLAMA_SERVER_MODEL, PROJECT_ROOT,
)
from core.auth   import audit_log
from core.gpu    import GPUDetector
from core.stack  import StackManager
from core.models import ModelManager, ModelConfigManager

def _svc(label: str, ok: bool, url: str, note: str = "",
         start_fn=None, log_name: str = ""):
    """
    Render one service row.
    When offline AND start_fn is provided, show an inline ▶️ Start button
    and a collapsible log tail for instant diagnosis.
    """
    icon  = "🟢" if ok else "🔴"
    state_html = "<span class='ok'>running</span>" if ok else "<span class='err'>offline</span>"
    st.markdown(
        f"{icon} **{label}** &ensp; <span class='mono'>{url}</span>"
        f" &ensp; {state_html}"
        + (f" &ensp; <small>{note}</small>" if note else ""),
        unsafe_allow_html=True,
    )
    if not ok and start_fn is not None:
        col_btn, col_log = st.columns([1, 4])
        with col_btn:
            if st.button(f"▶️ Start {label}", key=f"start_{label}"):
                with st.spinner(f"Starting {label}…"):
                    ok2, msg = start_fn()
                if ok2:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        with col_log:
            if log_name and STACK_LOG_DIR.exists():
                log_path = STACK_LOG_DIR / f"{log_name}.log"
                if log_path.exists():
                    tail = ""
                    try:
                        r = subprocess.run(
                            ["tail", "-n", "8", str(log_path)],
                            capture_output=True, text=True, timeout=3,
                        )
                        tail = r.stdout.strip()
                    except Exception:
                        pass
                    if tail:
                        with st.expander(f"📋 Last lines of {log_name}.log"):
                            st.code(tail, language="bash")
                else:
                    st.caption(f"No log yet: `{log_path}`")


def tab_stack():
    st.header("🦀 rust-ai-kit Stack")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.info("Switch to **rust-ai-kit** in the sidebar to use this tab.")
        return

    if st.button("🔄 Refresh status"):
        st.rerun()

    status = StackManager.full_status()
    st.subheader("Service health")

    active = ModelManager.get_active_path()
    gpu_layers = GPUDetector.gpu_layers()

    _svc("llama-server (SYCL)", status["engine"], f":{ENGINE_PORT}",
         "Direct inference — no web search",
         start_fn=(lambda: StackManager.start_engine(
             active, gpu_layers, ModelConfigManager.load(active)
         )) if active else None,
         log_name="engine")
    _svc("search proxy", status["proxy"], f":{PROXY_PORT}",
         "Point AnythingLLM here — adds SearXNG transparently",
         start_fn=StackManager.start_search_proxy,
         log_name="proxy")
    _svc("memory server", status["memory"], f":{MEMORY_PORT}",
         "mem0 + ChromaDB persistent facts",
         start_fn=StackManager.start_memory_server,
         log_name="memory")
    _svc("SearXNG", status["searxng"], f":{SEARXNG_PORT}",
         "Private Docker metasearch",
         start_fn=StackManager.setup_searxng,
         log_name="")

    if all(status.values()):
        st.success("✅ All four services online")
    else:
        st.error(f"⚠️ Offline: {', '.join(k for k, v in status.items() if not v)}")

    st.divider()

    # GPU (mirrors check_status)
    st.subheader("🖥️ Intel Arc A770")
    gpu_ok = GPUDetector.clinfo_visible()
    if gpu_ok:
        st.success("✅ GPU visible (level-zero / OpenCL) — SYCL will use GPU")
        xpu = GPUDetector.xpu_smi_line()
        if xpu:
            st.code(xpu)
        freq = GPUDetector.arc_freq_mhz()
        if freq:
            st.caption(f"Core freq: {freq} MHz")
    else:
        st.error("❌ GPU not visible — `render` group membership required")
        st.code("groups   # 'render' must appear\n# If missing: log out + back in\n"
                "dpkg -l libze-intel-gpu1  # must be installed")

    st.divider()

    # Active model
    st.subheader("🤖 Active model")
    active = ModelManager.get_active_path()
    if active:
        st.code(active)
        p = Path(active)
        if p.exists():
            st.caption(f"✅ File present · {p.stat().st_size / 1e9:.2f} GB")
    else:
        st.warning("No model — use Model Manager tab or option 14 in `ai_stack_manager.sh`")

    st.divider()

    # Stack controls (options 2 / 3 / 4)
    st.subheader("⚙️ Stack controls")

    # ── Window launch row ─────────────────────────────────────────────────────
    st.markdown("**Start server in its own terminal window** (recommended — live output visible)")
    wc1, wc2, wc3 = st.columns([2, 2, 4])
    with wc1:
        if st.button("🖥️ Open server window", type="primary",
                     help="Launches llama-server in a dedicated terminal. "
                          "Close the window or press Ctrl-C to stop it."):
            script = PROJECT_ROOT / "run-server-window.sh"
            if not script.exists():
                st.error(f"`run-server-window.sh` not found at `{PROJECT_ROOT}`. "
                         "Pull the latest code and re-run `make setup`.")
            elif not active:
                st.error("No active model — use the Models tab to download and activate one.")
            else:
                try:
                    subprocess.Popen(
                        ["bash", str(script)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    st.success(
                        "Terminal window opening… watch it for startup progress. "
                        "The engine will appear in the status panel above once it's ready."
                    )
                    audit_log(st.session_state.username, "SERVER_WINDOW_OPEN",
                              str(script), True)
                except Exception as e:
                    st.error(f"Could not launch terminal: {e}")

    with wc2:
        if st.button("🛑 Stop server",
                     help="Kills llama-server, search proxy, and memory server."):
            script = PROJECT_ROOT / "stop-server.sh"
            if not script.exists():
                # Fallback: use Python StackManager
                msgs = StackManager.stop_all()
                for m in msgs:
                    st.success(m)
            else:
                result = subprocess.run(
                    ["bash", str(script)],
                    capture_output=True, text=True, timeout=15,
                )
                output = (result.stdout + result.stderr).strip()
                if output:
                    st.code(output, language="bash")
                st.success("Stop command sent.")
            audit_log(st.session_state.username, "SERVER_STOP", "stop-server.sh")

    with wc3:
        st.caption(
            "The server window shows live llama.cpp output — tokens/s, context usage, errors.  \n"
            "It uses your saved **Configure** settings (GPU layers, context size, flash-attn, etc.)."
        )

    st.divider()

    # ── Background controls ───────────────────────────────────────────────────
    st.markdown("**Background controls** (silent — no terminal window)")
    st.caption(
        "Use these if you prefer the server hidden. "
        "Same as `ai_stack_manager.sh` options 2 / 3 / 4."
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶️ Start (background)"):
            if not active:
                st.error("No model set")
            else:
                with st.spinner(f"Starting… GPU layers={gpu_layers} (up to 90s)"):
                    cfg = ModelConfigManager.load(active)
                    ok, msg = StackManager.start_engine(active, gpu_layers, cfg)
                st.success(msg) if ok else st.error(msg)
                audit_log(st.session_state.username, "START_ENGINE", msg, ok)

    with c2:
        if st.button("⏹ Stop all"):
            msgs = StackManager.stop_all()
            for m in msgs:
                st.success(m)
            audit_log(st.session_state.username, "STOP_ALL", "; ".join(msgs))

    with c3:
        if st.button("🔄 Restart"):
            if not active:
                st.error("No model set")
            else:
                with st.spinner("Restarting…"):
                    cfg     = ModelConfigManager.load(active)
                    results = StackManager.restart(active, gpu_layers, cfg)
                for svc, (ok, msg) in results.items():
                    (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {svc}: {msg}")
                audit_log(st.session_state.username, "RESTART", str(results))

    st.divider()

    # Systemd (options 6 / 7)
    st.subheader("🕒 Auto-start on boot")
    st.caption(
        "Writes `~/.config/systemd/user/llamaedge.service` — identical unit to "
        "option 6. Reads `~/.ai_stack/.active_model` at each boot."
    )
    enabled = StackManager.systemd_enabled()
    st.info(f"llamaedge.service: **{'enabled' if enabled else 'disabled'}**")
    c6, c7 = st.columns(2)
    with c6:
        if st.button("✅ Enable auto-start"):
            ok, msg = StackManager.enable_systemd()
            st.success(msg) if ok else st.error(msg)
    with c7:
        if st.button("❌ Disable auto-start"):
            ok, msg = StackManager.disable_systemd()
            st.success(msg) if ok else st.error(msg)

    st.divider()

    # SearXNG setup (option 9)
    st.subheader("🔍 SearXNG setup")
    st.caption(
        "Writes `~/searxng-config/settings.yml` with `format: json` enabled "
        "and launches the Docker container — same as option 9."
    )
    if st.button("🚀 Setup / restart SearXNG"):
        with st.spinner("Setting up SearXNG Docker container…"):
            ok, msg = StackManager.setup_searxng()
        st.success(msg) if ok else st.error(msg)
        audit_log(st.session_state.username, "SETUP_SEARXNG", msg, ok)

    # Proxy health detail
    if status["proxy"]:
        st.divider()
        st.subheader("🌐 Search proxy /health")
        try:
            r = requests.get(f"{PROXY_URL}/health", timeout=3)
            st.json(r.json())
        except Exception as e:
            st.error(str(e))

    # AnythingLLM connection guide (option 8)
    with st.expander("📋 AnythingLLM connection guide (option 8)"):
        st.markdown(f"""
**LLM Provider setup:**
1. Open AnythingLLM → ⚙️ Settings → AI Providers → LLM
2. Provider: **Generic OpenAI**
3. Base URL: `http://localhost:{PROXY_PORT}/v1` ← search proxy **(not {ENGINE_PORT})**
4. API Key: `{LLAMA_API_KEY}`
5. Model Name: `{LLAMA_SERVER_MODEL}`
6. Token Limit: `8192`

> Port **{PROXY_PORT}** adds live web search. Port **{ENGINE_PORT}** is llama-server direct — no search.

**Memory API (mem0):**
```bash
# Store a conversation
curl -X POST http://localhost:{MEMORY_PORT}/memorize \\
  -H "Content-Type: application/json" \\
  -d '{{"messages":[{{"role":"user","content":"I prefer dark mode"}}],"user_id":"me"}}'

# Semantic search
curl -X POST http://localhost:{MEMORY_PORT}/retrieve \\
  -H "Content-Type: application/json" \\
  -d '{{"query":"display preferences","user_id":"me"}}'

# List all
curl http://localhost:{MEMORY_PORT}/memories?user_id=me

# Swagger UI
open http://localhost:{MEMORY_PORT}/docs
```
""")


# ============================================================================
# TAB: MEMORY
# ============================================================================
