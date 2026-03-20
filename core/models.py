# core/models.py — ModelManager: get/set/list/download/delete GGUF models
# Mirrors _load_active_model(), _switch_model_menu(), _remove_model_menu()
# from ai_stack_manager.sh.
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from core.config import MODEL_DIR, MODEL_CONFIG

logger = logging.getLogger(__name__)

class ModelManager:

    @staticmethod
    def get_active_path() -> str:
        """
        Read MODEL_CONFIG, validate path exists, auto-detect first .gguf if missing.
        Mirrors _load_active_model() exactly.
        """
        if MODEL_CONFIG.exists():
            stored = MODEL_CONFIG.read_text().strip()
            if stored and Path(stored).exists():
                return stored
        found = sorted(MODEL_DIR.glob("*.gguf"))
        if found:
            path = str(found[0])
            MODEL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            MODEL_CONFIG.write_text(path)
            return path
        return ""

    @staticmethod
    def set_active(path: str) -> bool:
        """Write chosen path — mirrors: echo "$chosen" > "$MODEL_CONFIG" """
        try:
            MODEL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            MODEL_CONFIG.write_text(path)
            return True
        except Exception as e:
            logger.error(f"set_active: {e}")
            return False

    @staticmethod
    def list_installed() -> List[Dict]:
        if not MODEL_DIR.exists():
            return []
        active = ModelManager.get_active_path()
        out = []
        for f in sorted(MODEL_DIR.glob("*.gguf")):
            out.append({
                "name":      f.name,
                "path":      str(f),
                "size_gb":   round(f.stat().st_size / 1e9, 2),
                "size_human": f"{f.stat().st_size / 1e9:.1f} GB",
                "is_active": str(f) == active,
            })
        return out

    @staticmethod
    def download(filename: str, url: str) -> Tuple[bool, str]:
        """wget to MODEL_DIR — mirrors _download_model_menu()."""
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        dest = MODEL_DIR / filename
        if dest.exists():
            return True, f"Already downloaded: {filename}"
        try:
            r = subprocess.run(["wget", "-O", str(dest), url], timeout=3600)
            if r.returncode == 0 and dest.exists():
                return True, f"Downloaded: {filename} ({dest.stat().st_size / 1e9:.1f} GB)"
            dest.unlink(missing_ok=True)
            return False, "wget failed or was interrupted"
        except Exception as e:
            dest.unlink(missing_ok=True)
            return False, str(e)

    @staticmethod
    def delete(filename: str) -> Tuple[bool, str]:
        """Unlink and auto-select next model — mirrors _remove_model_menu()."""
        path = MODEL_DIR / filename
        if not path.exists():
            return False, "File not found"
        active = ModelManager.get_active_path()
        path.unlink()
        if active and Path(active).name == filename:
            MODEL_CONFIG.unlink(missing_ok=True)
            ModelManager.get_active_path()  # auto-select next
        return True, f"Deleted: {filename}"


# ============================================================================
# MEMORY — mem0 + ChromaDB REST API (:8000)
# ============================================================================
