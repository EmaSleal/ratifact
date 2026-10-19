"""Herramientas de tareas para el agente de código: registrar, actualizar, devolver y listar tareas."""
from __future__ import annotations

from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, herramienta
from ratifact.catalogo import _registros_en
from ratifact.config import ErrorMemoria, _mem, _proyectos, _repos, _valor
from ratifact.esquema import _bloqueo
from ratifact.integraciones import registro as _integraciones
from ratifact.registros import (_buscar_registro, _commit, _duplicado_reciente, _escribir_registro, _hoy,
                                _ids_resuelve, _leer_registro, _mensaje_duplicado, _resumen_tareas, _siguiente_id,
                                _slug, _texto_resuelve)
from ratifact.vocabulario import ESTADOS, TAREAS, _normalizar_estado


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


def _validar_resuelve(proyecto: str, resuelve: str) -> list[tuple[str, bool]]:
    """`resuelve` de registrar_tarea (ADR-027): cada id debe existir y estar abierto; si no, ErrorMemoria con todos los
    inválidos (y no se escribe nada)."""
    ids = _ids_resuelve(resuelve)
    abiertos = _pendientes_abiertos(proyecto)
    existentes = {r.id for r in _registros_en(proyecto, "P")}
    malos = [f"{i} ({'no está abierto' if i in existentes else 'no existe'})" for i, _ in ids if i not in abiertos]
    if malos:
        raise ErrorMemoria(f"`resuelve` inválido: {', '.join(malos)}. Solo pendientes abiertos (P-NNN, opcional "
                           "\"(parcial)\" o \"(partial)\").")
    return ids


@herramienta
def registrar_tarea(proyecto: str, titulo: str, objetivo: str, criterios_aceptacion: str,
                    decisiones: str = "", archivos: str = "", fuera_de_alcance: str = "",
                    notas: str = "", repositorio: str = "", resuelve: str = "") -> str:
    """Crea una especificación de trabajo para Claude Code en .project/tasks/T-NNN.md (estado 'todo').
    En proyectos de varios repos, `repositorio` (obligatorio) indica la carpeta donde se trabaja; en proyectos de
    un solo repositorio se ignora (la respuesta lo avisa).
    Debe ser autosuficiente: Claude Code la ejecuta sin este chat. `criterios_aceptacion`: lista verificable
    (pruebas que deben pasar, comportamiento observable). `decisiones`: ids de ADR aplicables.
    `archivos`: rutas que probablemente se tocan. El usuario la ejecuta con /tarea T-NNN en Claude Code.
    `resuelve`: pendientes que la tarea resuelve, separados por coma, cada uno opcionalmente con "(parcial)" o
    "(partial)" (p. ej. "P-036, P-037 (parcial)"); deben existir y estar abiertos. Se guarda en la tarea (sección
    "Resolves") y,
    al integrarla, actualizar_tarea recuerda los que sigan abiertos. Nunca cierra pendientes.
    La respuesta agrega la línea de integraciones detectadas (no se escribe en la tarea).
    Idempotente (ADR-019): si ya hay una tarea con este título (sin distinguir mayúsculas ni espacios) creada
    en los últimos minutos Y TODAVÍA en estado 'todo', no crea nada nuevo y devuelve el id existente
    (con el comando /tarea para repetírselo al usuario). Si esa tarea ya cambió de estado (p. ej. in_progress:
    ya se está ejecutando), un humano o el agente de código ya intervino, así que se registra una tarea
    nueva."""
    def f():
        repos, repo = _repos(proyecto), repositorio
        if repos and repositorio not in repos:
            raise ErrorMemoria(f"Proyecto de varios repositorios: indica `repositorio` ({', '.join(repos)}).")
        nota = ""
        if not repos and repositorio:     # no es un error: el valor no cambia nada, solo se avisa que se ignoró
            repo, nota = "", "\n(proyecto de un solo repositorio: se ignoró `repositorio`)"
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / TAREAS
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "T", "title", titulo, "todo")
            if dup:
                return _mensaje_duplicado(dup["id"], f"Ejecutar en Claude Code: /tarea {dup['id']}") + nota
            ids = _validar_resuelve(proyecto, resuelve) if resuelve.strip() else []
            id_ = _siguiente_id(carpeta, "T")
            ruta = carpeta / f"{id_}-{_slug(titulo)}.md"
            meta = {"id": id_, "title": titulo, "status": "todo", "date": _hoy(),
                    "created": _registros._ahora().isoformat(timespec="seconds"),
                    "branch": f"{id_.lower()}-{_slug(titulo)}"}
            if repo:
                meta["repo"] = repo
            if ids:
                meta["resolves"] = _texto_resuelve(ids)
            secciones = [f"# {id_} — {titulo}", "## Goal", objetivo,
                         "## Acceptance criteria", criterios_aceptacion]
            if ids:
                temas = _pendientes_abiertos(proyecto)
                secciones += ["## Resolves", "\n".join(f"- {i}{' (partial)' if parcial else ''} · {temas[i]}"
                                                        for i, parcial in ids)]
            for nombre, valor in (("Applicable decisions", decisiones), ("Files involved", archivos),
                                  ("Out of scope", fuera_de_alcance), ("Notes", notas)):
                if valor:
                    secciones += [f"## {nombre}", valor]
            cmd = _comando_pruebas(proyecto, repo)
            donde = f"Desde `{repo}/`" if repo else "Desde la raíz del repositorio"
            secciones += ["## How to verify",
                          f"{donde}: `{cmd}`" if cmd else
                          "(sin comando de pruebas configurado: pregúntale al usuario o usa actualizar_proyecto)"]
            secciones += ["## Result", MARCA_RESULTADO]
            _escribir_registro(ruta, meta, "\n\n".join(secciones))
            sha = _commit(proyecto, [ruta], f"{id_} {titulo} (todo)")
            linea = _integraciones._linea_integraciones(proyecto)
            return (f"{id_} registrada · rama sugerida {meta['branch']} · commit {sha}\nEjecutar en Claude Code: /tarea {id_}"
                    + nota + (f"\n{linea}" if linea else ""))
    return _ejecutar(f)


