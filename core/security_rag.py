# core/security_rag.py — SecurityValidator + RAGManager
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from core.config import SECURITY_CONFIG, RAG_DOCS_DIR

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
    def process(file_path: Path, file_name: str) -> Tuple[bool, str]:
        try:
            if file_path.suffix.lower() == ".pdf":
                try:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        content = "".join(p.extract_text() for p in PyPDF2.PdfReader(f).pages)
                except ImportError:
                    content = "PyPDF2 not installed: pip install PyPDF2"
            else:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            out  = RAG_DOCS_DIR / f"{file_name}.txt"
            meta = RAG_DOCS_DIR / f"{file_name}.meta.json"
            out.write_text(content, encoding="utf-8")
            meta.write_text(json.dumps({
                "filename": file_name, "uploaded": datetime.now().isoformat(),
                "size": len(content), "path": str(out),
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
    def search(query: str, max_results: int = 3) -> List[Dict]:
        q, results = query.lower(), []
        for doc in RAG_DOCS_DIR.glob("*.txt"):
            try:
                content = doc.read_text(encoding="utf-8")
                score   = content.lower().count(q)
                if score:
                    idx  = content.lower().find(q)
                    s, e = max(0, idx - 250), min(len(content), idx + 250)
                    ctx  = ("..." if s else "") + content[s:e] + ("..." if e < len(content) else "")
                    results.append({"filename": doc.stem, "score": score, "context": ctx})
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
