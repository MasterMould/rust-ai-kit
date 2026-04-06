# core/models.py — ModelManager: get/set/list/download/delete GGUF models
# Mirrors _load_active_model(), _switch_model_menu(), _remove_model_menu()
# from ai_stack_manager.sh.
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.config import MODEL_DIR, MODEL_CONFIG, MODEL_CONFIGS_DIR, ModelRunConfig

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
# MODEL CONFIG MANAGER — per-model run configuration (llama-server flags)
# Configs are stored as JSON in config/model_configs/<model_stem>.json
# so each .gguf file can have its own saved settings.
# ============================================================================

class ModelConfigManager:

    @staticmethod
    def _cfg_path(model_path: str) -> Path:
        """Return the JSON config path for a given .gguf path."""
        stem = Path(model_path).stem
        return MODEL_CONFIGS_DIR / f"{stem}.json"

    @staticmethod
    def load(model_path: str) -> ModelRunConfig:
        """
        Load saved config for model_path.
        Returns default ModelRunConfig if no saved config exists yet.
        """
        cfg_file = ModelConfigManager._cfg_path(model_path)
        if not cfg_file.exists():
            return ModelRunConfig()
        try:
            data = json.loads(cfg_file.read_text())
            return ModelRunConfig(**{
                k: v for k, v in data.items()
                if k in ModelRunConfig.__dataclass_fields__
            })
        except Exception as e:
            logger.warning(f"ModelConfigManager.load: {e} — using defaults")
            return ModelRunConfig()

    @staticmethod
    def save(model_path: str, cfg: ModelRunConfig) -> bool:
        """Persist a ModelRunConfig to JSON."""
        try:
            cfg_file = ModelConfigManager._cfg_path(model_path)
            import dataclasses
            cfg_file.write_text(json.dumps(dataclasses.asdict(cfg), indent=2))
            return True
        except Exception as e:
            logger.error(f"ModelConfigManager.save: {e}")
            return False

    @staticmethod
    def to_server_args(cfg: ModelRunConfig, model_path: str) -> List[str]:
        """
        Convert a ModelRunConfig to a llama-server argument list.
        The caller prepends the binary path and appends --host/--port/--api-key.
        """
        args: List[str] = [
            "--model",          model_path,
            "--n-gpu-layers",   str(cfg.n_gpu_layers),
            "--ctx-size",       str(cfg.ctx_size),
            "--batch-size",     str(cfg.batch_size),
            "--threads",        str(cfg.threads),
            "--split-mode",     cfg.split_mode,
            "--main-gpu",       str(cfg.main_gpu),
            "--parallel",       str(cfg.parallel),
        ]
        if cfg.flash_attn:    args.append("--flash-attn")
        if cfg.cont_batching: args.append("--cont-batching")
        if cfg.mlock:         args.append("--mlock")
        if cfg.jinja:         args.append("--jinja")
        return args

    @staticmethod
    def to_cli_args(cfg: ModelRunConfig, model_path: str) -> List[str]:
        """
        Convert a ModelRunConfig to a llama-cli argument list.
        llama-cli uses the same flags minus the server-only ones.
        """
        args: List[str] = [
            "--model",          model_path,
            "--n-gpu-layers",   str(cfg.n_gpu_layers),
            "--ctx-size",       str(cfg.ctx_size),
            "--batch-size",     str(cfg.batch_size),
            "--threads",        str(cfg.threads),
            "--temp",           str(cfg.temperature),
            "--top-p",          str(cfg.top_p),
            "--min-p",          str(cfg.min_p),
            "--repeat-penalty", str(cfg.repeat_penalty),
            "--split-mode",     cfg.split_mode,
            "--main-gpu",       str(cfg.main_gpu),
        ]
        if cfg.flash_attn: args.append("--flash-attn")
        if cfg.mlock:      args.append("--mlock")
        if cfg.jinja:      args.append("--jinja")
        return args

    @staticmethod
    def to_command_preview(cfg: ModelRunConfig, model_path: str,
                           binary: str = "./llama-cli") -> str:
        """
        Return a shell command string suitable for display in a code block.
        Uses llama-cli flags by default; pass binary='./llama-server' for server mode.
        """
        is_server = "server" in binary
        if is_server:
            args = ModelConfigManager.to_server_args(cfg, model_path)
        else:
            args = ModelConfigManager.to_cli_args(cfg, model_path)

        lines = [binary]
        i = 0
        while i < len(args):
            a = args[i]
            if a.startswith("--"):
                # check if next arg is a value (not a flag)
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    lines.append(f"  {a} {args[i + 1]} \\")
                    i += 2
                    continue
                else:
                    lines.append(f"  {a} \\")
            i += 1
        # trim trailing backslash on last line
        if lines[-1].endswith(" \\"):
            lines[-1] = lines[-1][:-2]
        return "\n".join(lines)

