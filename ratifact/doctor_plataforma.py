"""Platform section of `ratifact doctor` (read only): WSL detection and the native Windows notice."""
from __future__ import annotations

import platform
import sys
from pathlib import Path


def _osrelease() -> str:
    try:
        return Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8")
    except OSError:
        return platform.release()


def _es_wsl() -> bool:
    return sys.platform.startswith("linux") and "microsoft" in _osrelease().lower()


def _plataforma() -> list[str]:
    """ADR-012: Windows is supported only through WSL. Informational only: it never adds a pending action."""
    if sys.platform == "win32":
        return ["⚠ Native Windows is not a supported platform: install ratifact inside WSL2, with the "
                "repositories on the WSL filesystem (not under /mnt/c). The rest of the diagnosis follows."]
    if _es_wsl():
        return ["Running inside WSL: supported; keep the repositories on the WSL filesystem"]
    return []
