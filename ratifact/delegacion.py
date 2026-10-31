"""Política de delegación de ratifact (ADR-036): la decide ratifact al planificar, no el agente que ejecuta.

`delegation` = required | suggested | off. Global en settings.json (por defecto required), excepción por proyecto en
su entrada de projects.json (update_project) y excepción por tarea en su frontmatter (`delegation: required | off`,
create_task/amend_task). Precedencia: tarea > proyecto > global.

Aquí viven también el bloque "Delegation" de update_task(..., "in_progress"), el rastro `routing:` del frontmatter y
el parser único de la línea `Workers:` del resultado (lo usan la validación blanda de in_review y `ratifact report`)."""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from ratifact import modelos
from ratifact.config import ErrorMemoria
from ratifact.workers import (LINEA, Trabajadores, aviso_in_review, parsear_workers, proponer_workers,  # noqa: F401
                              ultimo_workers_valido, workers_del_resultado)

CLAVE = "delegation"
POLITICAS = ("required", "suggested", "off")
POLITICAS_TAREA = ("required", "off")
DEFECTO = "required"
HEREDAR = "inherit"


# ───────────────────────── política efectiva ─────────────────────────

def resolver(tarea: str = "", proyecto: str = "", global_: str = "") -> tuple[str, str]:
    """(política, origen) por precedencia tarea > proyecto > global > required por defecto. Los valores vacíos o
    inválidos no cuentan (se valida antes, con aviso)."""
    for valor, origen, validos in ((tarea, "task", POLITICAS_TAREA), (proyecto, "project", POLITICAS),
                                   (global_, "global", POLITICAS)):
        if valor in validos:
            return valor, origen
    return DEFECTO, "global"


def _valor(fuente: dict, donde: str, validos: tuple, avisos: list[str]) -> str:
    valor = fuente.get(CLAVE, "")
    if valor in ("", None):
        return ""
    if valor not in validos:
        avisos.append(f"{donde}: invalid `delegation` value {valor!r} (valid: {', '.join(validos)}); ignored.")
        return ""
    return valor


def efectiva(entrada: dict, tarea: dict | None = None, config: Path | None = None) -> tuple[str, str, list[str]]:
    """(política, origen, avisos) para la entrada de un proyecto en projects.json y el frontmatter de una tarea.
    Un settings.json ilegible deja el global en el valor por defecto (el bloque Model routing ya lo avisa); un valor
    inválido se ignora con un aviso. Nunca lanza."""
    avisos: list[str] = []
    try:
        settings = modelos.leer_settings(config)
    except ErrorMemoria:
        settings = {}
    global_ = _valor(settings, "settings.json", POLITICAS, avisos)
    proyecto = _valor(entrada, "projects.json (project entry)", POLITICAS, avisos)
    propia = _valor(tarea or {}, "task frontmatter", POLITICAS_TAREA, avisos)
    politica, origen = resolver(propia, proyecto, global_)
    return politica, origen, avisos


def _modelo(rol: str, efectivos: dict) -> str:
    return efectivos[rol][0] if rol in efectivos else "session model"


def bloque(entrada: dict, tarea: dict | None = None) -> str:
    """Bloque "Delegation" de update_task(..., "in_progress"): imperativo con required, condicional con suggested,
    ninguno con off (solo los avisos de valores inválidos, si hay)."""
    politica, origen, avisos = efectiva(entrada, tarea)
    efectivos, _ = modelos.efectivos(entrada)
    m = {r: _modelo(r, efectivos) for r in modelos.ROLES}
    lineas: list[str] = []
    if politica == "required":
        lineas = [f"Delegation (required, set by {origen} policy; this is an instruction, not a suggestion):",
                  "- You, the main session, orchestrate: you do not write the code yourself.",
                  f"- Exploration runs in an explore worker (model: {m['explore']}).",
                  f"- Implementation runs in write workers (model: {m['write']}).",
                  f"- Verification runs in a verify worker that did not see the implementation (model: {m['verify']}).",
                  "- Every brief carries the full task spec (criteria, amendments, out of scope), not a summary.",
                  "- Before update_task(in_review) you review the complete diff yourself.",
                  "- If a writer fails verification twice, you take over the implementation and declare it as "
                  "`escalated: write`.",
                  "- In the result, report `Workers: <role>/<model>×<n>, …` (plus `escalated: write` if it applies)."]
    elif politica == "suggested":
        lineas = [f"Delegation (suggested, set by {origen} policy): you may delegate exploration to an explore worker "
                  f"({m['explore']}), implementation to write workers ({m['write']}) and verification to a verify "
                  f"worker that did not see the implementation ({m['verify']}). Report `Workers: <role>/<model>×<n>, "
                  "…`, or `Workers: none — reason: <why>` if you did not delegate."]
    lineas += [f"⚠ {a}" for a in avisos]
    return "\n".join(lineas)


