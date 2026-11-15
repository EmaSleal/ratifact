"""Attribution of transcript messages to tasks (ADR-048). A session is a candidate when one of its lines has a `cwd`
equal to the project path or inside it. The session of a run is the candidate with some line within TOLERANCIA of the
window start (memory in_progress commit) or end (in_review commit; a window closed by another state only anchors at
its start). Several anchored sessions: those with a line inside the window on the task branch; none and more than one
is an ambiguous window. Messages inside the window of the anchored sessions (and their subagents) count; a message
goes to one task only: the one whose branch matches the line's `gitBranch`, else the latest started window."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field

from ratifact.informe_tokens_lectura import Sesion, hay_linea

TOLERANCIA = dt.timedelta(seconds=120)          # distance from a transition within which a line anchors a session
VENTANA_LARGA = dt.timedelta(hours=8)           # summed windows above this get a warning


@dataclass
class Tarea:
    id: str
    rama: str
    raices: list[str]
    ventanas: list[tuple[dt.datetime, dt.datetime, bool]]     # (start, end, whether the end is an in_review commit)
    politica: str
    delegada: bool | None                           # None: no valid `Workers:` line (excluded from the summaries)
    uso: dict = field(default_factory=dict)         # (worker?, model) -> [in, out, cache write, cache read]
    agentes: set = field(default_factory=set)
    ambigua: int = 0                                # >0: sessions active at the transition of an ambiguous window

    def duracion(self) -> dt.timedelta:
        return sum((fin - ini for ini, fin, _ in self.ventanas), dt.timedelta())


def _dentro(cwds, raices: list[str]) -> bool:
    for cwd in cwds:
        p = os.path.normpath(cwd)
        if any(p == r or p.startswith(r.rstrip(os.sep) + os.sep) for r in raices):
            return True
    return False


def _ancla(s: Sesion, ini: dt.datetime, fin: dt.datetime, con_fin: bool) -> bool:
    return hay_linea(s.instantes, ini - TOLERANCIA, ini + TOLERANCIA) or \
        (con_fin and hay_linea(s.instantes, fin - TOLERANCIA, fin + TOLERANCIA))


def _elegidas(sesiones: list[Sesion], t: Tarea, ventana) -> tuple[list[Sesion], int]:
    """(sessions that own the window, number of anchored sessions if the window is ambiguous else 0)."""
    ini, fin, con_fin = ventana
    ancladas = [s for s in sesiones if _dentro(s.cwds, t.raices) and _ancla(s, ini, fin, con_fin)]
    if len(ancladas) > 1:
        con_rama = [s for s in ancladas if hay_linea(s.por_rama.get(t.rama, []), ini, fin)]
        if con_rama:
            return con_rama, 0
        return [], len(ancladas)
    return ancladas, 0


def atribuir(sesiones: list[Sesion], tareas: list[Tarea]) -> None:
    propias: dict[int, list] = {id(s): [] for s in sesiones}       # session -> [(start, end, task)]
    for t in tareas:
        elegidas = []
        for v in t.ventanas:
            sel, ambigua = _elegidas(sesiones, t, v)
            t.ambigua = max(t.ambigua, ambigua)
            elegidas += [(s, v[0], v[1], t) for s in sel]
        if not t.ambigua:                                           # an ambiguous task claims no message
            for s, ini, fin, t in elegidas:
                propias[id(s)].append((ini, fin, t))
    for s in sesiones:
        for m in s.mensajes.values():
            opciones = [(ini, t) for ini, fin, t in propias[id(s)] if ini <= m.ts <= fin]
            if not opciones:
                continue
            mias = [o for o in opciones if o[1].rama == m.rama] or opciones
            t = max(mias, key=lambda o: o[0])[1]
            acumulado = t.uso.setdefault((m.trabajador, m.modelo), [0, 0, 0, 0])
            for i, v in enumerate(m.cifras):
                acumulado[i] += v
            if m.trabajador:
                t.agentes.add(m.agente)
