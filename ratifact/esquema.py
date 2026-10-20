"""Versión de esquema de la memoria (schema.json; esquema.json en v0/v1), migraciones y el bloqueo de escritura que las
aplica."""
from __future__ import annotations

import fcntl
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from ratifact.config import ErrorMemoria, _es_repo, _mem
from ratifact.migracion_v2 import _migrar_1_a_2
from ratifact.registros import _escribir_atomico
from ratifact.vocabulario import CARPETAS_V1


# ───────────────────────── versión de esquema de la memoria ─────────────────────────
# Cada memoria declara en schema.json el formato con que fue escrita (en v0/v1 era esquema.json). Al cambiar el
# formato: subir VERSION_ESQUEMA y agregar en MIGRACIONES la función que lleva una memoria de la versión anterior a la
# nueva (devuelve las líneas del informe que van al commit). La migración corre sola, bajo el bloqueo, en el primer
# acceso a la memoria; exige un repo git limpio, deja antes un tag pre-vN y queda en un commit propio (reversible con
# git). Si algo falla, la memoria vuelve al tag y se reintenta en la próxima llamada. Una memoria con versión mayor que
# la del servidor no se toca.

VERSION_ESQUEMA = 2
ARCHIVO_ESQUEMA = "schema.json"
# Centinela (ADR-030): un servidor anterior a v2 solo lee esquema.json y, si falta, tomaría la memoria por v0 y la
# reescribiría como v1. Por eso cada escritura de schema.json escribe también esquema.json con la misma versión (sin
# otros campos): el servidor viejo lee "v2" y se niega. Se quita en 1.1, junto con el respaldo MEMORIA_PROYECTOS_*
# (ADR-028).
ARCHIVO_ESQUEMA_V1 = "esquema.json"
IDIOMA_MIGRADAS = "es"    # content_language de las memorias existentes (ADR-028); las nuevas nacen en "en"
IDIOMA_NUEVAS = "en"


def _migrar_0_a_1(mem: Path) -> list[str]:
    """v0 = memorias anteriores al versionado. Su formato ya es el de v1: solo falta declararlo."""
    return []


MIGRACIONES = {1: _migrar_0_a_1, 2: _migrar_1_a_2}


def _leer_json(archivo: Path) -> dict:
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        int(datos["version"])
        return datos
    except (ValueError, KeyError, TypeError) as e:
        raise ErrorMemoria(f"{archivo} is corrupted ({e}); check it with git log in the memory.") from e


def _version_esquema(mem: Path) -> int:
    """schema.json manda si existe (esquema.json se ignora entonces); si solo está esquema.json, la memoria es v0/v1."""
    if (mem / ARCHIVO_ESQUEMA).exists():
        return int(_leer_json(mem / ARCHIVO_ESQUEMA)["version"])
    if not (mem / ARCHIVO_ESQUEMA_V1).exists():
        return 0
    version = int(_leer_json(mem / ARCHIVO_ESQUEMA_V1)["version"])
    if 1 < version <= VERSION_ESQUEMA:
        raise ErrorMemoria(f"{mem / ARCHIVO_ESQUEMA_V1} says v{version} but {ARCHIVO_ESQUEMA} is missing; the memory is "
                           "damaged. Check it with git log before continuing; nothing was changed.")
    return version


def _idioma_contenido(mem: Path) -> str:
    """content_language de schema.json (ADR-016, ADR-029)."""
    archivo = mem / ARCHIVO_ESQUEMA
    return str(_leer_json(archivo).get("content_language") or IDIOMA_NUEVAS) if archivo.exists() else IDIOMA_NUEVAS


def _escribir_esquema(mem: Path, idioma: str) -> list[Path]:
    """schema.json con versión e idioma del contenido, y el centinela esquema.json con la misma versión (ADR-030)."""
    nuevo, centinela = mem / ARCHIVO_ESQUEMA, mem / ARCHIVO_ESQUEMA_V1
    _escribir_atomico(nuevo, json.dumps({"version": VERSION_ESQUEMA, "content_language": idioma}) + "\n")
    _escribir_atomico(centinela, json.dumps({"version": VERSION_ESQUEMA}) + "\n")
    return [nuevo, centinela]


def _inicializada(mem: Path) -> bool:
    """¿Hay una memoria aquí? Repo git, archivo de esquema o carpetas de registros (v1 o v2)."""
    nombres = (ARCHIVO_ESQUEMA, ARCHIVO_ESQUEMA_V1, *CARPETAS_V1, *CARPETAS_V1.values())
    return _es_repo(mem) or any((mem / n).exists() for n in nombres)


def _git(mem: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(mem), *args], capture_output=True, text=True)


def _verificar_precondiciones(proyecto: str, mem: Path) -> None:
    """Repo git con al menos un commit y `git status` limpio (salvo .lock); si no, no se toca nada."""
    if not _es_repo(mem):
        raise ErrorMemoria(f"The memory of '{proyecto}' ({mem}) is not a git repository: it cannot be migrated to "
                           f"schema v{VERSION_ESQUEMA} with a backup. Run `git init` and make a commit in it; nothing "
                           "was changed.")
    if _git(mem, "rev-parse", "-q", "--verify", "HEAD").returncode != 0:
        raise ErrorMemoria(f"The memory of '{proyecto}' ({mem}) has no commits: make one before migrating to schema "
                           f"v{VERSION_ESQUEMA}; nothing was changed.")
    estado = _git(mem, "status", "--porcelain", "--untracked-files=all")
    sucios = [l for l in estado.stdout.splitlines() if l[3:].strip('"') != ".lock"]
    if estado.returncode != 0 or sucios:
        detalle = ", ".join(l[3:] for l in sucios[:5]) or estado.stderr.strip()[:200]
        raise ErrorMemoria(f"The memory of '{proyecto}' ({mem}) has uncommitted changes ({detalle}): migrating to "
                           f"schema v{VERSION_ESQUEMA} requires a clean `git status`. Commit or discard them; nothing "
                           "was changed.")


