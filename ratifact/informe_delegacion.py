"""Delegation indicator of `ratifact report`: policy compliance per project from the tasks whose `routing:` changed in
the period (by the routing's `at=` when present, else by `updated`; tasks from before the policy, without `routing:`,
are counted apart), delegated vs. not delegated in reviews and in_progress → in_review time, rework, a breakdown per
client and per build (ordered by each build's oldest `at=`; hashes have no order of their own) and how many delegated
tasks skipped explore. Rework is only measured where a verifier ran: never for the not delegated group, and not for
tasks whose routing has no `client=` (recorded before rework was)."""
from __future__ import annotations

import datetime as dt
import json
import re

from ratifact.informe_memoria import (_carpeta, _duracion, _memoria, _porcentaje, _promedio, _registro, _transiciones,
                                      ruta_config)
from ratifact.plurales import contar
from ratifact.registros import _normalizar_id

SIN_BUILD = "no build"


def _instante(at: dt.datetime) -> dt.datetime:
    return at if at.tzinfo else at.replace(tzinfo=dt.timezone.utc)      # comparable with the others


def _tareas_del_periodo(mem, desde: dt.datetime) -> list[tuple[dict, str, object]]:
    from ratifact.delegacion import at_de_routing
    tareas = []
    for archivo in sorted(_carpeta(mem, "tasks").glob("T-*.md")):
        meta, cuerpo = _registro(archivo, "tarea")
        at = at_de_routing(meta.get("routing", ""))      # the time of the execution, if it was recorded
        fecha = at.date().isoformat() if at else meta.get("updated") or meta.get("date", "")
        try:
            if dt.date.fromisoformat(str(fecha)[:10]) < desde.date():
                continue
        except ValueError:
            continue
        tareas.append((meta, cuerpo, archivo))
    return tareas


def _lineas_por_build(builds: dict[str, dict]) -> list[str]:
    """One line per `build=` value (and "no build"), oldest `at=` first; "no build" and builds without `at=` last."""
    def orden(item):
        nombre, b = item
        return (nombre == SIN_BUILD, b["at"] is None, b["at"] or dt.datetime.max.replace(tzinfo=dt.timezone.utc), nombre)
    return [f"    per build {nombre}: {contar(b['tareas'], 'task')} · {b['delegadas']} delegated · rework "
            f"{_porcentaje(b['rework'], b['con_cliente'])}" for nombre, b in sorted(builds.items(), key=orden)]


def _proyecto(nombre: str, mem, desde: dt.datetime) -> list[str]:
    from ratifact.delegacion import at_de_routing, build_de_routing, cliente_de_routing, politica_de_routing
    from ratifact.delegacion import ultimo_workers_valido
    tareas = _tareas_del_periodo(mem, desde)
    if not tareas:
        return []
    con = [(m, c, a) for m, c, a in tareas if m.get("routing")]
    transiciones = _transiciones(mem) if con else {}
    requeridas = cumplen = escaladas = 0
    grupos = {"delegated": ([], []), "not delegated": ([], [])}
    delegadas = con_rework = sin_explore = 0
    reenvios: dict[str, int] = {}
    clientes: dict[str, dict] = {}       # tasks, required, compliant, delegated, with rework
    builds: dict[str, dict] = {}         # tasks, delegated, with_client (delegated with `client=`), rework, earliest at
    for meta, cuerpo, archivo in con:
        routing = meta["routing"]
        resultado = cuerpo.split("\n## Result", 1)[-1]
        trabajadores = valida = ultimo_workers_valido(resultado)      # one read per task
        delegada = bool(trabajadores and trabajadores.total)
        requerida = politica_de_routing(routing) == "required"
        cumplen += requerida and delegada
        requeridas += requerida
        escaladas += bool(trabajadores and trabajadores.escalados)
        cliente = clientes.setdefault(cliente_de_routing(routing),
                                      dict(tareas=0, requeridas=0, cumplen=0, delegadas=0, rework=0))
        at = at_de_routing(routing)
        build = builds.setdefault(build_de_routing(routing) or SIN_BUILD,
                                  dict(tareas=0, delegadas=0, con_cliente=0, rework=0, at=None))
        if at and (build["at"] is None or _instante(at) < build["at"]):
            build["at"] = _instante(at)
        cliente["tareas"] += 1
        build["tareas"] += 1
        if requerida:
            cliente["requeridas"] += 1
            cliente["cumplen"] += delegada
        if delegada:
            delegadas += 1
            cliente["delegadas"] += 1
            build["delegadas"] += 1
            sin_explore += "explore" in valida.omitidos
            if re.search(r"(?:^|\s)client=", routing):       # without it the rework was not recorded yet
                build["con_cliente"] += 1
                build["rework"] += bool(valida.reenvios)
            if valida.reenvios:
                con_rework += 1
                cliente["rework"] += 1
            for rol, n in valida.reenvios.items():
                reenvios[rol] = reenvios.get(rol, 0) + n
        revisiones, horas = grupos["delegated" if delegada else "not delegated"]
        revisiones.append(len(re.findall(r"^### (?:Review|Revisión) \d+ · ", cuerpo, re.M)))
        duracion = _duracion(transiciones.get(_normalizar_id(meta.get("id") or re.match(r"T-\d+", archivo.name).group(0)), []))
        if duracion is not None:
            horas.append(duracion.total_seconds() / 3600)
    lineas = [f"  {nombre}: {contar(len(con), 'task')} with routing · required {requeridas} · with workers "
              f"{cumplen} · compliance {_porcentaje(cumplen, requeridas)} · escalations {escaladas} · without routing "
              f"(before the policy): {len(tareas) - len(con)}"]
    for grupo, (revisiones, horas) in grupos.items():
        lineas.append(f"    {grupo}: {contar(len(revisiones), 'task')} · reviews (changes_requested) average "
                      f"{_promedio(revisiones)} · in_progress → in_review average {_promedio(horas)} h")
        if grupo == "not delegated":
            lineas.append("    not delegated: rework not measured (no verifier)")
    total = ", ".join(f"{r}×{n}" for r, n in reenvios.items()) or "0"
    lineas.append(f"    rework: with rework {con_rework} of {delegadas} delegated · rate "
                  f"{_porcentaje(con_rework, delegadas)} · resends {total} · escalations {escaladas}")
    lineas.append(f"    explore skipped {sin_explore} of {delegadas} delegated")
    lineas += _lineas_por_build(builds)
    for nombre_cliente, c in sorted(clientes.items()):
        lineas.append(f"    per client {nombre_cliente}: {contar(c['tareas'], 'task')} · compliance "
                      f"{_porcentaje(c['cumplen'], c['requeridas'])} · rework "
                      f"{_porcentaje(c['rework'], c['delegadas'])}")
    return lineas


def indicador_delegacion(desde: dt.datetime, proyecto: str | None) -> list[str]:
    config = ruta_config()
    try:
        proyectos = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"- no configuration ({config})"]
    lineas = []
    for nombre, p in proyectos.items():
        if proyecto and nombre != proyecto or not isinstance(p, dict):
            continue
        lineas += _proyecto(nombre, _memoria(nombre, p), desde)
    return lineas or ["- no tasks in the period"]