# ============================================================================
# HUGGING FACE SEARCH CLIENT
# Live search against the HF Hub API — no auth token required for public models.
# API docs: https://huggingface.co/docs/hub/api
# ============================================================================

HF_API = "https://huggingface.co/api"
HF_BASE = "https://huggingface.co"

# Quant quality tiers — used to score/sort file choices for the user.
# Lower index = higher priority recommendation for A770 16 GB.
_QUANT_PREFERENCE = [
    "Q4_K_M", "Q5_K_M", "Q4_K_S", "IQ4_XS", "IQ4_NL",
    "Q3_K_M", "Q3_K_L", "IQ3_M",
    "Q8_0", "Q6_K",
    "Q2_K", "IQ2_M", "IQ1_M",
    "Q4_0", "Q5_0",
]


def _quant_score(filename: str) -> int:
    """Lower score = recommended first on A770."""
    fn = filename.upper()
    for i, q in enumerate(_QUANT_PREFERENCE):
        if q in fn:
            return i
    return 99


class HFSearchClient:
    """
    Thin wrapper around the public HuggingFace Hub REST API.
    All methods return plain dicts/lists — no huggingface_hub library required.
    Gracefully returns [] / {} on any network or parse error so the UI
    can show a friendly message rather than crash.
    """

    TIMEOUT = 12   # seconds — aggressive but avoids frozen UI

    @staticmethod
    def search(query: str, sort: str = "downloads", limit: int = 20,
               author: str = "") -> List[Dict]:
        """
        Search public GGUF repos.
        Returns list of dicts: {id, downloads, likes, lastModified, author, tags}.
        sort options: 'downloads' | 'trending' | 'likes' | 'lastModified'
        """
        params: Dict = {
            "library": "gguf",
            "sort":    sort,
            "limit":   limit,
        }
        if query:
            params["search"] = query
        if author:
            params["author"] = author

        try:
            r = requests.get(f"{HF_API}/models", params=params,
                             timeout=HFSearchClient.TIMEOUT)
            r.raise_for_status()
            raw = r.json()
            return [
                {
                    "id":           m.get("id", ""),
                    "author":       m.get("author", m.get("id", "").split("/")[0]),
                    "downloads":    m.get("downloads", 0),
                    "likes":        m.get("likes", 0),
                    "lastModified": m.get("lastModified", ""),
                    "tags":         m.get("tags", []),
                    "gated":        m.get("gated", False),
                }
                for m in raw
                if not m.get("gated")       # skip gated / access-restricted repos
                and m.get("id", "")
            ]
        except Exception as e:
            logger.warning(f"HFSearchClient.search: {e}")
            return []

    @staticmethod
    def repo_files(repo_id: str) -> List[Dict]:
        """
        Fetch the .gguf file list for a repo.
        Returns list of dicts: {filename, size_bytes, size_human, url, quant_score, recommended}.
        Sorted: recommended quant first, then by quant_score.
        """
        try:
            r = requests.get(f"{HF_API}/models/{repo_id}",
                             timeout=HFSearchClient.TIMEOUT)
            r.raise_for_status()
            info = r.json()
            siblings = info.get("siblings", [])
            files = []
            for s in siblings:
                fn = s.get("rfilename", "")
                if not fn.lower().endswith(".gguf"):
                    continue
                # skip split shards — only list the first shard or unsplit files
                if "-of-" in fn and not fn.endswith("-00001-of-00001.gguf"):
                    if not fn.endswith("-00001-of-00002.gguf") and \
                       "-00001-of-" not in fn:
                        continue
                sz = s.get("size", 0) or 0
                files.append({
                    "filename":    fn,
                    "size_bytes":  sz,
                    "size_human":  f"{sz / 1e9:.2f} GB" if sz else "? GB",
                    "size_gb":     sz / 1e9 if sz else 0.0,
                    "url":         f"{HF_BASE}/{repo_id}/resolve/main/{fn}",
                    "quant_score": _quant_score(fn),
                    "recommended": _quant_score(fn) == min(_quant_score(f["filename"])
                                                           for f in [{"filename": fn}])
                })
            # Sort: best quant first
            files.sort(key=lambda x: x["quant_score"])
            # Mark the top-scored file as recommended
            if files:
                best = files[0]["quant_score"]
                for f in files:
                    f["recommended"] = f["quant_score"] == best
            return files
        except Exception as e:
            logger.warning(f"HFSearchClient.repo_files({repo_id}): {e}")
            return []

    @staticmethod
    def trending(limit: int = 15) -> List[Dict]:
        """Top trending GGUF repos right now."""
        return HFSearchClient.search("", sort="trending", limit=limit)

    @staticmethod
    def popular_authors() -> List[str]:
        """Well-known GGUF quantisers — shown as quick-filter chips."""
        return ["bartowski", "unsloth", "MaziyarPanahi", "lmstudio-community",
                "TheBloke", "ggml-org"]