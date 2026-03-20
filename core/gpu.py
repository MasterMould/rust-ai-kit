# core/gpu.py — Intel Arc A770 GPU detection (mirrors ai_stack_manager.sh)
import re
import subprocess
from pathlib import Path
from typing import Optional

class GPUDetector:
    @staticmethod
    def clinfo_visible() -> bool:
        """clinfo -l | grep -qi 'intel' — exact test used by the shell script."""
        try:
            r = subprocess.run(["clinfo", "-l"], capture_output=True, text=True, timeout=5)
            return "intel" in r.stdout.lower()
        except Exception:
            return False

    @staticmethod
    def xpu_smi_line() -> str:
        """xpu-smi discovery | grep -i 'arc|A770' | head -1"""
        try:
            r = subprocess.run(["xpu-smi", "discovery"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if re.search(r"arc|a770", line, re.IGNORECASE):
                    return line.strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def arc_freq_mhz() -> Optional[str]:
        """Read current core freq from sysfs — fallback when xpu-smi absent."""
        for p in Path("/sys/class/drm").glob("card*/device/tile0/gt0/freq0/cur_freq_mhz"):
            try:
                return p.read_text().strip()
            except Exception:
                pass
        return None

    @staticmethod
    def gpu_layers() -> int:
        """99 when GPU visible (SYCL), 0 for CPU fallback — mirrors GPU_LAYERS in script."""
        return 99 if GPUDetector.clinfo_visible() else 0


# ============================================================================
# STACK MANAGER — mirrors start/stop/restart/systemd/benchmark in the script
# ============================================================================
