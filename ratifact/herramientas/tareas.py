"""Herramientas de tareas para el agente de código: create_task, update_task, request_changes y list_tasks
(amend_task y read_task en tareas_brief)."""
from __future__ import annotations

import re

from ratifact import build as _build
from ratifact import delegacion as _delegacion
from ratifact import modelos as _modelos
from ratifact import workers as _workers
from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, herramienta
from ratifact.catalogo import _registros_en
from ratifact.config import ErrorMemoria, _mem, _proyectos, _repos, _valor
from ratifact.esquema import _bloqueo
from ratifact.integraciones import registro as _integraciones
from ratifact.registros import (_buscar_registro, _commit, _duplicado_reciente, _escribir_registro, _hoy,
                                _ids_resuelve, _leer_registro, _mensaje_duplicado, _normalizar_id, _resumen_tareas,
                                _siguiente_id, _slug, _texto_resuelve)
from ratifact.vocabulario import DECISIONES, ESTADOS, TAREAS, _normalizar_estado


# ───────────────────────── tareas para Claude Code ─────────────────────────

ESTADOS_TAREA = ESTADOS["tarea"]     # todo, in_progress, in_review, changes_requested, failed, merged, discarded
MARCA_RESULTADO = "(filled in by the coding agent when done)"
MARCA_RESULTADO_V1 = "(lo completa Claude Code al terminar)"    # tareas de antes del esquema v2 (el cuerpo no migra)


def _anexar_resultado(cuerpo: str, bloque: str) -> str:
    """Agrega un bloque a la sección Result (reemplaza el marcador inicial, v2 o v1, la primera vez)."""
    for marca in (MARCA_RESULTADO, MARCA_RESULTADO_V1):
        if marca in cuerpo:
            return cuerpo.replace(marca, bloque, 1)
    return cuerpo.rstrip() + "\n\n" + bloque


def _comando_pruebas(proyecto: str, repositorio: str = "") -> str:
    """Comando de pruebas de un repo; sin `repositorio` en proyectos multi-repo, la lista completa."""
    cfg = _valor(_proyectos().get(proyecto, {}), "pruebas", "")
    if isinstance(cfg, dict):
        if repositorio:
            return cfg.get(repositorio, "")
        return "; ".join(f"{repo}/: {cmd}" for repo, cmd in cfg.items())
    return cfg


def _pendientes_abiertos(proyecto: str) -> dict[str, str]:
    """Id → tema de cada pendiente abierto, desde el catálogo (ADR-022)."""
    return {r.id: r.titulo for r in _registros_en(proyecto, "P") if r.estado == "open"}


def _validar_decisiones(proyecto: str, decisiones: str) -> str:
    """`decisions` de create_task (P-012): ids separados por comas, normalizados ("adr-3" → "ADR-003"); si alguno no
    existe, ErrorMemoria que los nombra (y no se escribe nada)."""
    ids = list(dict.fromkeys(_normalizar_id(i) for i in decisiones.split(",") if i.strip()))
    faltan = []
    for i in ids:
        try:
            _buscar_registro(_mem(proyecto) / DECISIONES, i)
        except ErrorMemoria:
            faltan.append(i)
    if faltan:
        verbo = "does" if len(faltan) == 1 else "do"
        raise ErrorMemoria(f"Invalid `decisions`: {', '.join(faltan)} ({verbo} not exist); nothing was created.")
    return ", ".join(ids)


def _validar_resuelve(proyecto: str, resuelve: str) -> list[tuple[str, bool]]:
    """`resuelve` de registrar_tarea (ADR-027): cada id debe existir y estar abierto; si no, ErrorMemoria con todos los
    inválidos (y no se escribe nada)."""
    ids = _ids_resuelve(resuelve)
    abiertos = _pendientes_abiertos(proyecto)
    existentes = {r.id for r in _registros_en(proyecto, "P")}
    malos = [f"{i} ({'not open' if i in existentes else 'does not exist'})" for i, _ in ids if i not in abiertos]
    if malos:
        raise ErrorMemoria(f"Invalid `resolves`: {', '.join(malos)}. Only open pending items (P-NNN, optionally "
                           "\"(partial)\").")
    return ids


