# ui/tab_users.py — User management tab (PAM + local accounts)
import pwd as _pwd
import grp as _grp

import streamlit as st

from core.config import SecurityLevel
from core.auth   import AuthManager, audit_log

def tab_users():
    st.header("👥 User Management")

    is_admin = st.session_state.get("role") == SecurityLevel.ADMIN.value
    if not is_admin:
        st.warning("🔒 Admin access required.")
        return

    # PAM status
    pam_ok = AuthManager.pam_available()
    if pam_ok:
        st.success(
            "✅ **PAM active** — users log in with their Linux system credentials.  \n"
            "Any user account on this machine can log in. Role is determined by "
            "OS group membership (`sudo`/`admin` → admin, everyone else → user)."
        )
    else:
        st.warning(
            "⚠️ **PAM unavailable** — falling back to local `config/users.json`.  \n"
            "Install `python-pam` and ensure the process user is in the `shadow` group "
            "to enable OS-level authentication.  \n"
            "```bash\npip install python-pam\nsudo usermod -aG shadow $USER\n"
            "# then log out and back in\n```"
        )

    st.divider()

    # Show OS users who could log in (those with login shells)
    if pam_ok:
        st.subheader("🐧 OS users with login shells")
        st.caption("These accounts can authenticate directly with their system password.")
        try:
            shell_users = []
            for pw in _pwd.getpwall():
                if (pw.pw_shell not in ("/bin/false", "/usr/sbin/nologin", "")
                        and pw.pw_uid >= 1000):
                    groups = [g.gr_name for g in _grp.getgrall() if pw.pw_name in g.gr_mem]
                    role = "admin" if set(groups) & {"sudo", "admin", "wheel"} else "user"
                    shell_users.append({
                        "Username": pw.pw_name,
                        "UID": pw.pw_uid,
                        "Role in app": role,
                        "OS Groups": ", ".join(sorted(groups)[:6]),
                    })
            if shell_users:
                import pandas as pd
                st.dataframe(pd.DataFrame(shell_users), use_container_width=True)
            else:
                st.info("No regular user accounts found.")
        except Exception as e:
            st.error(f"Could not enumerate users: {e}")

    st.divider()

    # Local JSON users (fallback accounts)
    st.subheader("📋 Local fallback accounts  (`config/users.json`)")
    st.caption(
        "These are used when PAM is unavailable, or as override accounts "
        "(e.g. a service account that has no OS login)."
    )

    local_users = AuthManager.list_local_users()
    if local_users:
        for u in local_users:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.write(f"**{u['username']}**")
            c2.write(u["role"])
            c3.caption(u["created"][:10] if u["created"] else "")
            with c4:
                if u["username"] != st.session_state.username:  # can't delete yourself
                    if st.button("🗑️", key=f"delusr_{u['username']}"):
                        if AuthManager.delete_local_user(u["username"]):
                            st.success(f"Deleted {u['username']}")
                            st.rerun()
    else:
        st.info("No local accounts.")

    st.divider()

    # Add local user
    st.subheader("➕ Add local fallback account")
    with st.form("add_user_form"):
        new_u = st.text_input("Username")
        new_p = st.text_input("Password", type="password")
        new_p2 = st.text_input("Confirm password", type="password")
        new_r = st.selectbox("Role", [SecurityLevel.USER.value, SecurityLevel.ADMIN.value])
        if st.form_submit_button("Add user"):
            if not new_u or not new_p:
                st.error("Username and password required.")
            elif new_p != new_p2:
                st.error("Passwords do not match.")
            elif len(new_p) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                if AuthManager.add_local_user(new_u, new_p, new_r):
                    st.success(f"Added local account: {new_u} ({new_r})")
                    audit_log(st.session_state.username, "USER_ADDED", new_u)
                    st.rerun()
                else:
                    st.error("Failed to save user.")


# ============================================================================
# TAB: LOGS  (mirrors view_logs() options 1–4)
# ============================================================================
