# core/security_rag.py — SecurityValidator + RAGManager (improved chunking + TF-IDF search)
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from core.config import SECURITY_CONFIG, RAG_DOCS_DIR, APP_WORKSPACE


# ============================================================================
# SECURITY VALIDATOR
# ============================================================================

class SecurityValidator:
    @staticmethod
    def validate_code(code: str) -> Tuple[bool, List[str]]:
        issues = []
        for pat in SECURITY_CONFIG.BLOCKED_PATTERNS:
            if re.search(pat, code, re.IGNORECASE):
                issues.append(f"Blocked pattern: `{pat}`")
        for imp in ["os", "subprocess", "shutil", "sys", "ctypes", "pickle"]:
            if re.search(rf"\bimport\s+{imp}\b|\bfrom\s+{imp}\s+import", code):
                issues.append(f"Potentially dangerous import: `{imp}`")
        return len(issues) == 0, issues

    @staticmethod
    def sanitize(text: str, max_len: int = 10_000) -> str:
        return "".join(c for c in text[:max_len] if c.isprintable() or c in "\n\t")


# ============================================================================
# RAG MANAGER — improved chunking + TF-IDF ranked search
# ============================================================================

_CHUNK_SIZE  = 400    # characters per chunk
_CHUNK_OVER  = 80     # overlap between chunks

def _chunk_text(text: str) -> List[str]:
    """
    Split text into overlapping chunks of ~_CHUNK_SIZE chars,
    breaking at sentence/paragraph boundaries where possible.
    """
    chunks = []
    start  = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        # Try to break at a sentence boundary
        if end < len(text):
            for sep in ("\n\n", "\n", ". ", "? ", "! ", " "):
                pos = text.rfind(sep, start + _CHUNK_SIZE // 2, end)
                if pos != -1:
                    end = pos + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = max(start + 1, end - _CHUNK_OVER)
    return chunks


def _tf_idf_score(query_terms: List[str], chunk: str,
                  doc_freq: Dict[str, int], total_docs: int) -> float:
    """
    Lightweight TF-IDF: rewards chunks where query terms appear
    frequently (TF) and are rare across all documents (IDF).
    """
    chunk_lower = chunk.lower()
    score = 0.0
    word_count = max(len(chunk_lower.split()), 1)
    for term in query_terms:
        tf  = chunk_lower.count(term) / word_count
        df  = doc_freq.get(term, 1)
        idf = math.log((total_docs + 1) / (df + 1)) + 1
        score += tf * idf
    return round(score, 6)


class RAGManager:

    # ── Ingest ───────────────────────────────────────────────────────────────

    @staticmethod
    def process(file_path: Path, file_name: str) -> Tuple[bool, str]:
        try:
            suffix = file_path.suffix.lower()
            if suffix == ".pdf":
                try:
                    import PyPDF2
                    with open(file_path, "rb") as f:
                        content = "\n".join(
                            p.extract_text() or "" for p in PyPDF2.PdfReader(f).pages
                        )
                except ImportError:
                    return False, "PyPDF2 not installed — run: pip install PyPDF2"
            else:
                content = file_path.read_text(encoding="utf-8", errors="ignore")

            if not content.strip():
                return False, "File appears to be empty or contains no extractable text"

            # Chunk and store
            chunks = _chunk_text(content)
            out    = RAG_DOCS_DIR / f"{file_name}.txt"
            meta   = RAG_DOCS_DIR / f"{file_name}.meta.json"
            out.write_text(content, encoding="utf-8")
            meta.write_text(json.dumps({
                "filename":    file_name,
                "uploaded":    datetime.now().isoformat(),
                "size":        len(content),
                "chunk_count": len(chunks),
                "path":        str(out),
                "suffix":      suffix,
            }, indent=2))
            return True, f"{len(content):,} chars  ·  {len(chunks)} chunks"
        except Exception as e:
            return False, str(e)

    # ── List / delete ─────────────────────────────────────────────────────────

    @staticmethod
    def list_docs() -> List[Dict]:
        return sorted(
            [json.loads(m.read_text()) for m in RAG_DOCS_DIR.glob("*.meta.json")],
            key=lambda x: x.get("uploaded", ""), reverse=True,
        )

    @staticmethod
    def get_content(filename: str) -> str:
        p = RAG_DOCS_DIR / f"{filename}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    @staticmethod
    def delete(filename: str):
        for sfx in (".txt", ".meta.json"):
            p = RAG_DOCS_DIR / f"{filename}{sfx}"
            if p.exists():
                p.unlink()

    # ── Search ────────────────────────────────────────────────────────────────

    @staticmethod
    def search(query: str, max_results: int = 5) -> List[Dict]:
        """
        TF-IDF ranked search across all RAG documents.
        Returns list of {filename, score, context, chunk_idx} dicts,
        sorted by relevance descending.
        """
        if not query.strip():
            return []

        # Tokenise query: lowercase words of 3+ chars
        query_terms = [t for t in re.split(r'\W+', query.lower()) if len(t) >= 3]
        if not query_terms:
            # Short query — fall back to substring match
            query_terms = [query.lower()]

        # Build document-frequency map (per whole document)
        docs = list(RAG_DOCS_DIR.glob("*.txt"))
        total_docs = len(docs)
        if total_docs == 0:
            return []

        doc_freq: Dict[str, int] = {}
        doc_texts: Dict[str, str] = {}
        for doc in docs:
            try:
                text = doc.read_text(encoding="utf-8")
                doc_texts[str(doc)] = text
                text_lower = text.lower()
                for term in query_terms:
                    if term in text_lower:
                        doc_freq[term] = doc_freq.get(term, 0) + 1
            except Exception:
                pass

        # Score every chunk of every document
        results = []
        for doc_path, content in doc_texts.items():
            stem = Path(doc_path).stem   # e.g. "report.pdf"
            chunks = _chunk_text(content)
            for i, chunk in enumerate(chunks):
                score = _tf_idf_score(query_terms, chunk, doc_freq, total_docs)
                if score > 0:
                    results.append({
                        "filename":  stem,
                        "score":     score,
                        "context":   chunk,
                        "chunk_idx": i,
                        "total_chunks": len(chunks),
                    })

        # Sort by score, deduplicate (keep best chunk per doc), return top N
        results.sort(key=lambda x: x["score"], reverse=True)
        seen_files: set = set()
        deduped = []
        for r in results:
            # Allow up to 2 chunks per document in top results
            key = (r["filename"], r["chunk_idx"] // 3)
            if key not in seen_files:
                seen_files.add(key)
                deduped.append(r)
        return deduped[:max_results]