@herramienta
def create_task(project: str, title: str, goal: str, acceptance_criteria: str, decisions: str = "",
                files: str = "", out_of_scope: str = "", notes: str = "", repo: str = "", resolves: str = "",
                delegation: str = "") -> str:
    """Creates a work specification for the coding agent in .project/tasks/T-NNN.md (status 'todo').
    In multi-repo projects, `repo` (required) is the folder where the work happens; in single-repo projects it is
    ignored (the response says so).
    It must be self-contained: the coding agent runs it without this chat. `acceptance_criteria`: a verifiable list
    (tests that must pass, observable behavior). `decisions`: applicable ADR ids. `files`: paths likely to be
    touched. The user runs it with /run-task T-NNN.
    `resolves`: pending items the task resolves, comma-separated, each optionally with "(partial)" (e.g.
    "P-036, P-037 (partial)"); they must exist and be open. Stored in the task ("Resolves" section); when the task is
    merged, update_task reminds which ones are still open. It never closes pending items.
    `delegation`: the task's exception to the delegation policy, decided while planning (ADR-036): "required" or
    "off" (empty = inherit from the project/global policy). Use "off" when the task touches security, is
    cross-cutting, or depends on diagnosing a cause the spec does not know yet. Stored in the task's frontmatter.
    The response adds the line of detected integrations (not written into the task).
    Idempotent (ADR-019): if a task with this title (ignoring case and spaces) was created in the last minutes AND is
    STILL 'todo', nothing new is created and the existing id is returned (with the /run-task command to repeat to
    the user). If that task already changed status (e.g. in_progress: it is running), a human or the coding agent
    already intervened, so a new task is recorded."""
    proyecto, titulo, objetivo, criterios_aceptacion = project, title, goal, acceptance_criteria
    decisiones, archivos, fuera_de_alcance, notas, repositorio, resuelve = (decisions, files, out_of_scope, notes,
                                                                             repo, resolves)

    def f():
        politica = _delegacion.validar_tarea(delegation)
        repos, repo = _repos(proyecto), repositorio
        if repos and repositorio not in repos:
            raise ErrorMemoria(f"Multi-repo project: give `repo` ({', '.join(repos)}).")
        nota = ""
        if not repos and repositorio:     # no es un error: el valor no cambia nada, solo se avisa que se ignoró
            repo, nota = "", "\n(single-repo project: `repo` was ignored)"
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / TAREAS
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "T", "title", titulo, "todo")
            if dup:
                return _mensaje_duplicado(dup["id"], f"Run it with: /run-task {dup['id']}") + nota
            ids = _validar_resuelve(proyecto, resuelve) if resuelve.strip() else []
            decisiones_norm = _validar_decisiones(proyecto, decisiones) if decisiones.strip() else ""
            id_ = _siguiente_id(carpeta, "T")
            ruta = carpeta / f"{id_}-{_slug(titulo)}.md"
            meta = {"id": id_, "title": titulo, "status": "todo", "date": _hoy(),
                    "created": _registros._ahora().isoformat(timespec="seconds"),
                    "branch": f"{id_.lower()}-{_slug(titulo)}"}
            if repo:
                meta["repo"] = repo
            if ids:
                meta["resolves"] = _texto_resuelve(ids)
            if politica:
                meta[_delegacion.CLAVE] = politica
            secciones = [f"# {id_} — {titulo}", "## Goal", objetivo,
                         "## Acceptance criteria", criterios_aceptacion]
            if ids:
                temas = _pendientes_abiertos(proyecto)
                secciones += ["## Resolves", "\n".join(f"- {i}{' (partial)' if parcial else ''} · {temas[i]}"
                                                        for i, parcial in ids)]
            for nombre, valor in (("Applicable decisions", decisiones_norm), ("Files involved", archivos),
                                  ("Out of scope", fuera_de_alcance), ("Notes", notas)):
                if valor:
                    secciones += [f"## {nombre}", valor]
            cmd = _comando_pruebas(proyecto, repo)
            donde = f"From `{repo}/`" if repo else "From the repository root"
            secciones += ["## How to verify",
                          f"{donde}: `{cmd}`" if cmd else
                          "(no test command configured: ask the user or use update_project)"]
            secciones += ["## Result", MARCA_RESULTADO]
            _escribir_registro(ruta, meta, "\n\n".join(secciones))
            sha = _commit(proyecto, [ruta], f"{id_} {titulo} (todo)")
            linea = _integraciones._linea_integraciones(proyecto)
            return (f"{id_} created · suggested branch {meta['branch']} · commit {sha}\nRun it with: /run-task {id_}"
                    + nota + (f"\n{linea}" if linea else ""))
    return _ejecutar(f)


