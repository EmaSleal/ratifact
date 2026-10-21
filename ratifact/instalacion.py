"""Inventario de la instalación para `ratifact doctor` y `ratifact upgrade` (solo lee): projects.json en uso y la
grafía de sus claves, y por proyecto el código, la memoria (ruta, ubicación por defecto vieja/nueva o propia, esquema,
estado git) y las integraciones detectadas; además, los servidores en marcha y los bloqueos tomados (ADR-029)."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ratifact import rutas
from ratifact import config as _cfg
from ratifact.config import (CLAVES_CONFIG, _base, _es_repo, _mem_por_defecto, _ruta_config,
                             _valor)
from ratifact.esquema import _inicializada, _version_esquema
from ratifact.integraciones.registro import INTEGRACIONES, _detectada

VIEJA, NUEVA, PROPIA = "old default (.memorias/)", "new default (.ratifact/)", "custom path"


@dataclass
class Proyecto:
    nombre: str
    entrada: dict
    codigo: Path | None      # None: projects.json no tiene la ruta del código
    mem: Path
    ubicacion: str
    version: int | None = None      # None: la memoria no existe o no está inicializada
    error: str = ""                 # esquema ilegible o fuera de rango
    git: str = "missing"
    limpio: bool = False
    integraciones: list[str] = field(default_factory=list)

    @property
    def existe(self) -> bool:
        return self.mem.is_dir()


@dataclass
class Instalacion:
    config: Path
    datos: dict
    base: Path
    proyectos: list[Proyecto]

    @property
    def claves(self) -> str:
        """Grafía de las claves de projects.json: Spanish, English, mixed o none."""
        usadas = {k for p in self.datos.values() if isinstance(p, dict) for k in p}
        es, en = bool(usadas & set(CLAVES_CONFIG)), bool(usadas & set(CLAVES_CONFIG.values()))
        return "mixed" if es and en else "Spanish" if es else "English" if en else "none"


def _git(mem: Path, *args: str) -> subprocess.CompletedProcess:
    # --no-optional-locks: `git status` no refresca el índice (doctor no escribe nada, ni siquiera en .git/)
    return subprocess.run(["git", "--no-optional-locks", "-C", str(mem), *args], capture_output=True, text=True)


def estado_git(mem: Path) -> tuple[str, bool]:
    """(descripción, limpio): clean, uncommitted changes (…), not a git repository, no commits o missing. `.lock` no
    cuenta (lo ignora el .gitignore de la memoria)."""
    if not mem.is_dir():
        return "missing", False
    if not _es_repo(mem):
        return "not a git repository", False
    if _git(mem, "rev-parse", "-q", "--verify", "HEAD").returncode != 0:
        return "no commits", False
    r = _git(mem, "status", "--porcelain", "--untracked-files=all")
    sucios = [l[3:] for l in r.stdout.splitlines() if l[3:].strip('"') != ".lock"]
    if r.returncode != 0 or sucios:
        return f"uncommitted changes ({', '.join(sucios[:5]) or r.stderr.strip()[:120]})", False
    return "clean", True


def _ubicacion(mem: Path, base: Path, nombre: str) -> str:
    if mem == base / ".memorias" / nombre:
        return VIEJA
    return NUEVA if mem == base / ".ratifact" / nombre else PROPIA


def _integraciones(entrada: dict, codigo: Path) -> list[str]:
    """Las de alcance proyecto detectadas en disco (ADR-025); las apagadas en projects.json se muestran como off."""
    apagadas = _valor(entrada, "integraciones") or {}
    salida = []
    for i in INTEGRACIONES:
        if isinstance(apagadas, dict) and apagadas.get(i.nombre) == "off":
            salida.append(f"{i.nombre} (off)")
        elif i.alcance != "user" and _detectada(i, codigo):
            salida.append(f"{i.nombre} (detected)")
    return salida


def _proyecto(nombre: str, entrada: dict, base: Path) -> Proyecto:
    memoria = _valor(entrada, "memoria")
    mem = Path(memoria).expanduser().resolve() if memoria else _mem_por_defecto(nombre, base)
    ruta = _valor(entrada, "ruta")
    codigo = Path(ruta).expanduser().resolve() if ruta else None
    p = Proyecto(nombre, entrada, codigo, mem, _ubicacion(mem, base, nombre))
    p.git, p.limpio = estado_git(mem)
    if p.existe and _inicializada(mem):
        try:
            p.version = _version_esquema(mem)
        except _cfg.ErrorMemoria as e:
            p.error = str(e)
    p.integraciones = _integraciones(entrada, codigo) if codigo else []
    return p


def inventario(config: Path | None = None, base: Path | None = None) -> Instalacion:
    """Lee projects.json (el que usaría el servidor ahora) sin escribir nada."""
    config = config or _ruta_config()
    base = base or _base()
    if not config.is_file():
        raise _cfg.ErrorMemoria(f"Configuration file {config} does not exist.")
    try:
        datos = json.loads(config.read_text(encoding="utf-8"))
    except ValueError as e:
        raise _cfg.ErrorMemoria(f"{config} is not valid JSON ({e}).") from e
    proyectos = [_proyecto(n, e, base) for n, e in datos.items() if isinstance(e, dict)]
    return Instalacion(config, datos, base, proyectos)


# ───────────────────────── servidores en marcha y bloqueos ─────────────────────────

@dataclass
class Proceso:
    pid: int
    comando: str
    config: Path | None      # projects.json que usa; None si no se pudo leer su entorno
    por_variable: bool = False      # lo eligió RATIFACT_CONFIG / MEMORIA_PROYECTOS_CONFIG (no la ruta por defecto)


def _es_servidor(args: list[str]) -> bool:
    """`ratifact serve`, `uvx ratifact serve`, `python …/servidor.py`, `uv run --script …/servidor.py`, `python -m
    ratifact.cli serve`. Un editor o un visor con servidor.py abierto no cuenta."""
    nombres = [Path(a).name for a in args if a]
    if not nombres:
        return False
    if nombres[0] == "ratifact":
        return nombres[1:2] == ["serve"]
    if not (nombres[0].startswith("python") or nombres[0] in ("uv", "uvx")):
        return False
    return "servidor.py" in nombres or (bool({"ratifact", "ratifact.cli"} & set(nombres)) and "serve" in nombres)


def _config_de(entorno: dict[str, str], cwd: Path | None) -> Path | None:
    """projects.json que resolvería un servidor con ese entorno (misma regla que config._ruta_config). Una variable con
    ruta relativa se resuelve contra el cwd del proceso; si no se pudo leer (`cwd` None), la config es desconocida."""
    home = Path(entorno.get("HOME") or Path.home())
    nueva = home / ".config" / "ratifact" / "projects.json"
    explicita = entorno.get("RATIFACT_CONFIG") or entorno.get("MEMORIA_PROYECTOS_CONFIG")
    if explicita:
        ruta = home / explicita[2:] if explicita == "~" or explicita.startswith("~/") else Path(explicita)
        if not ruta.is_absolute():
            if cwd is None:
                return None
            ruta = cwd / ruta
        return nueva if not ruta.exists() and rutas.respaldo(ruta).exists() and nueva.exists() else ruta
    return nueva if nueva.exists() else home / ".config" / "memoria-proyectos" / "projects.json"


def procesos_servidor(proc: Path = Path("/proc")) -> list[Proceso]:
    """Servidores ratifact en marcha (Linux: /proc; en otro sistema, `ps` sin entorno → config desconocida). `proc` se
    cambia en las pruebas por un /proc simulado."""
    salida = []
    if not proc.is_dir():
        r = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True)
        for linea in r.stdout.splitlines():
            pid, _, comando = linea.strip().partition(" ")
            if pid.isdigit() and int(pid) != os.getpid() and _es_servidor(comando.split()):
                salida.append(Proceso(int(pid), comando, None))
        return salida
    for d in proc.iterdir():
        if not d.name.isdigit() or int(d.name) == os.getpid():
            continue
        try:
            args = [a.decode(errors="replace") for a in (d / "cmdline").read_bytes().split(b"\0") if a]
        except OSError:
            continue
        if not _es_servidor(args):
            continue
        try:
            cwd = Path(os.readlink(d / "cwd"))
        except OSError:
            cwd = None
        try:
            pares = (l.decode(errors="replace").partition("=") for l in (d / "environ").read_bytes().split(b"\0"))
            entorno = {k: v for k, _, v in pares if k}
            config = _config_de(entorno, cwd)
        except OSError:
            entorno, config = {}, None
        variable = bool(entorno.get("RATIFACT_CONFIG") or entorno.get("MEMORIA_PROYECTOS_CONFIG"))
        salida.append(Proceso(int(d.name), " ".join(args), config, variable))
    return sorted(salida, key=lambda p: p.pid)


def separar_procesos(procesos: list[Proceso], config: Path) -> tuple[list[Proceso], list[Proceso]]:
    """(los que usan `config` o no se sabe cuál usan, los que usan otra configuración). Solo los primeros bloquean el
    upgrade: un servidor de otra configuración no ve estas memorias ni este projects.json."""
    propios, otros = [], []
    for p in procesos:
        (otros if p.config is not None and p.config.resolve() != config.resolve() else propios).append(p)
    return propios, otros


def bloqueo_tomado(mem: Path) -> bool:
    """¿Alguien tiene el .lock de la memoria? Se prueba sin espera y sin crear el archivo (solo lectura)."""
    lock = mem / ".lock"
    if not lock.is_file():
        return False
    with open(lock) as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
    return False


# ───────────────────────── configuración por defecto ausente (T-013) ─────────────────────────

def sugerencias_config(procesos: list[Proceso], origen: Path | None) -> list[Path]:
    """Sin variable CONFIG y sin projects.json por defecto (nuevo ni viejo): los projects.json que usan los servidores
    en marcha (RATIFACT_CONFIG / MEMORIA_PROYECTOS_CONFIG) y el que está junto al repositorio de origen."""
    if os.environ.get("RATIFACT_CONFIG") or os.environ.get("MEMORIA_PROYECTOS_CONFIG"):
        return []
    if rutas.config_nueva().exists() or rutas.config_vieja().exists():
        return []
    candidatas = [p.config for p in procesos if p.por_variable and p.config is not None and p.config.is_file()]
    if origen is not None and (origen / "projects.json").is_file():
        candidatas.append(origen / "projects.json")
    salida: list[Path] = []
    for c in candidatas:
        if c.resolve() not in {s.resolve() for s in salida}:
            salida.append(c)
    return salida


def mensaje_sugerencia(candidatas: list[Path]) -> str:
    """El comando exacto para cada configuración encontrada (vacío si no hay ninguna)."""
    if not candidatas:
        return ""
    comandos = "; ".join(f"`RATIFACT_CONFIG={c} ratifact upgrade`" for c in candidatas)
    return (f"the default configuration {rutas.config_nueva()} does not exist, but a projects.json is in use "
            f"(running servers or next to the source install): review the plan with {comandos}")
