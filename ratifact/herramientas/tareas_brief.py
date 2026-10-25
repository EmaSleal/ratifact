"""amend_task (ADR-021) y read_task (ADR-031): ampliar una tarea antes de que corra y leerla como un brief de trabajo.

Estructura de una tarea (esquema v2): frontmatter; spec (Goal, Acceptance criteria, Resolves, Applicable decisions,
Files involved, Out of scope, Notes, Amendments, How to verify); "## Result" al final, con bloques "### <fecha> ·
<estado>" (resultados del agente de código) y "### Review N · <fecha> · changes_requested" (revisiones). El texto de
un resultado puede traer sus propios títulos "##"/"###": solo esos dos formatos abren un bloque."""
from __future__ import annotations

import datetime as _dt
import re

from ratifact import delegacion as _delegacion
from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, herramienta
from ratifact.busqueda import _fin_frontmatter
from ratifact.config import MEM, ErrorMemoria, _mem
from ratifact.esquema import _bloqueo
from ratifact.registros import (MARCA_DUPLICADO, VENTANA_IDEMPOTENCIA_MINUTOS, _buscar_registro, _commit,
                                _escribir_registro, _hoy, _leer_registro)
from ratifact.vocabulario import TAREAS

ESTADOS_AMPLIABLES = ("todo", "changes_requested")
SECCION_ENMIENDAS = "## Amendments"
SECCIONES_RESULTADO = ("## Result", "## Resultado")
ENMIENDA = re.compile(r"^### Amendment (\d+) · (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*$")
RESULTADO = re.compile(r"^### \d{4}-\d{2}-\d{2} · [a-z_]+\s*$")
REVISION = re.compile(r"^### (?:Review|Revisión) \d+ · ")


# ───────────────────────── amend_task ─────────────────────────

def _texto_enmienda(criterios: str, notas: str) -> str:
    partes = []
    if criterios.strip():
        partes += ["**Additional criteria**", criterios.strip()]
    if notas.strip():
        partes += ([""] if partes else []) + ["**Notes**", notas.strip()]
    return "\n".join(partes)


def _enmiendas(lineas: list[str]) -> list[tuple[int, _dt.datetime, str]]:
    """(número, fecha y hora, texto) de cada bloque "### Amendment N" del cuerpo."""
    salida, actual = [], None
    for linea in lineas + ["## (fin)"]:
        m = ENMIENDA.match(linea)
        if actual and (m or linea.startswith("## ") or linea.startswith("### ")):
            salida.append((actual[0], actual[1], "\n".join(actual[2]).strip()))
            actual = None
        if m:
            actual = (int(m.group(1)), _dt.datetime.strptime(m.group(2), "%Y-%m-%d %H:%M"), [])
        elif actual:
            actual[2].append(linea)
    return salida


def _insertar_enmienda(lineas: list[str], bloque: list[str]) -> list[str]:
    """Agrega el bloque al final de "## Amendments" (la crea antes de How to verify / Result si no existe). Solo mira
    la spec: lo que está desde "## Result" es historial."""
    fin_spec = next((i for i, l in enumerate(lineas) if l.strip() in SECCIONES_RESULTADO), len(lineas))
    inicio = next((i for i, l in enumerate(lineas[:fin_spec]) if l.strip() == SECCION_ENMIENDAS), None)
    if inicio is None:
        destino = next((i for i, l in enumerate(lineas[:fin_spec]) if l.strip() == "## How to verify"), fin_spec)
        return lineas[:destino] + [SECCION_ENMIENDAS, "", *bloque, ""] + lineas[destino:]
    fin = next((i for i in range(inicio + 1, fin_spec) if lineas[i].startswith("## ")), fin_spec)
    while fin > inicio + 1 and not lineas[fin - 1].strip():
        fin -= 1
    resto = lineas[fin:]
    return lineas[:fin] + ["", *bloque] + ([""] if resto and resto[0].strip() else []) + resto


