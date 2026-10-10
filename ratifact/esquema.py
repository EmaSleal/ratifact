"""Versión de esquema de la memoria (esquema.json), migraciones y el bloqueo de escritura que las aplica."""
from __future__ import annotations

import fcntl
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from ratifact.config import ErrorMemoria, _es_repo, _mem
from ratifact.registros import _commit, _escribir_atomico


# ───────────────────────── versión de esquema de la memoria ─────────────────────────
# Cada memoria declara en esquema.json el formato con que fue escrita. Al cambiar el formato: subir VERSION_ESQUEMA
# y agregar en MIGRACIONES la función que lleva una memoria de la versión anterior a la nueva (devuelve los archivos
# que tocó). La migración corre sola, bajo el bloqueo, en la primera escritura o al cargar contexto, y queda en un
# commit propio (reversible con git). Una memoria con versión mayor que la del servidor no se toca.

VERSION_ESQUEMA = 1
ARCHIVO_ESQUEMA = "esquema.json"


def _migrar_0_a_1(mem: Path) -> list[Path]:
    """v0 = memorias anteriores al versionado. Su formato ya es el de v1: solo falta declararlo."""
    return []


MIGRACIONES = {1: _migrar_0_a_1}


def _version_esquema(mem: Path) -> int:
    archivo = mem / ARCHIVO_ESQUEMA
    if not archivo.exists():
        return 0
    try:
        return int(json.loads(archivo.read_text(encoding="utf-8"))["version"])
    except (ValueError, KeyError, TypeError) as e:
        raise ErrorMemoria(f"{archivo} está dañado ({e}); revísalo con git log en la memoria.") from e


def _escribir_esquema(mem: Path) -> Path:
    archivo = mem / ARCHIVO_ESQUEMA
    _escribir_atomico(archivo, json.dumps({"version": VERSION_ESQUEMA}) + "\n")
    return archivo


def _esquema_al_dia(proyecto: str, mem: Path) -> None:
    """Llamar con el bloqueo tomado. Migra si la memoria es más antigua; rechaza si es más nueva."""
    if not _es_repo(mem):        # memoria aún no inicializada: inicializar_memoria declara la versión
        return
    actual = _version_esquema(mem)
    if actual > VERSION_ESQUEMA:
        raise ErrorMemoria(f"La memoria de '{proyecto}' usa el esquema v{actual} y este servidor solo conoce hasta "
                           f"v{VERSION_ESQUEMA}. Actualiza memoria-proyectos (git pull) antes de usarla; no se modificó nada.")
    if actual == VERSION_ESQUEMA:
        return
    tocados: list[Path] = []
    for v in range(actual + 1, VERSION_ESQUEMA + 1):
        tocados += MIGRACIONES[v](mem)
    tocados.append(_escribir_esquema(mem))
    resultado = _commit(proyecto, tocados, f"migrar esquema v{actual} → v{VERSION_ESQUEMA}")
    if "git falló" in resultado:     # sin commit no hay vuelta atrás: se deshace y se reintenta en la próxima llamada
        subprocess.run(["git", "-C", str(mem), "reset", "-q", "--", ARCHIVO_ESQUEMA], capture_output=True)
        if actual == 0:
            (mem / ARCHIVO_ESQUEMA).unlink(missing_ok=True)
        else:
            subprocess.run(["git", "-C", str(mem), "checkout", "-q", "--", ARCHIVO_ESQUEMA], capture_output=True)
        raise ErrorMemoria(f"No se pudo versionar la migración del esquema de '{proyecto}' {resultado}; "
                           "no se escribió nada. Revisa la configuración de git de la memoria.")


@contextmanager
def _bloqueo(proyecto: str):
    mem = _mem(proyecto)
    mem.mkdir(parents=True, exist_ok=True)
    with open(mem / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            _esquema_al_dia(proyecto, mem)    # toda escritura pasa por aquí: nunca se escribe en un formato ajeno
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
