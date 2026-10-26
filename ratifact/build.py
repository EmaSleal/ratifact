"""Build id and self-diagnosis of the running server (ADR-037).

There are three copies of ratifact: the source (git repository), the installation (uv tool directory, which the
/run-task skills link to) and the running process (one `ratifact serve` per client). This module detects two drifts:

- D2 (installation newer than the process): at startup the server computes its build id `<version>+<7 hex>` (content
  hash of its own package, skills included, bytecode excluded) and a cheap fingerprint (relative path, size and mtime
  of each file). `obsoleto()` takes the fingerprint again (stat only, cached a few seconds); if it changed or the
  directory is gone, the process runs code that is no longer on disk.
- D1 (source newer than the installation): when uv installed the package from a local folder (its tool receipt),
  `fuente_desfasada()` compares the package folder in that source with the installed one.

Nothing here writes, signals or restarts anything."""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ratifact import __version__

PAQUETE = Path(__file__).resolve().parent
TTL = 5.0                       # seconds a fingerprint check stays cached
RECIBO = "uv-receipt.toml"      # what `uv tool install` records next to the tool environment

RECORDATORIO = ("Restart the clients so they load the installed `ratifact` server (a running server keeps the code "
                "it started with), then verify with `ratifact doctor`.")

Huella = frozenset   # of (relative path, size, mtime_ns)


def _archivos(raiz: Path) -> list[Path]:
    """Package files, skills included; __pycache__ and *.pyc excluded (bytecode is not what the agent receives and
    Python rewrites it on its own). Symlinked directories are not followed."""
    salida = []
    for actual, dirs, nombres in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        salida += [Path(actual) / n for n in nombres if not n.endswith(".pyc")]
    return sorted(salida)


def huella(raiz: Path) -> Huella | None:
    """{(relative path, size, mtime_ns)} of the package files; None if the directory does not exist. Stat only."""
    if not raiz.is_dir():
        return None
    salida = set()
    for p in _archivos(raiz):
        try:
            st = p.stat()
        except OSError:
            continue
        salida.add((p.relative_to(raiz).as_posix(), st.st_size, st.st_mtime_ns))
    return frozenset(salida)


def hash_contenido(raiz: Path) -> str:
    """sha256 of every package file (relative path and bytes, in path order), same filter as `huella`."""
    h = hashlib.sha256()
    for p in _archivos(raiz):
        try:
            datos = p.read_bytes()
        except OSError:
            continue
        h.update(p.relative_to(raiz).as_posix().encode() + b"\0" + str(len(datos)).encode() + b"\0")
        h.update(datos)
    return h.hexdigest()


def build_de(raiz: Path, version: str = __version__) -> str:
    return f"{version}+{hash_contenido(raiz)[:7]}"


class Vigilante:
    """Build id and fingerprint taken once (at startup), and the cached stale check of the same directory."""

    def __init__(self, raiz: Path = PAQUETE, version: str = __version__, reloj: Callable[[], float] = time.monotonic,
                 ttl: float = TTL):
        self.raiz, self.reloj, self.ttl = raiz, reloj, ttl
        self.build = build_de(raiz, version)
        self.inicial = huella(raiz)
        self._cache: tuple[float, bool] | None = None

    def obsoleto(self) -> bool:
        ahora = self.reloj()
        if self._cache is not None and ahora - self._cache[0] < self.ttl:
            return self._cache[1]
        actual = huella(self.raiz)
        resultado = actual is None or actual != self.inicial
        self._cache = (ahora, resultado)
        return resultado


_VIGILANTE: Vigilante | None = None


def iniciar(raiz: Path = PAQUETE) -> Vigilante:
    """Takes the startup snapshot (`ratifact serve` calls it before serving; otherwise the first use does)."""
    global _VIGILANTE
    _VIGILANTE = Vigilante(raiz)
    return _VIGILANTE


def _vigilante() -> Vigilante:
    return _VIGILANTE or iniciar()


def build_id() -> str:
    """`<package version>+<7 hex>` of the code this process loaded."""
    return _vigilante().build


def obsoleto() -> bool:
    """True if the package files this process loaded changed (or disappeared) since it started."""
    return _vigilante().obsoleto()


def aviso_obsoleto() -> str:
    return (f"⚠ This ratifact server (ratifact {build_id()}) is older than the current installation: its package "
            "changed on disk after it started. Restart this client (close and reopen it) so it loads the installed "
            "version.")


MARCA_ERROR_OBSOLETO = "ERROR: stale ratifact server"


def error_in_progress() -> str:
    return (f"{MARCA_ERROR_OBSOLETO} — this process (ratifact {build_id()}) started before the current installation, "
            "so the guidance it would hand out may be out of date. Nothing was changed: the task keeps its status. "
            "Restart this client (close and reopen it) and repeat update_task(..., \"in_progress\").")


def marca_tiempo() -> str:
    """ISO 8601 with time zone, to the minute (the `at=` of `routing:`)."""
    from ratifact import registros
    return registros._ahora().astimezone().isoformat(timespec="minutes")