@herramienta
def amend_task(project: str, id: str, additional_criteria: str = "", notes: str = "", delegation: str = "") -> str:
    """Extends a task that has not run yet (status todo) or was sent back (changes_requested) with additional
    acceptance criteria and/or notes. Any other status is rejected (after a review, use request_changes).
    Appends a dated "### Amendment N" block (sub-labels "Additional criteria" / "Notes") to the task's "Amendments"
    section; the original criteria stay untouched. One commit per amendment; give at least one of the three fields.
    `delegation`: sets the task's exception to the delegation policy (ADR-036), "required" or "off", in its
    frontmatter (empty = unchanged); it adds no Amendment block by itself.
    Idempotent (ADR-019): an identical amendment recorded in the last minutes is not written again."""
    def f():
        texto = _texto_enmienda(additional_criteria, notes)
        politica = _delegacion.validar_tarea(delegation)
        if not texto and not politica:
            raise ErrorMemoria("Give at least one of `additional_criteria`, `notes` or `delegation`.")
        with _bloqueo(project):
            ruta = _buscar_registro(_mem(project) / TAREAS, id)
            meta, cuerpo = _leer_registro(ruta)
            estado = meta.get("status")
            if estado not in ESTADOS_AMPLIABLES:
                raise ErrorMemoria(f"{meta.get('id')} is '{estado}': amend_task only extends tasks in todo or "
                                   "changes_requested (after a review, use request_changes).")
            if not texto:
                if meta.get(_delegacion.CLAVE) == politica:
                    return f"{meta['id']} already has delegation: {politica}; nothing was written."
                meta[_delegacion.CLAVE], meta["updated"] = politica, _hoy()
                _escribir_registro(ruta, meta, cuerpo)
                sha = _commit(project, [ruta], f"{meta['id']} delegation {politica}")
                return (f"{meta['id']} amended (delegation: {politica}) · commit {sha}\n"
                        f"Run it with: /run-task {meta['id']}")
            if politica:
                meta[_delegacion.CLAVE] = politica
            lineas = cuerpo.strip().splitlines()
            previas = _enmiendas(lineas)
            ahora = _registros._ahora()
            limite = ahora - _dt.timedelta(minutes=VENTANA_IDEMPOTENCIA_MINUTOS)
            if previas and previas[-1][2] == texto and previas[-1][1] >= limite.replace(second=0, microsecond=0):
                return (f"{meta['id']} Amendment {previas[-1][0]} {MARCA_DUPLICADO}: an identical amendment was "
                        f"recorded less than {VENTANA_IDEMPOTENCIA_MINUTOS} minutes ago; nothing new was written.")
            n = max((p[0] for p in previas), default=0) + 1
            bloque = [f"### Amendment {n} · {ahora:%Y-%m-%d %H:%M}", *texto.splitlines()]
            meta["updated"] = _hoy()
            _escribir_registro(ruta, meta, "\n".join(_insertar_enmienda(lineas, bloque)))
            sha = _commit(project, [ruta], f"{meta['id']} amendment {n}")
            return f"{meta['id']} amended (Amendment {n}) · commit {sha}\nRun it with: /run-task {meta['id']}"
    return _ejecutar(f)


# ───────────────────────── read_task ─────────────────────────

def _bloques(lineas: list[str], desde: int) -> list[tuple[str, int, int]]:
    """(tipo, primera línea, última línea) de cada bloque del Result, con números 1-indexados del archivo. Tipo:
    "review", "result" o "amendment"."""
    inicios = []
    for i in range(desde, len(lineas)):
        l = lineas[i]
        tipo = ("review" if REVISION.match(l) else "amendment" if ENMIENDA.match(l)
                else "result" if RESULTADO.match(l) else None)
        if tipo:
            inicios.append((tipo, i))
    fines = [i for _, i in inicios[1:]] + [len(lineas)]
    salida = []
    for (tipo, i), fin in zip(inicios, fines):
        while fin - 1 > i and not lineas[fin - 1].strip():
            fin -= 1
        salida.append((tipo, i + 1, fin))
    return salida


def _relevante(estado: str, bloques: list[tuple[str, int, int]]) -> tuple[str, int, int] | None:
    """changes_requested → la última Review; in_review o failed → el último resultado; in_progress → la última Review
    si es el último bloque (la corrida en curso responde a esa revisión)."""
    def ultimo(tipo):
        return next((b for b in reversed(bloques) if b[0] == tipo), None)
    if estado == "changes_requested":
        return ultimo("review")
    if estado in ("in_review", "failed"):
        return ultimo("result")
    if estado == "in_progress" and bloques and bloques[-1][0] == "review":
        return bloques[-1]
    return None


@herramienta
def read_task(project: str, id: str) -> str:
    """Working brief of a task, instead of reading the whole file: the frontmatter, the full spec (Goal, Acceptance
    criteria, Resolves, Applicable decisions, Files involved, Out of scope, Notes, Amendments, How to verify), every
    Amendment block, the block relevant to the status in full (changes_requested → latest Review; in_review or
    failed → latest Result block; in_progress → the latest Review it answers) and a one-line index (heading · line
    range · size) of every other Result/Review block, readable with read_document and that range."""
    def f():
        ruta = _buscar_registro(_mem(project) / TAREAS, id)
        relativa = f"{MEM}/{ruta.relative_to(_mem(project)).as_posix()}"
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        meta, _ = _leer_registro(ruta)
        cuerpo_desde = _fin_frontmatter(lineas)
        fin_spec = next((i for i in range(cuerpo_desde, len(lineas)) if lineas[i].strip() in SECCIONES_RESULTADO),
                        len(lineas))
        partes = [f"(→ {relativa})\n" + "\n".join(lineas[:fin_spec]).rstrip()]
        bloques = _bloques(lineas, fin_spec + 1)
        elegido = _relevante(meta.get("status", ""), bloques)
        texto = lambda b: "\n".join(lineas[b[1] - 1:b[2]])   # noqa: E731
        for b in bloques:
            if b[0] == "amendment" or b == elegido:
                etiqueta = "Amendment" if b[0] == "amendment" else f"latest {'Review' if b[0] == 'review' else 'Result'}"
                partes.append(f"## Result — {etiqueta} (lines {b[1]}–{b[2]})\n{texto(b)}")
        otros = [b for b in bloques if b[0] != "amendment" and b != elegido]
        if otros:
            indice = [f"- {lineas[b[1] - 1].strip()} · lines {b[1]}–{b[2]} · {len(texto(b)):,} chars" for b in otros]
            partes.append(f"## Other Result/Review blocks ({len(otros)}) — read one with "
                          f'read_document("{project}", "{relativa}", from_line, to_line)\n' + "\n".join(indice))
        elif not bloques:
            partes.append("## Result\n(no result yet)")
        return "\n\n".join(partes)
    return _ejecutar(f)
