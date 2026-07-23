# ui/tab_security.py — Security: code scanner, audit timeline, bandit integration
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

import streamlit as st

from core.config       import APP_LOG_DIR, APP_WORKSPACE, PROJECT_ROOT
from core.auth         import AUDIT_LOG, audit_log
from core.security_rag import SecurityValidator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_audit(n_lines: int = 200) -> list:
    """Parse the last N lines of the audit log into dicts."""
    if not AUDIT_LOG.exists():
        return []
    entries = []
    for line in AUDIT_LOG.read_text().splitlines()[-n_lines:]:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 5:
            entries.append({
                "time":    parts[0],
                "user":    parts[1],
                "action":  parts[2],
                "status":  parts[3],
                "details": parts[4] if len(parts) > 4 else "",
            })
    return entries


def _run_bandit(code: str) -> str:
    """Run bandit on a temp file; return its text output."""
    tmp = APP_WORKSPACE / "_bandit_tmp.py"
    try:
        tmp.write_text(code)
        r = subprocess.run(
            ["bandit", "-r", str(tmp), "-f", "text", "-ll"],
            capture_output=True, text=True, timeout=30,
        )
        return (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return "bandit not installed — run: pip install bandit"
    except Exception as e:
        return f"bandit error: {e}"
    finally:
        tmp.unlink(missing_ok=True)


def _severity_colour(sev: str) -> str:
    return {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev.upper(), "⚪")


# ── Main tab ──────────────────────────────────────────────────────────────────

def tab_security():
    st.header("🛡️ Security")

    stabs = st.tabs(["🔍 Code Scanner", "📊 Audit Dashboard", "📋 Audit Log"])

    # ── Code Scanner ──────────────────────────────────────────────────────────
    with stabs[0]:
        col_input, col_result = st.columns(2)

        with col_input:
            st.subheader("Scan code")
            code = st.text_area(
                "Paste code to scan",
                height=280,
                placeholder="Paste any code here — Python, Bash, etc.",
                label_visibility="collapsed",
            )
            col_a, col_b = st.columns(2)
            with col_a:
                run_basic = st.button("🔍 Quick scan", type="primary", disabled=not code)
            with col_b:
                run_bandit = st.button(
                    "🛡️ Bandit scan",
                    disabled=not code,
                    help="Runs the full `bandit` security linter (Python only). "
                         "Requires `pip install bandit`.",
                )

        with col_result:
            st.subheader("Results")
            if run_basic and code:
                ok, issues = SecurityValidator.validate_code(code)
                if ok:
                    st.success("✅ Quick scan: no issues detected")
                else:
                    st.error(f"🚨 {len(issues)} issue(s) found:")
                    for iss in issues:
                        st.warning(iss)
                audit_log(
                    st.session_state.get("username", "system"),
                    "CODE_SCAN", f"issues={len(issues)}", ok,
                )

            if run_bandit and code:
                with st.spinner("Running bandit…"):
                    output = _run_bandit(code)
                if "No issues identified" in output or output.strip() == "":
                    st.success("✅ Bandit: no issues identified")
                elif "bandit not installed" in output or "bandit error" in output:
                    st.warning(output)
                else:
                    # Parse severity counts from bandit output
                    highs   = output.count("Severity: High")
                    mediums = output.count("Severity: Medium")
                    lows    = output.count("Severity: Low")
                    if highs:
                        st.error(f"🔴 {highs} HIGH · 🟡 {mediums} MEDIUM · 🟢 {lows} LOW")
                    else:
                        st.warning(f"🟡 {mediums} MEDIUM · 🟢 {lows} LOW")
                    with st.expander("Full bandit output"):
                        st.code(output, language="text")
                audit_log(
                    st.session_state.get("username", "system"),
                    "BANDIT_SCAN", f"H={highs if run_bandit else '?'}", True,
                )

            if not run_basic and not run_bandit:
                st.info(
                    "Paste code on the left, then choose a scan type:  \n"
                    "- **Quick scan** — checks for blocked patterns and dangerous imports (fast, any language)  \n"
                    "- **Bandit scan** — full Python AST security analysis (requires `pip install bandit`)"
                )

    # ── Audit Dashboard ───────────────────────────────────────────────────────
    with stabs[1]:
        entries = _parse_audit(500)
        if not entries:
            st.info("No audit entries yet.")
        else:
            total    = len(entries)
            failures = sum(1 for e in entries if e["status"] == "FAILURE")
            users    = len({e["user"] for e in entries})
            actions  = Counter(e["action"] for e in entries)

            # KPI row
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total events",   total)
            k2.metric("Failures",       failures)
            k3.metric("Success rate",   f"{(total-failures)/total*100:.1f}%")
            k4.metric("Active users",   users)
            st.divider()

            # Top actions
            col_act, col_fail = st.columns(2)
            with col_act:
                st.subheader("Top actions")
                for action, count in actions.most_common(8):
                    st.markdown(f"- `{action}` — **{count}**")

            with col_fail:
                st.subheader("Recent failures")
                fails = [e for e in reversed(entries) if e["status"] == "FAILURE"]
                if not fails:
                    st.success("No failures recorded 🎉")
                else:
                    for e in fails[:8]:
                        st.error(
                            f"**{e['action']}**  ·  {e['user']}  \n"
                            f"{e['time'][:16]}  ·  {e['details']}"
                        )

            # Login activity
            st.divider()
            st.subheader("Login activity")
            logins = [e for e in entries if "LOGIN" in e["action"]]
            if logins:
                import pandas as pd
                df = pd.DataFrame(logins)[["time", "user", "action", "status"]]
                st.dataframe(df.tail(20), use_container_width=True, hide_index=True)
            else:
                st.info("No login events in recent log.")

    # ── Audit Log (raw) ────────────────────────────────────────────────────────
    with stabs[2]:
        entries = _parse_audit(200)
        if not entries:
            st.info("Audit log is empty.")
        else:
            col_f, col_u, col_dl = st.columns([2, 2, 1])
            with col_f:
                f_action = st.text_input("Filter action", placeholder="LOGIN, CHAT…",
                                         label_visibility="collapsed")
            with col_u:
                all_users = sorted({e["user"] for e in entries})
                f_user = st.selectbox("Filter user", ["All"] + all_users,
                                      label_visibility="collapsed")
            with col_dl:
                if AUDIT_LOG.exists():
                    st.download_button(
                        "⬇️ Export",
                        data=AUDIT_LOG.read_bytes(),
                        file_name="audit.log",
                        mime="text/plain",
                    )

            filtered = [
                e for e in reversed(entries)
                if (not f_action or f_action.upper() in e["action"])
                and (f_user == "All" or e["user"] == f_user)
            ]
            st.caption(f"Showing {len(filtered)} of {len(entries)} entries")

            import pandas as pd
            if filtered:
                df = pd.DataFrame(filtered)
                # Colour status column
                st.dataframe(
                    df[["time", "user", "action", "status", "details"]].rename(columns={
                        "time": "Timestamp", "user": "User", "action": "Action",
                        "status": "Status", "details": "Details",
                    }),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Status": st.column_config.TextColumn(
                            "Status",
                            help="SUCCESS or FAILURE",
                        )
                    },
                )
