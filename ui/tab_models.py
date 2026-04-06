# ui/tab_models.py — Model Manager: categorised catalogue + live HF search + configure
import dataclasses
import subprocess
from pathlib import Path

import streamlit as st

from core.config import (
    BackendMode, MODEL_DIR, MODEL_CONFIG,
    MODEL_CATALOGUE, MODEL_CATEGORIES, MODEL_RUN_CONFIG_FIELDS, ModelRunConfig,
)
from core.auth   import audit_log
from core.models import ModelManager, ModelConfigManager, HFSearchClient
from core.inference import OllamaClient

_VRAM_BUDGET = 16.0   # Arc A770


# ═══════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════

def _vram_bar(vram_gb: float) -> str:
    pct    = min(vram_gb / _VRAM_BUDGET, 1.0)
    filled = int(pct * 10)
    bar    = "█" * filled + "░" * (10 - filled)
    colour = "green" if pct <= 0.6 else ("orange" if pct <= 0.95 else "red")
    return f":{colour}[{bar}]  `{vram_gb:.1f} / {_VRAM_BUDGET:.0f} GB`"


def _run_wget(url: str, dest: Path, progress_slot) -> bool:
    """Blocking wget with live progress bar updates. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen(
            ["wget", "--progress=dot:mega", "-O", str(dest), url],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            if "%" in line:
                try:
                    pct = int(line.strip().split("%")[0].split()[-1])
                    progress_slot.progress(
                        min(pct, 100) / 100, text=f"Downloading… {pct}%"
                    )
                except Exception:
                    pass
        proc.wait()
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            progress_slot.progress(1.0, text="✅ Complete!")
            return True
        dest.unlink(missing_ok=True)
        return False
    except FileNotFoundError:
        st.error("`wget` not found — run: `sudo apt install wget`")
        dest.unlink(missing_ok=True)
        return False
    except Exception as e:
        st.error(f"Download error: {e}")
        dest.unlink(missing_ok=True)
        return False


def _post_download(dest: Path, auto_active: bool, jinja_hint: bool):
    """Common actions after any successful download."""
    size = dest.stat().st_size / 1e9
    st.success(f"Downloaded `{dest.name}` — {size:.2f} GB")
    if auto_active:
        ModelManager.set_active(str(dest))
        if jinja_hint:
            cfg = ModelConfigManager.load(str(dest))
            cfg.jinja = True
            ModelConfigManager.save(str(dest), cfg)
            st.info("ℹ️ --jinja has been auto-enabled in this model's run config.")
        st.info("✅ Set as active. Restart the engine (Stack tab) to load it.")
    audit_log(
        st.session_state.get("username", "system"),
        "MODEL_DOWNLOAD", dest.name, True,
    )
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Tab 1 — Catalogue download
# ═══════════════════════════════════════════════════════════════════════════

def _catalogue_card(m: dict, dest: Path, key: str):
    vram  = float(m["vram"])
    fits  = vram <= _VRAM_BUDGET
    icon  = "🟢" if fits else "🟡"
    badges = []
    if m.get("recommended"): badges.append("⭐")
    if m.get("new"):         badges.append("🔥 New")
    if m.get("vision"):      badges.append("👁️ Vision")
    if m.get("jinja"):       badges.append("⚠️ --jinja")
    badge_str = "  ".join(badges)

    with st.expander(f"{icon} **{m['name']}**  {badge_str}"):
        col_l, col_r = st.columns([3, 1])
        with col_l:
            st.markdown(f"**{m['desc']}**")
            if m.get("notes"):
                st.caption(m["notes"])
            st.markdown(_vram_bar(vram))
            tag_str = "  ".join(f"`{t}`" for t in m.get("tags", []))
            if tag_str: st.markdown(tag_str)
            st.caption(
                f"📁 `{m['file']}`  \n"
                f"🔗 [View on HuggingFace]({m['url'].split('/resolve')[0]})"
            )
        with col_r:
            if dest.exists():
                st.success(f"✅ {dest.stat().st_size/1e9:.1f} GB")
                if st.button("▶️ Activate", key=f"cat_act_{key}"):
                    ModelManager.set_active(str(dest))
                    if m.get("jinja"):
                        cfg = ModelConfigManager.load(str(dest))
                        cfg.jinja = True
                        ModelConfigManager.save(str(dest), cfg)
                    st.rerun()
            else:
                if not fits:
                    st.warning(f"⚠️ {vram} GB\nExceeds A770")
                else:
                    st.info(f"{vram} GB VRAM")
                if st.button("⬇️ Download", type="primary", key=f"cat_dl_{key}"):
                    prog = st.progress(0, text="Starting…")
                    ok = _run_wget(m["url"], dest, prog)
                    if ok:
                        _post_download(dest, True, bool(m.get("jinja")))
                    else:
                        st.error("Download failed.")


# ═══════════════════════════════════════════════════════════════════════════
# Tab 2 — Live HF search (Manual Download)
# ═══════════════════════════════════════════════════════════════════════════

def _hf_search_tab():
    st.markdown(
        "Search the entire HuggingFace Hub for GGUF models in real time. "
        "Pick a repo, choose your quantisation, and download — no URL typing needed."
    )

    # ── Search bar + sort ─────────────────────────────────────────────────
    col_q, col_sort, col_author = st.columns([3, 1, 1])
    with col_q:
        query = st.text_input(
            "Search HuggingFace",
            placeholder="e.g. llama, mistral, qwen coder, gemma…",
            label_visibility="collapsed",
            key="hf_search_query",
        )
    with col_sort:
        sort = st.selectbox(
            "Sort", ["downloads", "trending", "likes", "lastModified"],
            label_visibility="collapsed",
            key="hf_search_sort",
        )
    with col_author:
        author_input = st.text_input(
            "Author",
            placeholder="e.g. bartowski",
            label_visibility="collapsed",
            key="hf_search_author",
        )

    # Quick-author chips
    st.caption("Quick filter by popular GGUF curators:")
    chip_cols = st.columns(len(HFSearchClient.popular_authors()))
    chosen_author = author_input
    for i, a in enumerate(HFSearchClient.popular_authors()):
        with chip_cols[i]:
            if st.button(a, key=f"chip_{a}", use_container_width=True):
                chosen_author = a
                st.session_state["hf_search_author"] = a
                st.rerun()

    st.divider()

    # ── Results ───────────────────────────────────────────────────────────
    effective_author = st.session_state.get("hf_search_author", "").strip()
    effective_query  = st.session_state.get("hf_search_query", "").strip()

    if not effective_query and not effective_author:
        # Show trending by default — useful on first open
        st.caption("🔥 Trending GGUF models right now:")
        results = HFSearchClient.trending(limit=12)
    else:
        with st.spinner("Searching HuggingFace…"):
            results = HFSearchClient.search(
                effective_query,
                sort=st.session_state.get("hf_search_sort", "downloads"),
                limit=20,
                author=effective_author,
            )

    if not results:
        st.warning(
            "No results returned. Check your search terms or network connection.  \n"
            "HuggingFace API requires internet access from the machine running this app."
        )
        return

    st.caption(f"Showing {len(results)} repos — click one to browse its files.")

    # ── Repo selector ─────────────────────────────────────────────────────
    repo_labels = []
    for r in results:
        dl  = f"{r['downloads']:,}" if r['downloads'] else "?"
        ago = r.get("lastModified", "")[:10]
        repo_labels.append(f"{r['id']}  ·  ⬇️ {dl}  ·  🕐 {ago}")

    selected_idx = st.selectbox(
        "Select repo",
        range(len(repo_labels)),
        format_func=lambda i: repo_labels[i],
        label_visibility="collapsed",
        key="hf_repo_select",
    )
    selected_repo = results[selected_idx]

    # Repo metadata strip
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Downloads", f"{selected_repo['downloads']:,}")
    mc2.metric("Likes",     selected_repo['likes'])
    mc3.metric("Updated",   selected_repo.get("lastModified", "")[:10] or "?")
    mc4.markdown(
        f"[🔗 Open on HuggingFace](https://huggingface.co/{selected_repo['id']})"
    )

    st.divider()

    # ── File picker ───────────────────────────────────────────────────────
    with st.spinner(f"Fetching file list for `{selected_repo['id']}`…"):
        files = HFSearchClient.repo_files(selected_repo["id"])

    if not files:
        st.warning(
            "No GGUF files found in this repo, or it could not be reached.  \n"
            "Try opening the HuggingFace page directly to confirm files exist."
        )
        return

    # Build file select labels
    def _file_label(f):
        rec  = " ⭐ Recommended" if f["recommended"] else ""
        vram = f"  {_vram_bar_inline(f['size_gb'])}" if f["size_gb"] else ""
        return f"{f['filename']}  ·  {f['size_human']}{rec}"

    def _vram_bar_inline(gb):
        if gb <= 0: return ""
        pct = gb / _VRAM_BUDGET
        colour = "green" if pct <= 0.6 else ("orange" if pct <= 0.95 else "red")
        return f"({gb:.1f} GB)"

    # Default selection: first recommended file
    default_file_idx = 0
    for i, f in enumerate(files):
        if f["recommended"]:
            default_file_idx = i
            break

    file_idx = st.selectbox(
        "Choose quantisation",
        range(len(files)),
        index=default_file_idx,
        format_func=lambda i: _file_label(files[i]),
        key="hf_file_select",
    )
    chosen_file = files[file_idx]

    # Quantisation info row
    fc1, fc2, fc3 = st.columns(3)
    fc1.markdown(f"**File:** `{chosen_file['filename']}`")
    fc2.markdown(f"**Size:** `{chosen_file['size_human']}`")
    gb = chosen_file["size_gb"]
    if gb > 0:
        fits = gb <= _VRAM_BUDGET
        fc3.markdown(
            "🟢 Fits on A770" if fits else f"🟡 {gb:.1f} GB — CPU offload needed"
        )

    # VRAM bar
    if gb > 0:
        st.markdown(_vram_bar(gb))

    # Quant explainer
    with st.expander("❓ What do Q4_K_M, Q8_0, IQ4_XS etc. mean?"):
        st.markdown("""