def _recordatorio_resuelve(proyecto: str, resuelve: str) -> str:
    """Al integrar (ADR-027, P-016): los pendientes declarados en `resolves` que siguen abiertos, con qué hacer en cada
    caso. Uno parcial dice cómo registrar lo que falta: una nota anexada al pendiente, o cerrarlo y abrir otro."""
    abiertos = {r.id: r.ruta for r in _registros_en(proyecto, "P") if r.estado == "open"} if resuelve else {}
    return "\n".join(
        f"{i} (partial) is still open: record what remains — append a note to its file with "
        f'update_document("{proyecto}", "{abiertos[i]}", "<what remains>", mode="append"), or close it with '
        f'close_pending("{proyecto}", "{i}", ...) and add the remainder with add_pending("{proyecto}", ...)'
        if parcial else
        f'{i} is still open: close it with close_pending("{proyecto}", "{i}", ...) if it was resolved'
        for i, parcial in _ids_resuelve(resuelve) if i in abiertos)


@herramienta
def update_task(project: str, id: str, status: str, result: str = "", commit: str = "") -> str:
    """Changes a task's status (todo, in_progress, in_review, failed, merged, discarded; the Spanish names pendiente,
    en_curso, en_revision, fallida, integrada, descartada are still accepted until 1.1). Stored in English.
    `result`: what was done, tests run and their summarized output, deviations from the spec.
    'merged' and 'discarded' only with the user's explicit confirmation.
    To ask for corrections after reviewing a task use `request_changes`, not this status change.
    With 'in_progress', the response brings the guidance of active integrations (execute, verify, close), computed at
    that moment; it is conditional: follow it only if you have those tools. It is not written into the task.
    It also brings a "Model routing" block when the user configured models per role (explore, write, verify), and
    the "Delegation" block of the effective policy (task > project > global, default required; ADR-036): with
    required it is an instruction, with suggested a suggestion, with off there is none. The effective models and
    policy are recorded in the task's frontmatter as `routing:` (overwritten on re-runs), together with the server
    build and the time of the transition (ADR-037).
    If this server process is older than the installation on disk, 'in_progress' is refused without changing
    anything (restart the client and repeat it); every other status works and carries a warning.
    With 'in_review', if the policy was required and `result` has no valid `Workers:` line, the response carries a
    warning with a proposed corrected line when it can derive one (the status changes anyway). If the task is already
    in review and `result` is only a valid `Workers:` line, it replaces that line in the latest result block instead of
    adding a block (ADR-041). The routing also records the MCP client (`client=`).
    With 'merged', if the task declares `resolves`, the response reminds which pending items are still open (it
    never closes or modifies any)."""
    proyecto, estado, resultado = project, status, result

    def f():
        nuevo = _normalizar_estado("tarea", estado)
        if nuevo == "changes_requested":
            raise ErrorMemoria("To send a task back use `request_changes` (it records the review in a fixed format).")
        if nuevo == "in_progress" and _build.obsoleto():
            return _build.error_in_progress()       # ADR-037 §2: nothing is read, written or committed
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / TAREAS, id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("status") == "in_review" and nuevo == "todo":
                raise ErrorMemoria(f"{meta['id']} is in review: to ask for corrections use `request_changes`; "
                                   "'todo' is only for tasks that never ran.")
            antes = meta.get("status")
            meta["status"], meta["updated"] = nuevo, _hoy()
            if commit:
                meta["commit"] = commit
            entrada = _proyectos().get(proyecto, {})
            if nuevo == "in_progress":
                meta["routing"] = _delegacion.routing(entrada, meta, _delegacion.cliente_actual())
            correccion = None
            if resultado and antes == "in_review" and nuevo == "in_review":
                solo = resultado.strip()
                if "\n" not in solo and _workers.LINEA.match(solo):
                    try:
                        _workers.parsear_workers(solo)
                        correccion = _workers.corregir_workers(cuerpo, solo)
                    except ValueError:
                        pass
            if correccion:
                cuerpo = correccion[0]
            elif resultado:
                cuerpo = _anexar_resultado(cuerpo, f"### {_hoy()} · {nuevo}\n{resultado.strip()}")
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta], f"{meta['id']} → {nuevo}")
            guia = ""
            if nuevo == "in_progress":
                partes = (_integraciones._guia_en_curso(proyecto), _modelos.bloque(entrada),
                          _delegacion.bloque(entrada, meta))
                guia = "\n\n".join(p for p in partes if p)
            if nuevo == "in_review":
                politica = (_delegacion.politica_de_routing(meta.get("routing", ""))
                            or _delegacion.efectiva(entrada, meta)[0])
                guia = _delegacion.aviso_in_review(politica, resultado)
            if nuevo == "merged":
                guia = _recordatorio_resuelve(proyecto, meta.get("resolves", ""))
            nota = ""
            if correccion:
                nota = (" · Workers line replaced in the latest result block" if correccion[1]
                        else " · Workers line added to the latest result block")
            return f"{meta['id']} → {nuevo}{nota} · commit {sha}" + (f"\n\n{guia}" if guia else "")
    return _ejecutar(f)


