"""Política de delegación de ratifact (ADR-036): la decide ratifact al planificar, no el agente que ejecuta.

`delegation` = required | suggested | off. Global en settings.json (por defecto required), excepción por proyecto en
su entrada de projects.json (update_project) y excepción por tarea en su frontmatter (`delegation: required | off`,
create_task/amend_task). Precedencia: tarea > proyecto > global.

Aquí viven también el bloque "Delegation" de update_task(..., "in_progress"), el rastro `routing:` del frontmatter y
el parser único de la línea `Workers:` del resultado (lo usan la validación blanda de in_review y `ratifact report`)."""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from ratifact import modelos
from ratifact.config import ErrorMemoria

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


def routing(entrada: dict, tarea: dict | None = None) -> str:
    """Valor del campo `routing:` del frontmatter (ADR-036 §6): modelos efectivos y política de esta ejecución, más el
    build del servidor y la hora de la transición (ADR-037 §3)."""
    efectivos, _ = modelos.efectivos(entrada)
    politica, _, _ = efectiva(entrada, tarea)
    roles = ",".join(f"{r}={efectivos[r][0] if r in efectivos else 'session'}" for r in modelos.ROLES)
    from ratifact import build
    return f"{roles} · delegation={politica} · build={build.build_id()} · at={build.marca_tiempo()}"


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
    m = re.search(r"at=(\S+)", texto or "")
    try:
        return _dt.datetime.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


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


# ───────────────────────── línea Workers ─────────────────────────

ROL_MODELO = re.compile(r"^(explore|write|verify)/([^\s,×]+)×(\d+)$")
ESCALADO = re.compile(r"^escalated:\s*(explore|write|verify)$")
NINGUNO = re.compile(r"^none\s*[—–-]+\s*reason:\s*(\S.*)$")
LINEA = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Workers:(?:\*\*)?\s*(.*)$")


@dataclass
class Trabajadores:
    """Una línea `Workers:` válida: (rol, modelo, cantidad) de cada trabajador, roles escalados y, si no hubo
    trabajadores, el motivo."""
    roles: list[tuple[str, str, int]] = field(default_factory=list)
    escalados: list[str] = field(default_factory=list)
    motivo: str = ""

    @property
    def total(self) -> int:
        return sum(n for _, _, n in self.roles)


def parsear_workers(linea: str) -> Trabajadores:
    """Parser único de la línea `Workers:` (ADR-036 §4). Acepta `Workers: explore/haiku×1, write/sonnet×2`,
    `Workers: write/sonnet×1, escalated: write` y `Workers: none — reason: <motivo>`. Lanza ValueError con el
    motivo si está mal formada (incluido `none` sin motivo)."""
    m = LINEA.match(linea or "")
    if not m:
        raise ValueError("it does not start with `Workers:`")
    texto = m.group(1).strip()
    if not texto:
        raise ValueError("`Workers:` is empty")
    if texto.lower().startswith("none"):
        ninguno = NINGUNO.match(texto)
        if not ninguno:
            raise ValueError("`Workers: none` needs a reason: `Workers: none — reason: <why>`")
        return Trabajadores(motivo=ninguno.group(1).strip())
    salida = Trabajadores()
    for item in (x.strip() for x in texto.split(",")):
        rol_modelo, escalado = ROL_MODELO.match(item), ESCALADO.match(item)
        if rol_modelo and int(rol_modelo.group(3)) > 0:
            salida.roles.append((rol_modelo.group(1), rol_modelo.group(2), int(rol_modelo.group(3))))
        elif escalado:
            salida.escalados.append(escalado.group(1))
        else:
            raise ValueError(f"malformed item {item!r} (expected <role>/<model>×<n> with role explore, write or "
                             "verify, or `escalated: <role>`)")
    if not salida.roles:
        raise ValueError("no worker listed (use `Workers: none — reason: <why>` if none ran)")
    return salida


def workers_del_resultado(resultado: str) -> tuple[Trabajadores | None, str]:
    """La última línea `Workers:` de un texto de resultado: (trabajadores, "") si es válida; (None, qué falta) si no
    está o está mal formada."""
    lineas = [l for l in (resultado or "").splitlines() if LINEA.match(l)]
    if not lineas:
        return None, "the result has no `Workers:` line"
    try:
        return parsear_workers(lineas[-1]), ""
    except ValueError as e:
        return None, f"the `Workers:` line is invalid: {e}"


def aviso_in_review(politica: str, resultado: str) -> str:
    """Validación blanda de update_task(..., "in_review") (ADR-036 §5): aviso si la política era required y falta una
    línea Workers válida. Nunca rechaza la transición."""
    if politica != "required":
        return ""
    trabajadores, falta = workers_del_resultado(resultado)
    if trabajadores is not None:
        return ""
    return (f"⚠ Delegation was required for this task, but {falta}. The status was changed anyway; add to the "
            "result a line `Workers: <role>/<model>×<n>, …` (plus `escalated: write` if it applies) or "
            "`Workers: none — reason: <why>`, separate from `Integrations used:`.")
