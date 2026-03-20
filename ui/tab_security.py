# ui/tab_security.py — Security scanner + audit statistics tab
import streamlit as st

from core.auth         import AUDIT_LOG
from core.security_rag import SecurityValidator

def tab_security():
    st.header("🛡️ Security")
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Code Scanner")
        code = st.text_area("Paste code to scan:", height=200)
        if st.button("🔍 Scan") and code:
            ok, issues = SecurityValidator.validate_code(code)
            if ok:
                st.success("✅ No issues detected")
            else:
                st.error(f"🚨 {len(issues)} issue(s):")
                for iss in issues:
                    st.warning(iss)

    with c2:
        st.subheader("Audit statistics")
        if AUDIT_LOG.exists():
            lines    = AUDIT_LOG.read_text().splitlines()
            total    = len(lines)
            failures = sum(1 for l in lines if "FAILURE" in l)
            st.metric("Total actions", total)
            st.metric("Failures",      failures)
            if total:
                st.metric("Success rate", f"{(total - failures) / total * 100:.1f}%")
        else:
            st.info("No audit log yet.")


# ============================================================================
# TAB: USERS  (admin only)
# ============================================================================
