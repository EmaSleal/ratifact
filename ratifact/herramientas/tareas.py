"""Herramientas de tareas para el agente de código: registrar, actualizar, devolver y listar tareas."""
from __future__ import annotations

from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, herramienta
from ratifact.catalogo import _registros_en
from ratifact.config import ErrorMemoria, _mem, _proyectos, _repos
from ratifact.esquema import _bloqueo
from ratifact.integraciones import registro as _integraciones
from ratifact.registros import (_buscar_registro, _commit, _duplicado_reciente, _escribir_registro, _hoy,
                                _ids_resuelve, _leer_registro, _mensaje_duplicado, _resumen_tareas, _siguiente_id,
                                _slug, _texto_resuelve)


# ───────────────────────── tareas para Claude Code ─────────────────────────

ESTADOS_TAREA = ("pendiente", "en_curso", "en_revision", "devuelta", "fallida", "integrada", "descartada")
MARCA_RESULTADO = "(lo completa Claude Code al terminar)"


def _anexar_resultado(cuerpo: str, bloque: str) -> str:
    """Agrega un bloque a la sección Resultado (reemplaza el marcador inicial la primera vez)."""
    if MARCA_RESULTADO in cuerpo:
        return cuerpo.replace(MARCA_RESULTADO, bloque, 1)
    return cuerpo.rstrip() + "\n\n" + bloque


def _comando_pruebas(proyecto: str, repositorio: str = "") -> str:
    """Comando de pruebas de un repo; sin `repositorio` en proyectos multi-repo, la lista completa."""
    cfg = _proyectos().get(proyecto, {}).get("pruebas", "")
    if isinstance(cfg, dict):
        if repositorio:
            return cfg.get(repositorio, "")
        return "; ".join(f"{repo}/: {cmd}" for repo, cmd in cfg.items())
    return cfg


def _pendientes_abiertos(proyecto: str) -> dict[str, str]:
    """Id → tema de cada pendiente abierto, desde el catálogo (ADR-022)."""
    return {r.id: r.titulo for r in _registros_en(proyecto, "P") if r.estado == "abierta"}


def _validar_resuelve(proyecto: str, resuelve: str) -> list[tuple[str, bool]]:
    """`resuelve` de registrar_tarea (ADR-027): cada id debe existir y estar abierto; si no, ErrorMemoria con todos los
    inválidos (y no se escribe nada)."""
    ids = _ids_resuelve(resuelve)
    abiertos = _pendientes_abiertos(proyecto)
    existentes = {r.id for r in _registros_en(proyecto, "P")}
    malos = [f"{i} ({'no está abierto' if i in existentes else 'no existe'})" for i, _ in ids if i not in abiertos]
    if malos:
        raise ErrorMemoria(f"`resuelve` inválido: {', '.join(malos)}. Solo pendientes abiertos (P-NNN, opcional "
                           "\"(parcial)\").")
    return ids


