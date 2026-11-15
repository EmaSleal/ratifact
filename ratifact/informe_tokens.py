"""Token usage section of `ratifact report` (opt-in: `"token_usage": "on"` in settings.json). Reads only metadata of the
Claude Code transcripts (`$CLAUDE_CONFIG_DIR/projects`, else `~/.claude/projects`): never message content. Computed
on demand, nothing is stored. Attribution (ADR-048, which corrects ADR-047 §4): the session of each in_progress →
in_review window is the project session (some line with `cwd` in the project path) with activity within 120 s of the
transition instants of the memory's git history; several sessions: the one with the task's `gitBranch` inside the
window, else the window is ambiguous and the task is shown as such, out of the summaries. Messages of the anchored
sessions and their subagent files inside the window count; a message goes to one task only (line's branch, else the
latest started window). Summaries show average and median; summed windows over 8 h get a warning. The format is not
a public contract of Claude Code: the reader is tolerant and never makes `report` fail."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import statistics
from pathlib import Path

from ratifact.config import _valor
from ratifact.informe_memoria import _memoria, _transiciones, ruta_config
from ratifact.informe_tokens_atribucion import VENTANA_LARGA, Tarea, atribuir
from ratifact.informe_tokens_lectura import CAMPOS, cargar_sesiones, directorio_base  # noqa: F401  (re-exports)
from ratifact.plurales import contar
from ratifact.registros import _normalizar_id

ROTULOS = ("in", "out", "cache write", "cache read")
NOTA = ("Note: figures come from the local Claude Code transcripts, which are deleted after their retention "
        "period; the breakdown is per model, not per role.")


def _ventanas(transiciones: list[tuple[dt.datetime, str]], ahora: dt.datetime):
    """One window per in_progress: up to the first later in_review; else up to the next state change; else now.
    The third item tells whether the end is an in_review commit (only then it anchors a session)."""
    ventanas = []
    for i, (inicio, estado) in enumerate(transiciones):
        if estado != "in_progress":
            continue
        resto = transiciones[i + 1:]
        revision = next((t for t, e in resto if e == "in_review"), None)
        ventanas.append((inicio, revision or (resto[0][0] if resto else ahora), revision is not None))
    return ventanas


def _desglose(t: Tarea, trabajador: bool) -> str:
    partes = [f"{modelo}: " + " · ".join(f"{r} {v:,}" for r, v in zip(ROTULOS, c))
              for (w, modelo), c in sorted(t.uso.items()) if w == trabajador]
    return "; ".join(partes) or "none"


def _total(t: Tarea, trabajador: bool, i: int) -> int:
    return sum(c[i] for (w, _), c in t.uso.items() if w == trabajador)


def _medias(con: list[Tarea], f) -> str:
    return "; ".join(f"{lado}: " + " · ".join(f"{r} {f([_total(t, w, i) for t in con]):,.0f}"
                                               for r, i in (("out", 1), ("cache read", 3)))
                     for lado, w in (("main session", False), ("workers", True)))


def _resumen(grupo: list[Tarea], nombre: str) -> list[str]:
    con = [t for t in grupo if t.uso]
    if not con:
        return [f"    {nombre}: —"]
    return [f"    {nombre}: {len(con)} of {contar(len(grupo), 'task')} with data · average per task — "
            + _medias(con, lambda v: sum(v) / len(v)), f"      median per task — " + _medias(con, statistics.median)]


def _aviso(t: Tarea) -> str:
    if t.duracion() <= VENTANA_LARGA:
        return ""
    horas = f"{t.duracion().total_seconds() / 3600:.1f}".removesuffix(".0")
    return f" ⚠ long window ({horas} h): may include other work of the same session"


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
        raices = list({os.path.normpath(raiz.resolve()), os.path.normpath(os.path.abspath(raiz))})   # project root, also with `repo`
        trabajadores = ultimo_workers_valido(cuerpo.split("\n## Result", 1)[-1])
        t = Tarea(id_, str(meta.get("branch") or ""), raices, _ventanas(transiciones.get(id_, []), ahora),
                  politica_de_routing(meta.get("routing", "")) or "unknown",
                  None if trabajadores is None else bool(trabajadores.total))
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
            if t.ambigua:
                lineas.append(f"    {t.id} · delegation={t.politica}: ambiguous "
                              f"({contar(t.ambigua, 'session')} active at the transition)")
                continue
            if not t.uso:
                lineas.append(f"    {t.id} · delegation={t.politica}: no data")
                continue
            lineas += [f"    {t.id} · delegation={t.politica}{_aviso(t)}", f"      main session: {_desglose(t, False)}",
                       f"      workers: {contar(len(t.agentes), 'worker')} — {_desglose(t, True)}"]
        sin_ambiguas = [t for t in con if not t.ambigua]
        lineas += _resumen([t for t in sin_ambiguas if t.delegada is True], "delegated")
        lineas += _resumen([t for t in sin_ambiguas if t.delegada is False], "not delegated")
    return (lineas or ["  no tasks in the period"]) + [NOTA]
