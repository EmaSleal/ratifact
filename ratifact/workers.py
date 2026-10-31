"""Línea `Workers:` del resultado (ADR-036 §4, ampliada por ADR-041): parser único, propuesta de corrección,
reemplazo de la línea en el último bloque de resultado y aviso blando de in_review. Lo usan update_task y
`ratifact report`."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

ROL_MODELO = re.compile(r"^(explore|write|verify)/([^\s,×]+)×(\d+)$")
ESCALADO = re.compile(r"^escalated:\s*(explore|write|verify)$")
NINGUNO = re.compile(r"^none\s*[—–-]+\s*reason:\s*(\S.*)$")
LINEA = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Workers:(?:\*\*)?\s*(.*)$")
REENVIO = re.compile(r"^rework:\s*(explore|write|verify)×(\d+)$")
REENVIO_SEGUIDO = re.compile(r"^(explore|write|verify)×(\d+)$")
# ADR-042: el guion ASCII (`-`, `--`) separa la nota solo si lo sigue `note:`; ` — ` y ` – ` siempre.
NOTA = re.compile(r"\s(?:[—–]\s|--?\s(?=note:))", re.I)


@dataclass
class Trabajadores:
    """Una línea `Workers:` válida: (rol, modelo, cantidad) de cada trabajador, reenvíos por rol (`rework:`), roles
    escalados, la nota libre (`— note:`) y, si no hubo trabajadores, el motivo."""
    roles: list[tuple[str, str, int]] = field(default_factory=list)
    escalados: list[str] = field(default_factory=list)
    motivo: str = ""
    reenvios: dict[str, int] = field(default_factory=dict)
    nota: str = ""

    @property
    def total(self) -> int:
        return sum(n for _, _, n in self.roles)


def parsear_workers(linea: str) -> Trabajadores:
    """Parser único de la línea `Workers:` (ADR-036 §4, ampliado por ADR-041 §1). Acepta
    `Workers: explore/haiku×1, write/sonnet×2, rework: write×1, escalated: write — note: <texto>` (rework, escalated
    y nota opcionales, en ese orden) y `Workers: none — reason: <motivo>`. Separador de la nota (ADR-042): el canónico
    es ` — note:` (` — reason:` para `none`); también se aceptan ` - note:` / ` -- note:` (y `none - reason:`) en ASCII;
    un guion ASCII en cualquier otro lugar no separa nada (la raya ` — ` / ` – ` sí, ver NOTA). La nota, una vez separada, no se valida.
    Lanza ValueError con el motivo si está mal formada (incluido `none` sin motivo)."""
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
    partes = NOTA.split(texto, maxsplit=1)
    cabeza = partes[0]
    if len(partes) > 1:
        salida.nota = re.sub(r"^note:\s*", "", partes[1].strip(), flags=re.I)
    if "(" in cabeza or ")" in cabeza:
        raise ValueError("parentheses are not part of the format (rework goes in `rework: <role>×<n>`, comments in "
                         "`— note: <text>`)")
    en_lista = False   # el último item fue `rework:` o una continuación `<rol>×<n>`
    for item in (x.strip() for x in cabeza.split(",")):
        rol_modelo, reenvio, seguido, escalado = (ROL_MODELO.match(item), REENVIO.match(item),
                                                  REENVIO_SEGUIDO.match(item), ESCALADO.match(item))
        if rol_modelo and int(rol_modelo.group(3)) > 0:
            salida.roles.append((rol_modelo.group(1), rol_modelo.group(2), int(rol_modelo.group(3))))
            en_lista = False
        elif reenvio or (seguido and en_lista):
            r = reenvio or seguido
            rol, n = r.group(1), int(r.group(2))
            if n <= 0:
                raise ValueError(f"rework count must be at least 1 in {item!r}")
            salida.reenvios[rol] = salida.reenvios.get(rol, 0) + n
            en_lista = True
        elif escalado:
            salida.escalados.append(escalado.group(1))
            en_lista = False
        else:
            raise ValueError(f"malformed item {item!r} (expected <role>/<model>×<n> with role explore, write or "
                             "verify, `rework: <role>×<n>[, <role>×<n>]` or `escalated: <role>`)")
    for rol in salida.reenvios:
        if rol not in {x for x, _, _ in salida.roles}:
            raise ValueError(f"`rework: {rol}` but no {rol} worker is listed")
    if not salida.roles:
        raise ValueError("no worker listed (use `Workers: none — reason: <why>` if none ran)")
    return salida


RETRABAJO = re.compile(r"resum|correction|fix|retry|re-run", re.I)
PARENTESIS = re.compile(r"((?:explore|write|verify)/[^\s,×()]+×\d+)\s*\(([^()]*)\)")


def proponer_workers(linea: str) -> str | None:
    """Línea corregida propuesta (ADR-041 §3) para una línea `Workers:` con paréntesis tras `<rol>/<modelo>×<n>`: si
    el paréntesis habla de retrabajo (resum, correction, fix, retry, re-run) suma `rework: <rol>×1`; el texto va a
    la nota. None si no se puede derivar una línea que el parser acepte."""
    m = LINEA.match(linea or "")
    if not m:
        return None
    partes = NOTA.split(m.group(1).strip(), maxsplit=1)
    notas = [re.sub(r"^note:\s*", "", partes[1].strip(), flags=re.I)] if len(partes) > 1 and partes[1].strip() else []
    reenvios: list[str] = []

    def quitar(c: re.Match) -> str:
        texto = c.group(2).strip()
        rol = c.group(1).split("/")[0]
        if RETRABAJO.search(texto) and rol not in reenvios:
            reenvios.append(rol)
        if texto:
            notas.append(texto)
        return c.group(1)

    cabeza = PARENTESIS.sub(quitar, partes[0])
    items = [x.strip() for x in cabeza.split(",")]
    escalados = [x for x in items if x.startswith("escalated:")]
    items = [x for x in items if not x.startswith("escalated:")]
    propuesta = "Workers: " + ", ".join(
        items + ([f"rework: {', '.join(f'{r}×1' for r in reenvios)}"] if reenvios else []) + escalados)
    if notas:
        propuesta += " — note: " + "; ".join(notas)
    try:
        parsear_workers(propuesta)
    except ValueError:
        return None
    return propuesta


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


def ultimo_workers_valido(resultado: str) -> Trabajadores | None:
    """La última línea `Workers:` VÁLIDA de un texto (ADR-041 §5, para `ratifact report`); None si ninguna lo es."""
    for l in reversed((resultado or "").splitlines()):
        if LINEA.match(l):
            try:
                return parsear_workers(l)
            except ValueError:
                continue
    return None


def aviso_in_review(politica: str, resultado: str) -> str:
    """Validación blanda de update_task(..., "in_review") (ADR-036 §5): aviso si la política era required y falta una
    línea Workers válida. Nunca rechaza la transición."""
    if politica != "required":
        return ""
    trabajadores, falta = workers_del_resultado(resultado)
    if trabajadores is not None:
        return ""
    base = f"⚠ Delegation was required for this task, but {falta}. The status was changed anyway; "
    lineas = [l for l in (resultado or "").splitlines() if LINEA.match(l)]
    propuesta = proponer_workers(lineas[-1]) if lineas else None
    if propuesta:
        return (base + "corrected line proposed (copy it as is):\n" + propuesta + "\nSend only that line with "
                'update_task(project, id, "in_review", result=<that line>): it replaces the `Workers:` line of the '
                "latest result block, no new block is created.")
    return (base + "add to the result a line `Workers: <role>/<model>×<n>, …` (plus `rework: <role>×<n>` for resends "
            "after a failed verification and `escalated: write` if it applies; no parentheses, comments go after "
            "` — note: `), for example `Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1, rework: write×1 — "
            "note: resumed once for the verify fix`, or `Workers: none — reason: <why>`, separate from "
            "`Integrations used:`. To fix the line later send only that line with "
            'update_task(project, id, "in_review").')


_ENCABEZADO_RESULTADO = re.compile(r"^### \d{4}-\d{2}-\d{2} · \S+.*$", re.M)
_ENCABEZADO_REVISION = re.compile(r"^### (?:Review|Revisión) \d+ · ", re.M)


def corregir_workers(cuerpo: str, linea: str) -> tuple[str, bool] | None:
    """ADR-041 §2: reemplaza la última línea `Workers:` del último bloque de resultado por `linea` (o la agrega al
    final del bloque si no tenía) y devuelve (cuerpo, reemplazó). None si no hay bloque de resultado o si después de
    él hay una revisión: entonces se aplica el comportamiento normal (bloque nuevo)."""
    bloques = list(_ENCABEZADO_RESULTADO.finditer(cuerpo))
    if not bloques:
        return None
    inicio = bloques[-1].end()
    revision = _ENCABEZADO_REVISION.search(cuerpo, inicio)
    siguiente = re.compile(r"^#{1,3} ", re.M).search(cuerpo, inicio)
    fin = siguiente.start() if siguiente else len(cuerpo)
    if revision:
        return None
    lineas = cuerpo[inicio:fin].split("\n")
    previas = [i for i, l in enumerate(lineas) if LINEA.match(l)]
    if previas:
        lineas[previas[-1]] = linea
        return cuerpo[:inicio] + "\n".join(lineas) + cuerpo[fin:], True
    resto = cuerpo[inicio:fin]
    return cuerpo[:inicio] + resto.rstrip("\n") + "\n" + linea + ("\n\n" if cuerpo[fin:] else "\n") \
        + cuerpo[fin:], False