def routing(entrada: dict, tarea: dict | None = None, cliente: str = "unknown") -> str:
    """Valor del campo `routing:` del frontmatter (ADR-036 §6): modelos efectivos y política de esta ejecución, más el
    build del servidor y la hora de la transición (ADR-037 §3) y el cliente MCP (ADR-041 §4, siempre al final)."""
    efectivos, _ = modelos.efectivos(entrada)
    politica, _, _ = efectiva(entrada, tarea)
    roles = ",".join(f"{r}={efectivos[r][0] if r in efectivos else 'session'}" for r in modelos.ROLES)
    from ratifact import build
    return f"{roles} · delegation={politica} · build={build.build_id()} · at={build.marca_tiempo()} · client={cliente}"


def politica_de_routing(texto: str) -> str | None:
    """"explore=haiku,… · delegation=required" → "required" (None si el campo no la trae)."""
    m = re.search(r"delegation=(\w+)", texto or "")
    return m.group(1) if m else None


def build_de_routing(texto: str) -> str | None:
    """`build=1.0.0+abc1234` del campo routing (ADR-037 §3); None en el formato anterior."""
    m = re.search(r"build=(\S+)", texto or "")
    return m.group(1) if m else None


def at_de_routing(texto: str) -> _dt.datetime | None:
    """`at=2026-10-25T18:40-06:00` del campo routing (ADR-037 §3); None si falta o no es una fecha válida."""
    m = re.search(r"(?:^|\s)at=(\S+)", texto or "")
    try:
        return _dt.datetime.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


def cliente_de_routing(texto: str) -> str:
    """`client=claude-code/2.1.0` del campo routing (ADR-041 §4); "unknown" si falta (formato anterior)."""
    m = re.search(r"(?:^|\s)client=(\S+)", texto or "")
    return m.group(1) if m else "unknown"


def cliente_actual() -> str:
    """`<nombre>/<versión>` del clientInfo de la inicialización MCP de la sesión que llama (ADR-041 §4), saneado para
    no romper el routing (sin espacios, `·`, `=`, `,` ni caracteres de control; máximo 64). "unknown" si no hay dato
    o se llama fuera de una petición. Nunca lanza."""
    try:
        from mcp.server.lowlevel.server import request_ctx
        info = request_ctx.get().session.client_params.clientInfo
        if not info.name:
            return "unknown"
        crudo = f"{info.name}/{info.version or 'unknown'}"
    except Exception:       # LookupError fuera de una petición, client_params None, sin clientInfo…
        return "unknown"
    limpio = re.sub(r"[\s·=,\x00-\x1f\x7f]+", "-", crudo).strip("-")[:64]
    return limpio or "unknown"


# ───────────────────────── parámetros de herramientas ─────────────────────────

def validar_tarea(valor: str) -> str:
    """`delegation` de create_task/amend_task: "", "required" u "off"."""
    valor = (valor or "").strip().lower()
    if valor and valor not in POLITICAS_TAREA:
        raise ErrorMemoria(f"Invalid `delegation` {valor!r} for a task: use {' or '.join(POLITICAS_TAREA)} "
                           "(empty = inherit from the project/global policy).")
    return valor


def validar_proyecto(valor: str) -> str:
    """`delegation` de update_project: required | suggested | off | inherit (quita la excepción)."""
    valor = (valor or "").strip().lower()
    validos = (*POLITICAS, HEREDAR)
    if valor not in validos:
        raise ErrorMemoria(f"Invalid `delegation` {valor!r}: use {', '.join(validos)}.")
    return valor


def aplicar_proyecto(entrada: dict, politica: str) -> str:
    """Guarda (o quita, con inherit) la excepción del proyecto en su entrada de projects.json; devuelve el cambio."""
    if politica == HEREDAR:
        entrada.pop(CLAVE, None)
    else:
        entrada[CLAVE] = politica
    return f"delegation: {politica}"