**K-quants (QX_K_S / QX_K_M / QX_K_L)** — the recommended default. The number is the bit depth
(4 = Q4, 5 = Q5, …); M = medium accuracy/size balance; L = larger, higher quality.
- **Q4_K_M** — best all-round choice for 16 GB GPUs. ~75% the quality loss of Q8 at ~55% the size.
- **Q5_K_M** — step up if you have headroom; noticeably sharper.
- **Q8_0** — near-lossless but 2× the size of Q4.

**I-quants (IQ4_XS, IQ3_M …)** — importance-matrix quants. Same bit depth but smarter allocation
of bits based on layer importance. **IQ4_XS ≈ Q4_K_M quality at ~10% smaller file**.
Use these when the Q4_K_M is 1–2 GB over your VRAM budget.

**Avoid** Q2_K / IQ1_M unless you have extreme VRAM constraints — quality degrades sharply.
        """)

    st.divider()

    # ── Download form ─────────────────────────────────────────────────────
    col_opts, col_btn = st.columns([3, 1])
    with col_opts:
        save_name = st.text_input(
            "Save as",
            value=chosen_file["filename"],
            help="Filename under your model directory. Edit if you want a custom name.",
            key="hf_save_name",
        )
        auto_active = st.checkbox("Set as active model after download", value=True,
                                   key="hf_auto_active")

    with col_btn:
        st.markdown("&nbsp;", unsafe_allow_html=True)   # vertical spacer
        st.markdown("&nbsp;", unsafe_allow_html=True)
        do_download = st.button(
            "⬇️ Download", type="primary",
            key="hf_do_download",
            use_container_width=True,
        )

    if do_download:
        if not save_name.endswith(".gguf"):
            st.error("Filename must end in .gguf")
        else:
            dest = MODEL_DIR / save_name
            if dest.exists():
                st.warning(
                    f"`{save_name}` already exists ({dest.stat().st_size/1e9:.1f} GB).  \n"
                    "Delete it from the Remove tab first if you want to re-download."
                )
            else:
                prog = st.progress(0, text=f"Connecting to {chosen_file['url'][:70]}…")
                ok = _run_wget(chosen_file["url"], dest, prog)
                if ok:
                    _post_download(dest, auto_active, False)
                else:
                    st.error(
                        "Download failed. Common causes:  \n"
                        "• No internet access from this machine  \n"
                        "• The repo requires a HuggingFace login (gated model)  \n"
                        "• Disk full"
                    )

    # ── CLI snippet ───────────────────────────────────────────────────────
    with st.expander("📋 Download manually via CLI"):
        st.code(
            f"# huggingface-cli (recommended — handles auth + resume)\n"
            f"pip install -U huggingface_hub\n"
            f"huggingface-cli download {selected_repo['id']} "
            f"--include \"{chosen_file['filename']}\" --local-dir {MODEL_DIR}/\n\n"
            f"# wget (no auth, no resume)\n"
            f"wget -O {MODEL_DIR}/{chosen_file['filename']} \\\n"
            f"  \"{chosen_file['url']}\"",
            language="bash",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Configure tab helpers
# ═══════════════════════════════════════════════════════════════════════════

def _field_widget(field: dict, current_val, key_prefix: str):
    w, key, label, help_ = field["widget"], f"{key_prefix}_{field['key']}", field["label"], field["help"]
    if w == "int_slider":
        return st.slider(label, min_value=field["min"], max_value=field["max"],
                         step=field["step"], value=int(current_val), help=help_, key=key)
    if w == "float_slider":
        return st.slider(label, min_value=float(field["min"]), max_value=float(field["max"]),
                         step=float(field["step"]), value=float(current_val), help=help_, key=key)
    if w == "checkbox":
        return st.checkbox(label, value=bool(current_val), help=help_, key=key)
    if w == "select":
        opts = field["options"]
        return st.selectbox(label, opts, index=opts.index(current_val) if current_val in opts else 0,
                             help=help_, key=key)
    return current_val


def _config_form(model_path: str):
    cfg      = ModelConfigManager.load(model_path)
    cfg_dict = dataclasses.asdict(cfg)
    groups   = {}
    for f in MODEL_RUN_CONFIG_FIELDS:
        groups.setdefault(f["group"], []).append(f)

    st.markdown(f"**Configuring:** `{Path(model_path).name}`  \n"
                "Each slider maps directly to a llama-server flag. "
                "Hover for a plain-English explanation.")
    st.divider()

    new_vals: dict = {}
    for group_name, fields in groups.items():
        st.subheader(group_name)
        for f in fields:
            new_vals[f["key"]] = _field_widget(f, cfg_dict[f["key"]], model_path[:12])
        st.divider()

    c_save, c_reset, c_prev, _ = st.columns([1, 1, 1, 4])
    with c_save:
        if st.button("💾 Save", type="primary", key=f"save_{model_path}"):
            new_cfg = ModelRunConfig(**{k: new_vals.get(k, cfg_dict[k]) for k in cfg_dict})
            if ModelConfigManager.save(model_path, new_cfg):
                st.success("Saved.")
                audit_log(st.session_state.get("username", "system"),
                          "MODEL_CONFIG_SAVE", Path(model_path).name)
            else:
                st.error("Save failed.")
    with c_reset:
        if st.button("↩️ Defaults", key=f"reset_{model_path}"):
            ModelConfigManager.save(model_path, ModelRunConfig())
            st.success("Reset.")
            st.rerun()
    with c_prev:
        show_preview = st.toggle("🖥️ Preview", key=f"prev_{model_path}")

    if show_preview:
        st.divider()
        cur = ModelRunConfig(**{k: new_vals.get(k, cfg_dict[k]) for k in cfg_dict})
        t1, t2 = st.tabs(["llama-cli", "llama-server"])
        with t1:
            st.code(ModelConfigManager.to_command_preview(cur, model_path, "./llama-cli"),
                    language="bash")
        with t2:
            st.code(ModelConfigManager.to_command_preview(cur, model_path, "./llama-server")
                    + f"\n  --port 8080 \\\n  --host 0.0.0.0 \\\n  --api-key local",
                    language="bash")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def tab_models():
    st.header("🤖 Model Manager")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.subheader("Ollama Models")
        for m in OllamaClient.models():
            st.write(m)
        st.divider()
        custom = st.text_input("Pull model:")
        if st.button("📥 Pull") and custom:
            with st.spinner(f"Pulling {custom}…"):
                ok, msg = OllamaClient.pull(custom)
            st.success(msg) if ok else st.error(msg)
        return

    active_path = ModelManager.get_active_path()
    active_name = Path(active_path).name if active_path else "none"
    st.info(f"🟢 **Active:** `{active_name}`  &ensp; `{MODEL_CONFIG}`")

    mtabs = st.tabs([
        "📋 Installed",
        "⬇️ Catalogue",
        "🔍 Search HuggingFace",
        "⚙️ Configure",
        "🔄 Switch",
        "🗑️ Remove",
    ])

    # ── Installed ────────────────────────────────────────────────────────
    with mtabs[0]:
        installed = ModelManager.list_installed()
        if not installed:
            st.warning(f"No .gguf files in `{MODEL_DIR}`")
            st.info("Use the **Catalogue** or **Search HuggingFace** tab to download one.")
        else:
            st.success(f"{len(installed)} model(s) installed")
            for m in installed:
                marker = "🟢 **" + m["name"] + "**" if m["is_active"] else "⚪ " + m["name"]
                c1, c2, c3 = st.columns([6, 1, 1])
                c1.markdown(marker)
                c2.caption(m["size_human"])
                c3.caption("⚙️" if ModelConfigManager._cfg_path(m["path"]).exists() else "")

    # ── Catalogue ────────────────────────────────────────────────────────
    with mtabs[1]:
        col_cat, col_vram, col_q = st.columns([2, 1, 2])
        with col_cat:
            cats = ["🔍 All"] + list(MODEL_CATEGORIES.keys())
            cat_filter = st.selectbox("Category", cats, key="cat_filter")
        with col_vram:
            vram_lim = st.slider("Max VRAM GB", 1.0, 20.0, _VRAM_BUDGET, 0.5,
                                 key="cat_vram")
        with col_q:
            name_q = st.text_input("Filter", placeholder="name / tag…",
                                   label_visibility="visible", key="cat_name_q")

        c1, c2, c3 = st.columns(3)
        c1.metric("In catalogue", len(MODEL_CATALOGUE))
        c2.metric("🔥 New", sum(1 for m in MODEL_CATALOGUE if m.get("new")))
        c3.metric("⭐ Recommended", sum(1 for m in MODEL_CATALOGUE if m.get("recommended")))
        st.divider()

        visible = [
            m for m in MODEL_CATALOGUE
            if (cat_filter == "🔍 All" or m["category"] == cat_filter)
            and float(m["vram"]) <= vram_lim
            and (not name_q or name_q.lower() in m["name"].lower()
                 or name_q.lower() in m.get("desc", "").lower()
                 or any(name_q.lower() in t.lower() for t in m.get("tags", [])))
        ]

        if not visible:
            st.info("No models match these filters.")
        else:
            grouped = {}
            for m in visible:
                grouped.setdefault(m["category"], []).append(m)
            for cat_name, models in grouped.items():
                st.subheader(cat_name)
                st.caption(MODEL_CATEGORIES.get(cat_name, ""))
                for m in models:
                    _catalogue_card(m, MODEL_DIR / m["file"],
                                    m["file"][:18].replace(".", "_"))
                st.divider()

    # ── Search HuggingFace ────────────────────────────────────────────────
    with mtabs[2]:
        _hf_search_tab()

    # ── Configure ─────────────────────────────────────────────────────────
    with mtabs[3]:
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No installed models.")
        else:
            opts       = {m["name"]: m["path"] for m in installed}
            default_ix = next((i for i, m in enumerate(installed) if m["is_active"]), 0)
            chosen     = st.selectbox("Model to configure", list(opts.keys()),
                                      index=default_ix, key="cfg_model_select")
            path       = opts[chosen]

            saved   = dataclasses.asdict(ModelConfigManager.load(path))
            default = dataclasses.asdict(ModelRunConfig())
            diffs   = {k: (default[k], saved[k]) for k in saved if saved[k] != default[k]}
            if diffs:
                with st.expander(f"🔍 {len(diffs)} setting(s) differ from defaults"):
                    for k, (dv, sv) in diffs.items():
                        st.markdown(f"- **{k}**: default `{dv}` → saved `{sv}`")
            st.divider()
            _config_form(path)

    # ── Switch ─────────────────────────────────────────────────────────────
    with mtabs[4]:
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No installed models.")
        else:
            opts   = {m["name"]: m["path"] for m in installed}
            choice = st.selectbox("Switch to:", list(opts.keys()))
            cfg    = ModelConfigManager.load(opts[choice])
            with st.expander("⚙️ Run config for this model"):
                for f in MODEL_RUN_CONFIG_FIELDS:
                    v = getattr(cfg, f["key"])
                    st.markdown(f"- `{f['key']}` = **{v}**", unsafe_allow_html=False)
            if st.button("✅ Set active"):
                ModelManager.set_active(opts[choice])
                st.success(f"Active → `{choice}`")
                st.warning("Restart engine to load it.")
                audit_log(st.session_state.username, "MODEL_SWITCH", choice)

    # ── Remove ─────────────────────────────────────────────────────────────
    with mtabs[5]:
        installed = ModelManager.list_installed()
        if not installed:
            st.info("No models to remove.")
        else:
            opts  = {f"{m['name']} ({m['size_human']})": m["name"] for m in installed}
            label = st.selectbox("Remove:", list(opts.keys()))
            fname = opts[label]
            is_active = any(m["is_active"] and m["name"] == fname for m in installed)
            if is_active:
                st.warning("⚠️ Active model — removing will auto-select next.")
            c_del, c_cfg, _ = st.columns([1, 2, 4])
            with c_del:
                confirm = st.button("🗑️ Delete", type="primary")
            with c_cfg:
                del_cfg = st.checkbox("Also delete saved config", value=True)
            if confirm:
                ok, msg = ModelManager.delete(fname)
                if ok and del_cfg:
                    from core.config import MODEL_CONFIGS_DIR
                    cfg_f = MODEL_CONFIGS_DIR / f"{Path(fname).stem}.json"
                    if cfg_f.exists():
                        cfg_f.unlink()
                        msg += " + config"
                st.success(msg) if ok else st.error(msg)
                audit_log(st.session_state.username, "MODEL_DELETE", fname, ok)
                if ok:
                    st.rerun()