@herramienta
def registrar_tarea(proyecto: str, titulo: str, objetivo: str, criterios_aceptacion: str,
                    decisiones: str = "", archivos: str = "", fuera_de_alcance: str = "",
                    notas: str = "", repositorio: str = "", resuelve: str = "") -> str:
    """Crea una especificación de trabajo para Claude Code en .project/tareas/T-NNN.md (estado 'pendiente').
    En proyectos de varios repos, `repositorio` (obligatorio) indica la carpeta donde se trabaja; en proyectos de
    un solo repositorio se ignora (la respuesta lo avisa).
    Debe ser autosuficiente: Claude Code la ejecuta sin este chat. `criterios_aceptacion`: lista verificable
    (pruebas que deben pasar, comportamiento observable). `decisiones`: ids de ADR aplicables.
    `archivos`: rutas que probablemente se tocan. El usuario la ejecuta con /tarea T-NNN en Claude Code.
    `resuelve`: pendientes que la tarea resuelve, separados por coma, cada uno opcionalmente con "(parcial)"
    (p. ej. "P-036, P-037 (parcial)"); deben existir y estar abiertos. Se guarda en la tarea (sección "Resuelve") y,
    al integrarla, actualizar_tarea recuerda los que sigan abiertos. Nunca cierra pendientes.
    La respuesta agrega la línea de integraciones detectadas (no se escribe en la tarea).
    Idempotente (ADR-019): si ya hay una tarea con este título (sin distinguir mayúsculas ni espacios) creada
    en los últimos minutos Y TODAVÍA en estado 'pendiente', no crea nada nuevo y devuelve el id existente
    (con el comando /tarea para repetírselo al usuario). Si esa tarea ya cambió de estado (p. ej. en_curso:
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
            carpeta = _mem(proyecto) / "tareas"
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "T", "titulo", titulo, "pendiente")
            if dup:
                return _mensaje_duplicado(dup["id"], f"Ejecutar en Claude Code: /tarea {dup['id']}") + nota
            ids = _validar_resuelve(proyecto, resuelve) if resuelve.strip() else []
            id_ = _siguiente_id(carpeta, "T")
            ruta = carpeta / f"{id_}-{_slug(titulo)}.md"
            meta = {"id": id_, "titulo": titulo, "estado": "pendiente", "fecha": _hoy(),
                    "creado": _registros._ahora().isoformat(timespec="seconds"),
                    "rama": f"{id_.lower()}-{_slug(titulo)}"}
            if repo:
                meta["repositorio"] = repo
            if ids:
                meta["resuelve"] = _texto_resuelve(ids)
            secciones = [f"# {id_} — {titulo}", "## Objetivo", objetivo,
                         "## Criterios de aceptación", criterios_aceptacion]
            if ids:
                temas = _pendientes_abiertos(proyecto)
                secciones += ["## Resuelve", "\n".join(f"- {i}{' (parcial)' if parcial else ''} · {temas[i]}"
                                                        for i, parcial in ids)]
            for nombre, valor in (("Decisiones aplicables", decisiones), ("Archivos involucrados", archivos),
                                  ("Fuera de alcance", fuera_de_alcance), ("Notas", notas)):
                if valor:
                    secciones += [f"## {nombre}", valor]
            cmd = _comando_pruebas(proyecto, repo)
            donde = f"Desde `{repo}/`" if repo else "Desde la raíz del repositorio"
            secciones += ["## Cómo verificar",
                          f"{donde}: `{cmd}`" if cmd else
                          "(sin comando de pruebas configurado: pregúntale al usuario o usa actualizar_proyecto)"]
            secciones += ["## Resultado", MARCA_RESULTADO]
            _escribir_registro(ruta, meta, "\n\n".join(secciones))
            sha = _commit(proyecto, [ruta], f"{id_} {titulo} (pendiente)")
            linea = _integraciones._linea_integraciones(proyecto)
            return (f"{id_} registrada · rama sugerida {meta['rama']} · commit {sha}\nEjecutar en Claude Code: /tarea {id_}"
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
    """Cambia el estado de una tarea (pendiente, en_curso, en_revision, fallida, integrada, descartada).
    `resultado`: qué se hizo, pruebas ejecutadas y su salida resumida, desvíos respecto de la spec.
    'integrada' y 'descartada' solo con confirmación explícita del usuario.
    Para pedir correcciones tras revisar una tarea usa `devolver_tarea`, no este cambio de estado.
    Con 'en_curso', la respuesta trae la guía de integraciones activas (ejecutar, verificar, cerrar), calculada en
    ese momento; es condicional: síguela solo si tienes esas herramientas. No se escribe en la tarea.
    Con 'integrada', si la tarea declara `resuelve`, la respuesta recuerda los pendientes que siguen abiertos (no
    cierra ni modifica ninguno)."""
    def f():
        if estado not in ESTADOS_TAREA:
            raise ErrorMemoria(f"Estado inválido. Usa: {', '.join(ESTADOS_TAREA)}")
        if estado == "devuelta":
            raise ErrorMemoria("Para devolver una tarea usa `devolver_tarea` (registra la revisión con formato fijo).")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / "tareas", id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("estado") == "en_revision" and estado == "pendiente":
                raise ErrorMemoria(f"{meta['id']} está en revisión: para pedir correcciones usa `devolver_tarea`; "
                                   "'pendiente' es solo para tareas que nunca se ejecutaron.")
            meta["estado"], meta["actualizada"] = estado, _hoy()
            if commit:
                meta["commit"] = commit
            if resultado:
                cuerpo = _anexar_resultado(cuerpo, f"### {_hoy()} · {estado}\n{resultado.strip()}")
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta], f"{meta['id']} → {estado}")
            guia = _integraciones._guia_en_curso(proyecto) if estado == "en_curso" else ""
            if estado == "integrada":
                guia = _recordatorio_resuelve(proyecto, meta.get("resuelve", ""))
            return f"{meta['id']} → {estado} · commit {sha}" + (f"\n\n{guia}" if guia else "")
    return _ejecutar(f)


@herramienta
def devolver_tarea(proyecto: str, id: str, observaciones: str, criterios_adicionales: str = "") -> str:
    """Devuelve una tarea en revisión para que el agente de código la corrija en la MISMA rama.
    Úsala solo cuando el usuario, tras revisar el resultado, decida pedir cambios.
    `observaciones`: qué se aprueba y qué falla, con el porqué. `criterios_adicionales`: lista verificable de lo que
    debe cumplir la corrección (se suma a los criterios originales). La tarea queda 'devuelta' y se reejecuta
    con /tarea T-NNN, que continúa sobre la rama existente sin reescribir los commits anteriores."""
    def f():
        if not observaciones.strip():
            raise ErrorMemoria("`observaciones` es obligatorio: el agente de código ejecuta sin este chat.")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / "tareas", id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("estado") not in ("en_revision", "fallida"):
                raise ErrorMemoria(f"{meta['id']} está '{meta.get('estado')}': solo se devuelven tareas en_revision o fallida.")
            n = int(meta.get("revisiones", 0) or 0) + 1
            meta.update(estado="devuelta", actualizada=_hoy(), revisiones=n)
            base = f" (sobre el commit {meta['commit']})" if meta.get("commit") else ""
            bloque = [f"### Revisión {n} · {_hoy()} · devuelta",
                      f"Corregir en la MISMA rama `{meta.get('rama', '(la de la tarea)')}`{base}, con commits nuevos; "
                      "los criterios originales siguen vigentes.", "", "**Observaciones**", observaciones.strip()]
            if criterios_adicionales.strip():
                bloque += ["", "**Criterios adicionales**", criterios_adicionales.strip()]
            cuerpo = _anexar_resultado(cuerpo, "\n".join(bloque))
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta], f"{meta['id']} devuelta (revisión {n})")
            return f"{meta['id']} devuelta (revisión {n}) · commit {sha}\nReejecutar en Claude Code: /tarea {meta['id']}"
    return _ejecutar(f)


@herramienta
def listar_tareas(proyecto: str, incluir_cerradas: bool = False) -> str:
    """Lista las tareas de Claude Code con su estado y rama."""
    return _ejecutar(lambda: "\n".join(_resumen_tareas(proyecto, not incluir_cerradas)) or "(sin tareas)")
