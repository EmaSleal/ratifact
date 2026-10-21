"""Safe edits of files that belong to other programs (`ratifact install`, T-013): the new text is validated by parsing
it again, the original is copied to `<file>.bak-ratifact-<date>` (never overwritten: -2, -3… if one exists) and the
replacement is atomic (temporary file in the same folder + os.replace, keeping the permissions). If validation fails,
nothing is written. Files inside a repository (en_estado=True) are backed up under
$XDG_STATE_HOME/ratifact/backups/<date>/<absolute path>, so no backup file ever lands in the user's repositories."""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from ratifact import rutas

SUFIJO = ".bak-ratifact-"


class ErrorInstalacion(Exception):
    pass


def respaldo_libre(ruta: Path, en_estado: bool = False) -> Path:
    """Free backup path: next to the file, or mirrored under the state dir. An earlier backup is never overwritten:
    a second one on the same day gets -2, -3…"""
    hoy = _dt.date.today().isoformat()
    if en_estado:
        base = rutas.respaldos() / hoy / str(ruta.absolute()).lstrip("/")
    else:
        base = ruta.with_name(f"{ruta.name}{SUFIJO}{hoy}")
    destino, n = base, 1
    while destino.exists() or destino.is_symlink():
        n += 1
        destino = base.with_name(f"{base.name}-{n}")
    return destino


def leer_json(ruta: Path) -> dict:
    """Content of a JSON client file (an empty dict if it does not exist). ErrorInstalacion with the line and column
    if it is not valid JSON or not an object."""
    if not ruta.exists():
        return {}
    texto = ruta.read_text(encoding="utf-8")
    try:
        datos = json.loads(texto) if texto.strip() else {}
    except json.JSONDecodeError as e:
        raise ErrorInstalacion(f"{ruta} is not valid JSON (line {e.lineno}, column {e.colno}: {e.msg}); fix it by "
                               "hand, nothing was changed.") from None
    if not isinstance(datos, dict):
        raise ErrorInstalacion(f"{ruta} does not contain a JSON object; nothing was changed.")
    return datos


def texto_json(datos: dict) -> str:
    return json.dumps(datos, indent=2, ensure_ascii=False) + "\n"


def validar_json(texto: str) -> None:
    try:
        json.loads(texto)
    except ValueError as e:
        raise ErrorInstalacion(f"the generated JSON does not parse ({e}); nothing was changed.") from None


def respaldar(ruta: Path, en_estado: bool = False) -> Path | None:
    """Copy of `ruta` next to it or under the state dir (None if it does not exist)."""
    if not ruta.exists():
        return None
    bak = respaldo_libre(ruta, en_estado)
    bak.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ruta, bak)
    return bak


def escribir_validado(ruta: Path, texto: str, validar: Callable[[str], None], en_estado: bool = False) -> Path | None:
    """Validates `texto`, backs up `ruta` and replaces it atomically. Returns the backup (None for a new file). A
    symbolic link (e.g. CLAUDE.md → AGENTS.md, or a dotfiles manager) is kept: its target is what gets replaced."""
    validar(texto)
    ruta = ruta.resolve() if ruta.is_symlink() else ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
            f.flush()
            os.fsync(f.fileno())
        with open(tmp, encoding="utf-8") as f:     # what reaches the disk is what was validated
            validar(f.read())
        if ruta.exists():
            shutil.copymode(ruta, tmp)
        bak = respaldar(ruta, en_estado)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return bak
