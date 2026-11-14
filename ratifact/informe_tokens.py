"""Token usage section of `ratifact report` (opt-in: `"token_usage": "on"` in settings.json). Reads only metadata of the
Claude Code transcripts (`$CLAUDE_CONFIG_DIR/projects`, else `~/.claude/projects`): never message content. Computed
on demand, nothing is stored. Attribution to a task: a session qualifies when one of its lines has a `cwd` inside the
task's code folder and another has the task's `gitBranch`; its messages (and those of its subagent files) count for
the task when their `timestamp` falls in an in_progress → in_review window from the memory's git history. A message
goes to one task only: the one whose branch matches the line's `gitBranch`, else the latest started window. The format
is not a public contract of Claude Code: the reader is tolerant and never makes `report` fail."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ratifact.config import _valor
from ratifact.informe_memoria import _memoria, _transiciones, ruta_config
from ratifact.plurales import contar
from ratifact.registros import _normalizar_id

CAMPOS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
ROTULOS = ("in", "out", "cache write", "cache read")
NOTA = ("Note: figures come from the local Claude Code transcripts, which are deleted after their retention "
        "period; the breakdown is per model, not per role.")


@dataclass
class Mensaje:
    ts: dt.datetime
    rama: str | None
    modelo: str
    trabajador: bool
    agente: str | None
    cifras: list[int]


@dataclass
class Sesion:
    cwds: set = field(default_factory=set)
    ramas: set = field(default_factory=set)
    mensajes: dict = field(default_factory=dict)


@dataclass
class Tarea:
    id: str
    rama: str
    raices: list[str]
    ventanas: list[tuple[dt.datetime, dt.datetime]]
    politica: str
    delegada: bool
    uso: dict = field(default_factory=dict)         # (worker?, model) -> [in, out, cache write, cache read]
    agentes: set = field(default_factory=set)


def directorio_base() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base).expanduser() if base else Path.home() / ".claude") / "projects"


def _instante(texto) -> dt.datetime | None:
    if not isinstance(texto, str):
        return None
    texto = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), texto)
    texto = texto[:-1] + "+00:00" if texto.endswith("Z") else texto      # fromisoformat takes "Z" only from 3.11
    try:
        t = dt.datetime.fromisoformat(texto)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _texto(valor) -> str | None:
    return valor if isinstance(valor, str) and valor else None


def _linea(d: dict, clave_defecto, es_sub: bool, ruta: Path, s: Sesion) -> None:
    if _texto(d.get("cwd")):
        s.cwds.add(d["cwd"])
    if _texto(d.get("gitBranch")):
        s.ramas.add(d["gitBranch"])
    msg = d.get("message")
    uso = msg.get("usage") if isinstance(msg, dict) else None
    if not isinstance(uso, dict):
        return
    cifras = [uso[c] if type(uso.get(c)) is int and uso[c] >= 0 else 0 for c in CAMPOS]
    ts = _instante(d.get("timestamp"))
    modelo = _texto(msg.get("model")) or "unknown"
    if not any(type(uso.get(c)) is int for c in CAMPOS) or ts is None or modelo == "<synthetic>":
        return
    mid, rid = _texto(msg.get("id")), _texto(d.get("requestId"))
    clave = (mid, rid) if mid or rid else clave_defecto
    previo = s.mensajes.get(clave)
    if previo:                                   # repeated message: the maximum of each field
        previo.cifras = [max(a, b) for a, b in zip(previo.cifras, cifras)]
        return
    trabajador = es_sub or d.get("isSidechain") is True
    agente = str(ruta) if es_sub else _texto(d.get("agentId"))
    s.mensajes[clave] = Mensaje(ts, _texto(d.get("gitBranch")), modelo, trabajador, agente if trabajador else None,
                                cifras)


def cargar_sesiones(base: Path, desde: dt.datetime) -> list[Sesion]:
    """One Sesion per session (its file plus its `subagents/agent-*.jsonl`); files not modified since `desde` are
    skipped; each file is read line by line."""
    sesiones: dict[Path, Sesion] = {}
    for ruta in sorted(base.glob("**/*.jsonl")):
        try:
            if ruta.stat().st_mtime < desde.timestamp():
                continue
        except OSError:
            continue
        es_sub = ruta.parent.name == "subagents" and ruta.name.startswith("agent-")
        s = sesiones.setdefault(ruta.parent.parent if es_sub else ruta.with_suffix(""), Sesion())
        try:
            with ruta.open(encoding="utf-8", errors="replace") as f:
                for n, linea in enumerate(f):
                    try:
                        d = json.loads(linea)
                    except (ValueError, RecursionError):
                        continue
                    if isinstance(d, dict):
                        _linea(d, (str(ruta), n), es_sub, ruta, s)
        except OSError:
            continue
    return list(sesiones.values())


def _ventanas(transiciones: list[tuple[dt.datetime, str]], ahora: dt.datetime):
    """One window per in_progress: up to the first later in_review; else up to the next state change; else now."""
    ventanas = []
    for i, (inicio, estado) in enumerate(transiciones):
        if estado != "in_progress":
            continue
        resto = transiciones[i + 1:]
        fin = next((t for t, e in resto if e == "in_review"), resto[0][0] if resto else ahora)
        ventanas.append((inicio, fin))
    return ventanas


def _dentro(cwds, raices: list[str]) -> bool:
    for cwd in cwds:
        p = os.path.normpath(cwd)
        if any(p == r or p.startswith(r.rstrip(os.sep) + os.sep) for r in raices):
            return True
    return False


def atribuir(sesiones: list[Sesion], tareas: list[Tarea]) -> None:
    for s in sesiones:
        candidatas = [t for t in tareas if t.rama in s.ramas and _dentro(s.cwds, t.raices)]
        for m in s.mensajes.values():
            opciones = [(ini, t) for t in candidatas for ini, fin in t.ventanas if ini <= m.ts <= fin]
            if not opciones:
                continue
            propias = [o for o in opciones if o[1].rama == m.rama] or opciones
            t = max(propias, key=lambda o: o[0])[1]
            acumulado = t.uso.setdefault((m.trabajador, m.modelo), [0, 0, 0, 0])
            for i, v in enumerate(m.cifras):
                acumulado[i] += v
            if m.trabajador:
                t.agentes.add(m.agente)


def _desglose(t: Tarea, trabajador: bool) -> str:
    partes = [f"{modelo}: " + " · ".join(f"{r} {v:,}" for r, v in zip(ROTULOS, c))
              for (w, modelo), c in sorted(t.uso.items()) if w == trabajador]
    return "; ".join(partes) or "none"


def _total(t: Tarea, trabajador: bool, i: int) -> int:
    return sum(c[i] for (w, _), c in t.uso.items() if w == trabajador)


def _promedio(grupo: list[Tarea], nombre: str) -> str:
    con = [t for t in grupo if t.uso]
    if not con:
        return f"    {nombre}: —"
    medias = [f"{lado}: " + " · ".join(f"{r} {sum(_total(t, w, i) for t in con) / len(con):,.0f}"
                                        for r, i in (("out", 1), ("cache read", 3)))
              for lado, w in (("main session", False), ("workers", True))]
    return f"    {nombre}: {len(con)} of {contar(len(grupo), 'task')} with data · average per task — " + "; ".join(medias)


def _tareas_proyecto(nombre: str, p: dict, desde: dt.datetime, ahora: dt.datetime) -> tuple[list[Tarea], list[Tarea]]:
    """(tasks of the period, those of them with `routing:`), with their windows."""
    from ratifact.delegacion import politica_de_routing, ultimo_workers_valido
    from ratifact.informe_delegacion import _tareas_del_periodo
    ruta = _valor(p, "ruta")
    if not ruta:
        return [], []
    raiz = Path(ruta).expanduser()
    mem = _memoria(nombre, p)
    periodo = _tareas_del_periodo(mem, desde)
    transiciones = _transiciones(mem) if periodo else {}
    todas, con = [], []
    for meta, cuerpo, archivo in periodo:
        crudo = meta.get("id") or (re.match(r"T-\d+", archivo.name) or [None])[0]
        if not crudo:
            continue
        id_ = _normalizar_id(crudo)
        carpeta = raiz / meta["repo"] if meta.get("repo") else raiz
        raices = list({os.path.normpath(carpeta.resolve()), os.path.normpath(os.path.abspath(carpeta))})
        trabajadores = ultimo_workers_valido(cuerpo.split("\n## Result", 1)[-1])
        t = Tarea(id_, str(meta.get("branch") or ""), raices, _ventanas(transiciones.get(id_, []), ahora),
                  politica_de_routing(meta.get("routing", "")) or "unknown", bool(trabajadores and trabajadores.total))
        todas.append(t)
        if meta.get("routing"):
            con.append(t)
    return todas, con


def seccion(desde: dt.datetime, proyecto: str | None) -> list[str]:
    """Lines of the section (without its title). `desde` is naive local time, as in the rest of the report."""
    base = directorio_base()
    if not base.is_dir():
        return [f"  no transcripts found ({base})", NOTA]
    try:
        proyectos = json.loads(ruta_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["  no configuration", NOTA]
    desde = desde.astimezone()
    ahora = dt.datetime.now(dt.timezone.utc)
    sesiones = None
    lineas = []
    for nombre, p in proyectos.items():
        if proyecto and nombre != proyecto or not isinstance(p, dict):
            continue
        todas, con = _tareas_proyecto(nombre, p, desde, ahora)
        if not con:
            continue
        if sesiones is None:
            sesiones = cargar_sesiones(base, desde)
        atribuir(sesiones, todas)
        lineas.append(f"  {nombre}:")
        for t in con:
            if not t.uso:
                lineas.append(f"    {t.id} · delegation={t.politica}: no data")
                continue
            lineas += [f"    {t.id} · delegation={t.politica}", f"      main session: {_desglose(t, False)}",
                       f"      workers: {contar(len(t.agentes), 'worker')} — {_desglose(t, True)}"]
        lineas += [_promedio([t for t in con if t.delegada], "delegated"),
                   _promedio([t for t in con if not t.delegada], "not delegated")]
    return (lineas or ["  no tasks in the period"]) + [NOTA]
