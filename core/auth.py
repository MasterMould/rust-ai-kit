# core/auth.py — PAM + local-JSON authentication, audit log
import hashlib
import json
import logging
import os
import pwd as _pwd
import grp as _grp
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import (
    AUDIT_LOG, USERS_DB, SecurityLevel,
    APP_LOG_DIR,
)

import pwd as _pwd
import grp as _grp

def _os_user_exists(username: str) -> bool:
    try:
        _pwd.getpwnam(username)
        return True
    except KeyError:
        return False

def _os_user_role(username: str) -> str:
    """admin if in sudo/admin/wheel group, else user."""
    try:
        user_groups = {g.gr_name for g in _grp.getgrall() if username in g.gr_mem}
        # Also add primary group
        pw = _pwd.getpwnam(username)
        primary = _grp.getgrgid(pw.pw_gid).gr_name
        user_groups.add(primary)
        if user_groups & {"sudo", "admin", "wheel"}:
            return SecurityLevel.ADMIN.value
    except Exception:
        pass
    return SecurityLevel.USER.value

def _pam_authenticate(username: str, password: str) -> bool:
    """Try PAM authentication. Returns False (not raises) on any failure."""
    try:
        import pam  # python-pam
        p = pam.pam()
        return p.authenticate(username, password)
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"PAM error: {e}")
        return False


class AuthManager:

    # ── PAM / OS path ─────────────────────────────────────────────────────────

    @staticmethod
    def _try_pam(username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Authenticate against Linux system users via PAM."""
        if not _os_user_exists(username):
            return False, None
        if _pam_authenticate(username, password):
            role = _os_user_role(username)
            return True, role
        return False, None

    # ── Local JSON fallback ───────────────────────────────────────────────────

    @staticmethod
    def _hash(pw: str) -> str:
        return hashlib.sha256(f"{pw}llm_factory_salt_2024".encode()).hexdigest()

    @staticmethod
    def _load_local() -> Dict:
        if not USERS_DB.exists():
            u = {"admin": {
                "password": AuthManager._hash("admin123"),
                "role": SecurityLevel.ADMIN.value,
                "created": datetime.now().isoformat(),
            }}
            USERS_DB.write_text(json.dumps(u, indent=2))
            return u
        return json.loads(USERS_DB.read_text())

    @staticmethod
    def _try_local(username: str, password: str) -> Tuple[bool, Optional[str]]:
        users = AuthManager._load_local()
        if username not in users:
            return False, None
        if users[username]["password"] == AuthManager._hash(password):
            return True, users[username]["role"]
        return False, None

    # ── Public interface ──────────────────────────────────────────────────────

    @staticmethod
    def authenticate(username: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Try PAM first (system users), fall back to local users.json.
        Returns (success, role_string).
        """
        # 1. PAM — system users
        ok, role = AuthManager._try_pam(username, password)
        if ok:
            audit_log(username, "LOGIN_SUCCESS", f"method=pam role={role}")
            return True, role

        # 2. Local JSON — fallback / dev mode
        ok, role = AuthManager._try_local(username, password)
        if ok:
            audit_log(username, "LOGIN_SUCCESS", f"method=local role={role}")
            return True, role

        audit_log("SYSTEM", "LOGIN_FAILED", f"user={username}", False)
        return False, None

    @staticmethod
    def pam_available() -> bool:
        """Returns True when python-pam is installed and PAM is usable."""
        try:
            import pam  # noqa
            return True
        except ImportError:
            return False

    @staticmethod
    def add_local_user(username: str, password: str, role: str = "user") -> bool:
        """Add / update a user in the local JSON DB (admin task)."""
        try:
            users = AuthManager._load_local()
            users[username] = {
                "password": AuthManager._hash(password),
                "role": role,
                "created": datetime.now().isoformat(),
            }
            USERS_DB.write_text(json.dumps(users, indent=2))
            return True
        except Exception as e:
            logger.error(f"add_local_user: {e}")
            return False

    @staticmethod
    def list_local_users() -> List[Dict]:
        users = AuthManager._load_local()
        return [{"username": u, "role": d["role"], "created": d.get("created", "")}
                for u, d in users.items()]

    @staticmethod
    def delete_local_user(username: str) -> bool:
        try:
            users = AuthManager._load_local()
            if username in users:
                del users[username]
                USERS_DB.write_text(json.dumps(users, indent=2))
                return True
            return False
        except Exception:
            return False


# ============================================================================
# GPU DETECTION — mirrors _print_quick_status / check_status in script
# ============================================================================