# ───────────────────────── D1: local source vs. installation ─────────────────────────

def _recibo(paquete: Path) -> Path | None:
    """uv-receipt.toml of the tool environment that holds `paquete` (<tool>/lib/pythonX.Y/site-packages/ratifact)."""
    for padre in list(paquete.parents)[:5]:
        if (padre / RECIBO).is_file():
            return padre / RECIBO
    return None


def fuente_local(paquete: Path = PAQUETE, recibo: Path | None = None) -> Path | None:
    """The local folder uv installed ratifact from, read from the tool receipt (`directory = "..."` or a file://
    path). None when it cannot be told (no receipt, unreadable, no TOML parser) or the source is not local (PyPI,
    remote git)."""
    from ratifact.clientes_toml import _parser
    recibo = recibo or _recibo(paquete)
    parser = _parser()
    if recibo is None or parser is None:
        return None
    try:
        datos = parser.loads(recibo.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    requisitos = (datos.get("tool") or {}).get("requirements") or []
    for r in requisitos if isinstance(requisitos, list) else []:
        if not isinstance(r, dict) or r.get("name") != "ratifact":
            continue
        ruta = r.get("directory") or r.get("path") or ""
        if not ruta and str(r.get("url", "")).startswith("file://"):
            ruta = str(r["url"])[len("file://"):]
        return Path(ruta).expanduser() if ruta else None
    return None


def comando_reinstalar(fuente: Path) -> str:
    return f"uv tool install --reinstall {fuente}"


_CACHE_D1: dict = {}


def fuente_desfasada(paquete: Path = PAQUETE, fuente: Path | None = None) -> bool | None:
    """D1: True if the package folder in the local source differs from the installed one (content, same filter as
    the build); False if equal; None if the source folder does not exist. Hashes are cached per fingerprint pair, so
    repeated calls only stat."""
    origen = (fuente / "ratifact") if fuente else None
    if origen is None or not origen.is_dir():
        return None
    clave = (str(origen), huella(origen), str(paquete), huella(paquete))
    if clave not in _CACHE_D1:
        _CACHE_D1.clear()
        _CACHE_D1[clave] = hash_contenido(origen) != hash_contenido(paquete)
    return _CACHE_D1[clave]


def aviso_fuente(paquete: Path | None = None) -> str:
    """get_context's D1 warning: only for a local installation whose source exists and differs."""
    paquete = paquete or PAQUETE
    try:
        fuente = fuente_local(paquete)
        if fuente is None or not fuente_desfasada(paquete, fuente):
            return ""
    except Exception:
        return ""
    return (f"⚠ The ratifact source ({fuente}) is newer than the installation: reinstall with "
            f"`{comando_reinstalar(fuente)}` and restart the clients.")


# ───────────────────────── running processes (for doctor) ─────────────────────────

@dataclass
class ProcesoVivo:
    pid: int
    inicio: _dt.datetime
    padre: str
    anterior: bool = field(default=False)      # started before the latest modification of the installation


_PS = ["ps", "-axo", "pid=,ppid=,lstart=,command="]
_LINEA_PS = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\w{3}\s+\w{3}\s+\d+\s+[\d:]{8}\s+\d{4})\s+(.*)$")


def _correr_ps() -> str:
    r = subprocess.run(_PS, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"}, timeout=10)
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or f"ps exited with {r.returncode}")
    return r.stdout


def _es_serve(comando: str) -> bool:
    partes = comando.split()
    nombres = [Path(p).name for p in partes]
    return "serve" in partes and any(n in ("ratifact", "ratifact.cli") for n in nombres)


def modificacion_instalacion(paquete: Path = PAQUETE) -> _dt.datetime | None:
    """Latest mtime among the installed package files (same filter as the build)."""
    marcas = [mtime for _, _, mtime in (huella(paquete) or ())]
    return _dt.datetime.fromtimestamp(max(marcas) / 1e9) if marcas else None


def procesos_vivos(paquete: Path = PAQUETE, correr: Callable[[], str] = _correr_ps) -> list[ProcesoVivo]:
    """Running `ratifact serve` processes with start time and parent process name, marking the ones that started
    before the latest modification of the installation. Read only. Raises OSError if they cannot be listed."""
    filas = {}
    for linea in correr().splitlines():
        m = _LINEA_PS.match(linea)
        if m:
            filas[int(m.group(1))] = (int(m.group(2)), m.group(3), m.group(4))
    instalada = modificacion_instalacion(paquete)
    salida = []
    for pid, (ppid, lstart, comando) in sorted(filas.items()):
        if pid == os.getpid() or not _es_serve(comando):
            continue
        try:
            inicio = _dt.datetime.strptime(" ".join(lstart.split()), "%a %b %d %H:%M:%S %Y")
        except ValueError:
            continue
        padre = Path(filas[ppid][2].split()[0]).name if ppid in filas and filas[ppid][2].split() else "?"
        anterior = bool(instalada and inicio < instalada.replace(microsecond=0))
        salida.append(ProcesoVivo(pid, inicio, padre, anterior))
    return salida