def _recordatorio_resuelve(proyecto: str, resuelve: str) -> str:
    """Al integrar (ADR-027): los pendientes declarados en `resuelve` que siguen abiertos, con qué hacer en cada caso."""
    abiertos = _pendientes_abiertos(proyecto) if resuelve else {}
    return "\n".join(f"{i} (parcial) sigue abierto: registra qué falta" if parcial else
                     f'{i} sigue abierto: ciérralo con cerrar_pendiente("{proyecto}", "{i}", ...) si quedó resuelto'
                     for i, parcial in _ids_resuelve(resuelve) if i in abiertos)


@herramienta
def actualizar_tarea(proyecto: str, id: str, estado: str, resultado: str = "", commit: str = "") -> str:
    """Cambia el estado de una tarea (todo, in_progress, in_review, failed, merged, discarded; también acepta los
    nombres en español: pendiente, en_curso, en_revision, fallida, integrada, descartada). Se guarda en inglés.
    `resultado`: qué se hizo, pruebas ejecutadas y su salida resumida, desvíos respecto de la spec.
    'merged' y 'discarded' solo con confirmación explícita del usuario.
    Para pedir correcciones tras revisar una tarea usa `devolver_tarea`, no este cambio de estado.
    Con 'in_progress', la respuesta trae la guía de integraciones activas (ejecutar, verificar, cerrar), calculada en
    ese momento; es condicional: síguela solo si tienes esas herramientas. No se escribe en la tarea.
    Con 'merged', si la tarea declara `resuelve`, la respuesta recuerda los pendientes que siguen abiertos (no
    cierra ni modifica ninguno)."""
    def f():
        nuevo = _normalizar_estado("tarea", estado)
        if nuevo == "changes_requested":
            raise ErrorMemoria("Para devolver una tarea usa `devolver_tarea` (registra la revisión con formato fijo).")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / TAREAS, id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("status") == "in_review" and nuevo == "todo":
                raise ErrorMemoria(f"{meta['id']} está en revisión: para pedir correcciones usa `devolver_tarea`; "
                                   "'todo' es solo para tareas que nunca se ejecutaron.")
            meta["status"], meta["updated"] = nuevo, _hoy()
            if commit:
                meta["commit"] = commit
            if resultado:
                cuerpo = _anexar_resultado(cuerpo, f"### {_hoy()} · {nuevo}\n{resultado.strip()}")
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta], f"{meta['id']} → {nuevo}")
            guia = _integraciones._guia_en_curso(proyecto) if nuevo == "in_progress" else ""
            if nuevo == "merged":
                guia = _recordatorio_resuelve(proyecto, meta.get("resolves", ""))
            return f"{meta['id']} → {nuevo} · commit {sha}" + (f"\n\n{guia}" if guia else "")
    return _ejecutar(f)


@herramienta
def devolver_tarea(proyecto: str, id: str, observaciones: str, criterios_adicionales: str = "") -> str:
    """Devuelve una tarea en revisión para que el agente de código la corrija en la MISMA rama.
    Úsala solo cuando el usuario, tras revisar el resultado, decida pedir cambios.
    `observaciones`: qué se aprueba y qué falla, con el porqué. `criterios_adicionales`: lista verificable de lo que
    debe cumplir la corrección (se suma a los criterios originales). La tarea queda 'changes_requested' y se reejecuta
    con /tarea T-NNN, que continúa sobre la rama existente sin reescribir los commits anteriores."""
    def f():
        if not observaciones.strip():
            raise ErrorMemoria("`observaciones` es obligatorio: el agente de código ejecuta sin este chat.")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / TAREAS, id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("status") not in ("in_review", "failed"):
                raise ErrorMemoria(f"{meta['id']} está '{meta.get('status')}': solo se devuelven tareas in_review o failed.")
            n = int(meta.get("reviews", 0) or 0) + 1
            meta.update(status="changes_requested", updated=_hoy(), reviews=n)
            base = f" (sobre el commit {meta['commit']})" if meta.get("commit") else ""
            bloque = [f"### Review {n} · {_hoy()} · changes_requested",
                      f"Corregir en la MISMA rama `{meta.get('branch', '(la de la tarea)')}`{base}, con commits nuevos; "
                      "los criterios originales siguen vigentes.", "", "**Findings**", observaciones.strip()]
            if criterios_adicionales.strip():
                bloque += ["", "**Additional criteria**", criterios_adicionales.strip()]
            cuerpo = _anexar_resultado(cuerpo, "\n".join(bloque))
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta], f"{meta['id']} → changes_requested (review {n})")
            return f"{meta['id']} → changes_requested (revisión {n}) · commit {sha}\nReejecutar en Claude Code: /tarea {meta['id']}"
    return _ejecutar(f)


@herramienta
def listar_tareas(proyecto: str, incluir_cerradas: bool = False) -> str:
    """Lista las tareas de Claude Code con su estado y rama."""
    return _ejecutar(lambda: "\n".join(_resumen_tareas(proyecto, not incluir_cerradas)) or "(sin tareas)")
