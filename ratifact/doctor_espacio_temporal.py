"""Read-only inventory of Claude Code's temporary session directory."""
from __future__ import annotations

import os
import time
from pathlib import Path

DEFAULT_ROOT = Path("/tmp") / f"claude-{getattr(os, 'getuid', lambda: 0)()}"
ENV_ROOT = "RATIFACT_CLAUDE_CODE_TEMP"
SIZE_WARNING_BYTES = 500 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_SECONDS = 2.0
MAX_SENSITIVE_FILES = 20


def _sensible(name: str) -> str | None:
    name = name.lower()
    if name == ".env" or name.startswith(".env."):
        return ".env"
    for suffix in (".sql.gz", ".sql", ".dump", ".pem", ".key"):
        if name.endswith(suffix):
            return suffix
    return None


def _tamano(n: int) -> str:
    if n < 1024:
        return f"{n} bytes"
    for unidad in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unidad == "TB":
            return f"{n:.1f} {unidad}"
    return f"{n:.1f} TB"


def _ruta_base(raiz: Path | str | None = None) -> Path:
    if raiz is not None:
        return Path(raiz).expanduser()
    override = os.environ.get(ENV_ROOT)
    return Path(override).expanduser() if override else DEFAULT_ROOT


def seccion(acciones: list[str] | None = None, raiz: Path | str | None = None) -> list[str]:
    """Return doctor lines; never read file contents or mutate the tree."""
    base = _ruta_base(raiz)
    lineas = ["Claude Code temporary space (other clients are not inspected):", f"  Folder: {base}"]
    try:
        if not base.exists():
            return lineas + ["  Not found; this is not an error."]
        if base.is_symlink() or not base.is_dir():
            return lineas + ["  Not a directory (or a symbolic link); not inspected."]
    except OSError:
        return lineas + ["  Could not inspect the folder."]

    started = time.monotonic()
    pending = [base]
    sizes: dict[str, int] = {}
    sensitive: list[tuple[str, Path]] = []
    sensitive_counts = {pattern: 0 for pattern in (".env", ".dump", ".key", ".pem", ".sql", ".sql.gz")}
    total = entries_seen = permission_errors = 0
    partial = False

    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entries_seen >= MAX_ENTRIES or time.monotonic() - started >= MAX_SECONDS:
                        partial = True
                        break
                    entries_seen += 1
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if current == base:
                                sizes.setdefault(entry.name, 0)
                            pending.append(Path(entry.path))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        size = entry.stat(follow_symlinks=False).st_size
                    except PermissionError:
                        permission_errors += 1
                        continue
                    except OSError:
                        continue

                    total += size
                    relative = Path(entry.path).relative_to(base)
                    if len(relative.parts) > 1:
                        project = relative.parts[0]
                        sizes[project] = sizes.get(project, 0) + size
                    pattern = _sensible(entry.name)
                    if pattern:
                        sensitive_counts[pattern] = sensitive_counts.get(pattern, 0) + 1
                        sensitive.append((str(Path(entry.path)), Path(entry.path)))
                if partial:
                    break
        except PermissionError:
            permission_errors += 1
        except OSError:
            continue
        if entries_seen >= MAX_ENTRIES or time.monotonic() - started >= MAX_SECONDS:
            if pending:
                partial = True
                break

    lineas.append(f"  Total: {_tamano(total)}")
    lineas.append("  Project folders: " + (str(len(sizes)) if sizes else "0"))
    lineas.append("  By project (largest first):")
    if sizes:
        lineas.extend(f"    {name}: {_tamano(size)}" for name, size in sorted(sizes.items(), key=lambda item: (-item[1], item[0])))
    else:
        lineas.append("    none")
    lineas.append(f"  Sensitive-looking files: {len(sensitive)} total" if sensitive else
                  "  Sensitive-looking files: none")
    for path, _ in sorted(sensitive, key=lambda item: item[0])[:MAX_SENSITIVE_FILES]:
        lineas.append(f"    {path}")
    if len(sensitive) > MAX_SENSITIVE_FILES:
        lineas.append(f"    … first {MAX_SENSITIVE_FILES} shown; {len(sensitive)} total")
    counts = ", ".join(f"{pattern}={count}" for pattern, count in sorted(sensitive_counts.items()))
    lineas.append(f"  Counts by pattern: {counts}")
    if permission_errors:
        lineas.append(f"  Permission errors: {permission_errors} (some entries could not be inspected)")
    if partial:
        lineas.append(f"  Partial report: stopped at the {MAX_ENTRIES}-entry or {MAX_SECONDS:g}-second limit.")

    warning = total > SIZE_WARNING_BYTES or bool(sensitive)
    if total > SIZE_WARNING_BYTES:
        lineas.append(f"  ⚠ Total exceeds {_tamano(SIZE_WARNING_BYTES)}.")
    if sensitive:
        lineas.append("  ⚠ Filenames can indicate sensitive data; files were not opened.")
    if warning:
        aviso = (f"Review Claude Code temporary folder {base}; you decide whether to delete it. "
                 "It may contain copies from an active session.")
        lineas.append(f"  ⚠ {aviso}")
        if acciones is not None:
            acciones.append(aviso)
    return lineas
