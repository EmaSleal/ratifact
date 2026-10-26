"""Running `ratifact serve` processes, for `ratifact doctor` (ADR-037 §5, ADR-038).

Each server records its startup content in $XDG_STATE_HOME/ratifact/servers/<pid>.json (`registrar`, called by
`ratifact serve`); doctor lists the processes with `ps` and reads those records, so a process that started before the
latest modification of the installation is flagged only when its content differs (a reinstall rewrites identical
files). doctor only reads: nothing is signalled or stopped."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ratifact.build import PAQUETE, Vigilante, hash_contenido, huella

TOLERANCIA_INICIO = 5     # seconds between the recorded start and ps's start time (rules out a reused PID)


def carpeta_registro() -> Path:
    from ratifact import rutas
    return rutas.estado() / "servers"


def _vivo(pid: int) -> bool:
    """Whether a recorded PID still exists, without signalling it: /proc on Linux, signal 0 on other POSIX systems
    (it delivers nothing). Elsewhere (Windows, where os.kill terminates the process) nothing is probed and the record
    is kept."""
    if Path("/proc/self").is_dir():
        return Path(f"/proc/{pid}").exists()
    if os.name != "posix":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:              # exists but belongs to someone else
        return True
    return True


def registrar(vigilante: Vigilante, carpeta: Path | None = None, pid: int | None = None) -> Path | None:
    """Writes this server's record and removes the records of processes that no longer exist. Never raises: a
    failure only means doctor will not know this process's content."""
    carpeta = carpeta or carpeta_registro()
    pid = pid or os.getpid()
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in carpeta.glob("*.json"):
            if viejo.stem.isdigit() and int(viejo.stem) != pid and not _vivo(int(viejo.stem)):
                viejo.unlink(missing_ok=True)
        ruta = carpeta / f"{pid}.json"
        datos = {"pid": pid, "build": vigilante.build, "content": vigilante.contenido,
                 "started": _dt.datetime.now().isoformat(timespec="seconds"), "package": str(vigilante.raiz)}
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos), encoding="utf-8")
        os.replace(temporal, ruta)
        return ruta
    except OSError:
        return None


def desregistrar(ruta: Path | None) -> None:
    try:
        if ruta:
            ruta.unlink(missing_ok=True)
    except OSError:
        pass


def leer_registro(pid: int, inicio: _dt.datetime, carpeta: Path | None = None) -> dict | None:
    """The record of `pid` if its start matches `inicio` (ps); None if missing, unreadable or of a reused PID."""
    ruta = (carpeta or carpeta_registro()) / f"{pid}.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        registrado = _dt.datetime.fromisoformat(datos["started"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if abs((registrado - inicio).total_seconds()) > TOLERANCIA_INICIO or not datos.get("content"):
        return None
    return datos


ANTERIOR, MISMO, DESCONOCIDO, POSTERIOR = "stale", "same", "unknown", "after"


@dataclass
class ProcesoVivo:
    pid: int
    inicio: _dt.datetime
    padre: str
    anterior: bool = field(default=False)      # started before the latest modification AND runs different content
    estado: str = POSTERIOR                    # after | stale | same (same content) | unknown (no record)
    build: str = ""                            # from its record, when known


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


def procesos_vivos(paquete: Path = PAQUETE, correr: Callable[[], str] = _correr_ps,
                   registros: Path | None = None) -> list[ProcesoVivo]:
    """Running `ratifact serve` processes with start time and parent process name. One that started before the latest
    modification of the installation is `stale` only if its record (ADR-038) shows different content from the
    installed one, `same` if the content is identical, and `unknown` without a record. Read only. Raises OSError if
    they cannot be listed."""
    actual = ""
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
        proceso = ProcesoVivo(pid, inicio, padre)
        if instalada and inicio < instalada.replace(microsecond=0):
            registro = leer_registro(pid, inicio, registros)
            if registro is None:
                proceso.estado = DESCONOCIDO
            else:
                actual = actual or hash_contenido(paquete)
                proceso.build = registro.get("build", "")
                proceso.anterior = registro["content"] != actual
                proceso.estado = ANTERIOR if proceso.anterior else MISMO
        salida.append(proceso)
    return salida