def _crear_tag(mem: Path) -> str:
    """Tag pre-vN en HEAD; si ya existe, pre-vN-2, -3, …"""
    base = f"pre-v{VERSION_ESQUEMA}"
    nombre, n = base, 1
    while _git(mem, "rev-parse", "-q", "--verify", f"refs/tags/{nombre}").returncode == 0:
        n += 1
        nombre = f"{base}-{n}"
    r = _git(mem, "tag", nombre)
    if r.returncode != 0:
        raise ErrorMemoria(f"Could not create tag {nombre} in {mem} ({r.stderr.strip()[:200]}); nothing was "
                           "changed.")
    return nombre


def _carpetas_vacias(mem: Path) -> list[str]:
    """Carpetas v1 vacías: git no las versiona, así que ni el reset ni el tag las devuelven."""
    return [d for d in CARPETAS_V1 if (mem / d).is_dir() and not any((mem / d).iterdir())]


def _restaurar(mem: Path, tag: str, vacias: list[str]) -> None:
    """Vuelve la memoria al tag (archivos versionados y nuevos sin versionar de la migración), recrea las carpetas v1
    vacías que había y borra el tag: el próximo intento lo vuelve a crear con el mismo nombre."""
    _git(mem, "reset", "-q", "--hard", tag)
    _git(mem, "clean", "-fdq", "-e", ".lock")
    for d in vacias:
        nueva = mem / CARPETAS_V1[d]
        if nueva.is_dir() and not any(nueva.iterdir()):
            nueva.rmdir()
        (mem / d).mkdir(exist_ok=True)
    _git(mem, "tag", "-d", tag)


def _migrar(proyecto: str, mem: Path, actual: int) -> str:
    """Migra de `actual` a VERSION_ESQUEMA en un solo commit, con tag de respaldo. Devuelve el aviso para la
    respuesta."""
    _verificar_precondiciones(proyecto, mem)
    vacias = _carpetas_vacias(mem)
    tag = _crear_tag(mem)
    mensaje = f"memory: migrate schema v{actual} → v{VERSION_ESQUEMA}"
    try:
        informe: list[str] = []
        for v in range(actual + 1, VERSION_ESQUEMA + 1):
            informe += MIGRACIONES[v](mem)
        idioma = _idioma_contenido(mem) if (mem / ARCHIVO_ESQUEMA).exists() else IDIOMA_MIGRADAS
        _escribir_esquema(mem, idioma)
        for paso in (["add", "-A"], ["rm", "-q", "--cached", "--ignore-unmatch", "--", ".lock"],
                     ["commit", "-q", "-m", mensaje, "-m", "\n".join(informe)]):
            r = _git(mem, *paso)
            if r.returncode != 0:
                raise RuntimeError(f"git {paso[0]} failed: {(r.stdout + r.stderr).strip()[:200]}")
        sha = _git(mem, "rev-parse", "--short", "HEAD").stdout.strip()
    except Exception as e:
        _restaurar(mem, tag, vacias)
        raise ErrorMemoria(f"Could not migrate the memory of '{proyecto}' to schema v{VERSION_ESQUEMA} ({e}); it was "
                           "left exactly as it was and the migration is retried on the next call.") from e
    return (f"(memory of '{proyecto}' migrated to schema v{VERSION_ESQUEMA} · commit {sha} · backup in tag "
            f"{tag} · details: git show in the memory)")


def _esquema_al_dia(proyecto: str, mem: Path) -> str:
    """Llamar con el bloqueo tomado. Migra si la memoria es más antigua; rechaza si es más nueva. Devuelve el aviso
    de la migración ("" si no hubo)."""
    if not _inicializada(mem):    # memoria aún no inicializada: inicializar_memoria declara la versión
        return ""
    actual = _version_esquema(mem)
    if actual > VERSION_ESQUEMA:
        raise ErrorMemoria(f"The memory of '{proyecto}' uses schema v{actual} and this server only knows up to "
                           f"v{VERSION_ESQUEMA}. Update ratifact (git pull) before using it; nothing was changed.")
    if actual == VERSION_ESQUEMA:
        return ""
    return _migrar(proyecto, mem, actual)


def _asegurar_esquema(proyecto: str) -> str:
    """Primer acceso (lo llama cada herramienta con `proyecto`, antes de ejecutarla): lectura barata de la versión sin
    bloqueo y, solo si la memoria está atrasada, migración bajo el bloqueo. Un proyecto que no se puede resolver no es
    asunto de este paso: la herramienta da su propio error."""
    try:
        mem = _mem(proyecto)
    except Exception:
        return ""
    if not _inicializada(mem) or _version_esquema(mem) == VERSION_ESQUEMA:
        return ""
    with _bloqueo(proyecto) as aviso:
        return aviso


@contextmanager
def _bloqueo(proyecto: str):
    mem = _mem(proyecto)
    mem.mkdir(parents=True, exist_ok=True)
    with open(mem / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield _esquema_al_dia(proyecto, mem)    # toda escritura pasa por aquí: nunca se escribe en un formato ajeno
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