@herramienta
def request_changes(project: str, id: str, findings: str, additional_criteria: str = "") -> str:
    """Sends a task in review back so the coding agent fixes it on the SAME branch.
    Use it only when the user, after reviewing the result, decides to ask for changes.
    `findings`: what is approved and what fails, and why. `additional_criteria`: a verifiable list of what the fix
    must meet (added to the original criteria). The task becomes 'changes_requested' and is re-run with
    /run-task T-NNN, which continues on the existing branch without rewriting earlier commits.
    To extend a task that has not run yet (todo), use amend_task."""
    proyecto, observaciones, criterios_adicionales = project, findings, additional_criteria

    def f():
        if not observaciones.strip():
            raise ErrorMemoria("`findings` is required: the coding agent runs without this chat.")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / TAREAS, id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("status") not in ("in_review", "failed"):
                raise ErrorMemoria(f"{meta['id']} is '{meta.get('status')}': only in_review or failed tasks can be sent "
                                   "back (use amend_task to extend a todo task).")
            n = int(meta.get("reviews", 0) or 0) + 1
            meta.update(status="changes_requested", updated=_hoy(), reviews=n)
            base = f" (on top of commit {meta['commit']})" if meta.get("commit") else ""
            bloque = [f"### Review {n} · {_hoy()} · changes_requested",
                      f"Fix on the SAME branch `{meta.get('branch', '(the task branch)')}`{base}, with new commits; "
                      "the original criteria still apply.", "", "**Findings**", observaciones.strip()]
            if criterios_adicionales.strip():
                bloque += ["", "**Additional criteria**", criterios_adicionales.strip()]
            cuerpo = _anexar_resultado(cuerpo, "\n".join(bloque))
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta], f"{meta['id']} → changes_requested (review {n})")
            return f"{meta['id']} → changes_requested (review {n}) · commit {sha}\nRe-run it with: /run-task {meta['id']}"
    return _ejecutar(f)


@herramienta
def list_tasks(project: str, include_closed: bool = False) -> str:
    """Lists the code tasks with their status and branch. Closed ones (merged, discarded) only with
    include_closed=True."""
    return _ejecutar(lambda: "\n".join(_resumen_tareas(project, not include_closed)) or "(no tasks)")
