# core/security_rag.py — SecurityValidator + RAGManager
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from core.config import SECURITY_CONFIG, RAG_DOCS_DIR, ADMIN_ALLOWED_EXTENSIONS, ADMIN_MAX_FILE_SIZE_MB

class SecurityValidator:
    @staticmethod
    def validate_code(code: str) -> Tuple[bool, List[str]]:
        issues = []
        for pat in SECURITY_CONFIG.BLOCKED_PATTERNS:
            if re.search(pat, code, re.IGNORECASE):
                issues.append(f"Blocked pattern: {pat}")
        for imp in ["os", "subprocess", "shutil", "sys", "ctypes", "pickle"]:
            if re.search(rf"\bimport\s+{imp}\b|\bfrom\s+{imp}\s+import", code):
                issues.append(f"Dangerous import: {imp}")
        return len(issues) == 0, issues

    @staticmethod
    def sanitize(text: str, max_len: int = 10000) -> str:
        return "".join(c for c in text[:max_len] if c.isprintable() or c in "\n\t")


class RAGManager:
    @staticmethod
    def process(file_path: Path, file_name: str,
                is_admin: bool = False) -> Tuple[bool, str]:
        """
        Process an uploaded file for RAG.
        is_admin=True  — any extension, 100 MB limit, binary fallback.
        is_admin=False — respects ALLOWED_EXTENSIONS, 10 MB limit.
        """
        try:
            suffix = file_path.suffix.lower()
            max_mb = ADMIN_MAX_FILE_SIZE_MB if is_admin else 10
            size_mb = file_path.stat().st_size / 1e6
            if size_mb > max_mb:
                return False, f"File too large ({size_mb:.1f} MB > {max_mb} MB)"
            if not is_admin:
                allowed = [e.lower() for e in SECURITY_CONFIG.ALLOWED_EXTENSIONS]
                if suffix not in allowed:
                    ext_list = ', '.join(allowed)
                    return False, (
                        f"Extension '{suffix}' not allowed. "
                        f"Allowed: {ext_list}. Admin users can upload any type."
                    )
            if suffix == ".pdf":
                try:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        content = "".join(
                            p.extract_text() for p in PyPDF2.PdfReader(f).pages
                        )
                    if not content.strip():
                        content = "[PDF had no extractable text: " + file_name + "]"
                except ImportError:
                    content = "PyPDF2 not installed: pip install PyPDF2"
            elif suffix == ".ipynb":
                try:
                    nb = json.loads(file_path.read_text(encoding="utf-8"))
                    cells = []
                    for cell in nb.get("cells", []):
                        ct = cell.get("cell_type", "")
                        src = "".join(cell.get("source", []))
                        cells.append("[" + ct.upper() + "]" + "\n" + src)
                    content = "\n\n".join(cells)
                except Exception:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
            elif suffix in (".zip", ".tar", ".gz"):
                import zipfile, tarfile
                listing = []
                try:
                    if suffix == ".zip":
                        with zipfile.ZipFile(file_path) as z:
                            listing = z.namelist()
                    else:
                        with tarfile.open(file_path) as t:
                            listing = t.getnames()
                except Exception as ex:
                    listing = ["Could not read archive: " + str(ex)]
                content = "Archive: " + file_name + "\n" + "\n".join(listing)
            else:
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    if is_admin:
                        raw = file_path.read_bytes()
                        content = "[Binary file - hex preview]\n" + raw[:2048].hex()
                    else:
                        raise
            out  = RAG_DOCS_DIR / (file_name + ".txt")
            meta = RAG_DOCS_DIR / (file_name + ".meta.json")
            out.write_text(content, encoding="utf-8")
            meta.write_text(json.dumps({
                "filename":  file_name,
                "uploaded":  datetime.now().isoformat(),
                "size":      len(content),
                "path":      str(out),
                "is_admin":  is_admin,
            }, indent=2))
            return True, f"{len(content):,} chars"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def list_docs() -> List[Dict]:
        return sorted(
            [json.loads(m.read_text()) for m in RAG_DOCS_DIR.glob("*.meta.json")],
            key=lambda x: x.get("uploaded", ""), reverse=True,
        )

    @staticmethod
    def search(query: str, max_results: int = 3,
               full_content: bool = False) -> List[Dict]:
        """max_results up to 50 for admin. full_content=True returns full doc text."""
        q, results = query.lower(), []
        for doc in RAG_DOCS_DIR.glob("*.txt"):
            try:
                content = doc.read_text(encoding="utf-8")
                score   = content.lower().count(q)
                if score:
                    idx  = content.lower().find(q)
                    s, e = max(0, idx - 250), min(len(content), idx + 250)
                    ctx  = ("..." if s else "") + content[s:e] + ("..." if e < len(content) else "")
                    results.append({"filename": doc.stem, "score": score,
                                    "context": ctx,
                                    "full_content": content if full_content else ""})
            except Exception:
                pass
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:max_results]

    @staticmethod
    def delete(filename: str):
        for sfx in (".txt", ".meta.json"):
            p = RAG_DOCS_DIR / f"{filename}{sfx}"
            if p.exists():
                p.unlink()


# ============================================================================
# STREAMLIT CONFIG
# ============================================================================

    @staticmethod
    def bulk_delete(filenames: List[str]) -> Tuple[int, int]:
        """Delete multiple docs. Returns (deleted, failed)."""
        ok_n = fail_n = 0
        for filename in filenames:
            try:
                for sfx in (".txt", ".meta.json"):
                    p = RAG_DOCS_DIR / (filename + sfx)
                    if p.exists():
                        p.unlink()
                ok_n += 1
            except Exception:
                fail_n += 1
        return ok_n, fail_n

    @staticmethod
    def reindex_all(is_admin: bool = False) -> Tuple[int, int]:
        """Re-touch metadata timestamps on all stored docs. Returns (ok, failed)."""
        ok_n = fail_n = 0
        for meta_file in RAG_DOCS_DIR.glob("*.meta.json"):
            try:
                meta = json.loads(meta_file.read_text())
                meta["re_indexed"] = datetime.now().isoformat()
                meta_file.write_text(json.dumps(meta, indent=2))
                ok_n += 1
            except Exception:
                fail_n += 1
        return ok_n, fail_n

