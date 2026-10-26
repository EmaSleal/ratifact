"""`ratifact report` (antes analizar_uso.py): indicadores que salen de las memorias, no del log — decisiones por
estado y pendientes abiertos referenciados por tareas integradas. La configuración y la carpeta de proyectos se
resuelven igual que el servidor (ratifact.config, en cada llamada) y la memoria con la clave "memory"/"memoria" o la
ruta por defecto (config._mem_por_defecto: .ratifact/<nombre>, o .memorias/<nombre> si sigue ahí). Lee memorias v1
(carpetas, claves y estados en español) y v2 (en inglés): todo se normaliza a v2 antes de contar. Nunca migra ni
escribe."""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from ratifact.config import _base, _mem_por_defecto, _ruta_config
from ratifact.registros import _ids_resuelve, _leer_registro, _normalizar_id, _numero_id as _numero
from ratifact.vocabulario import CARPETAS_V1, CLAVES_V1, ESTADOS_V1

ESTADOS_DECISION = ("accepted", "proposed", "superseded", "rejected")
DIAS_PROPUESTA_VIEJA = 7
# no cuentan como mención (v1 y v2)
SECCIONES_EXCLUIDAS = {"Fuera de alcance", "Notas", "Cómo verificar", "Resuelve",
                       "Out of scope", "Notes", "How to verify", "Resolves"}
SECCIONES_RESULTADO = {"Resultado", "Result"}


def ruta_config() -> Path:
    """Igual que ratifact.config.CONFIG, resuelto en cada llamada."""
    return _ruta_config()


def _memoria(nombre: str, p: dict) -> Path:
    """Igual que ratifact.config._mem (sin la validación ADR-010: aquí solo se lee)."""
    memoria = p.get("memory") or p.get("memoria")     # projects.json en inglés o en español (gana el inglés)
    if memoria:
        return Path(memoria).expanduser()
    return _mem_por_defecto(nombre, _base())



def _carpeta(mem: Path, nueva: str) -> Path:
    """Carpeta de registros v2 (decisions, pending, tasks) o, en una memoria v1 aún sin migrar, su nombre v1."""
    vieja = next(v1 for v1, v2 in CARPETAS_V1.items() if v2 == nueva)
    return mem / nueva if (mem / nueva).is_dir() or not (mem / vieja).is_dir() else mem / vieja



def _registro(archivo: Path, tipo: str) -> tuple[dict, str]:
    """Frontmatter con claves y estado v2 (traduce los de una memoria v1) y cuerpo."""
    meta, cuerpo = _leer_registro(archivo)
    meta = {CLAVES_V1.get(k, k): v for k, v in meta.items()}
    meta["status"] = ESTADOS_V1[tipo].get(meta.get("status", ""), meta.get("status", ""))
    return meta, cuerpo



def _fecha(meta: dict) -> dt.date | None:
    for clave in ("created", "date"):
        try:
            return dt.datetime.fromisoformat(meta[clave]).date() if clave == "created" else dt.date.fromisoformat(meta[clave])
        except (KeyError, ValueError):
            continue
    return None



def indicador_decisiones(desde: dt.datetime, proyecto: str | None) -> list[str]:
    """Decisiones creadas en el período por estado (desde los archivos de la memoria) y propuestas abiertas viejas."""
    config = ruta_config()
    try:
        proyectos = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"- Decisiones: sin configuración ({config})"]
    por_proyecto, viejas, abiertas = {}, [], 0
    limite_vieja = dt.date.today() - dt.timedelta(days=DIAS_PROPUESTA_VIEJA)
    for nombre, p in proyectos.items():
        if proyecto and nombre != proyecto:
            continue
        conteo = Counter()
        for archivo in sorted(_carpeta(_memoria(nombre, p), "decisions").glob("ADR-*.md")):
            meta, _ = _registro(archivo, "decision")
            fecha, estado = _fecha(meta), meta.get("status", "")
            if fecha and fecha >= desde.date():
                conteo[estado] += 1
            abiertas += estado == "proposed"
            if estado == "proposed" and fecha and fecha < limite_vieja:
                viejas.append(f"  {nombre} {meta.get('id', archivo.stem)} {fecha.isoformat()} {meta.get('title', '')}")
        por_proyecto[nombre] = conteo
    lineas = ["- Decisiones creadas en el período (según la memoria): "
              + ("; ".join(f"{n}: " + " · ".join(f"{e} {c[e]}" for e in ESTADOS_DECISION)
                           for n, c in por_proyecto.items()) or "ninguna")]
    lineas.append(f"- Propuestas abiertas hoy: {abiertas} · con más de {DIAS_PROPUESTA_VIEJA} días: {len(viejas)}")
    return lineas + viejas



def _fecha_integracion(meta: dict, cuerpo: str) -> str:
    """Fecha de "### AAAA-MM-DD · merged" (v1: "· integrada") en el Result (la última); si no está, `updated` o
    `date`."""
    fechas = re.findall(r"^### (\d{4}-\d{2}-\d{2}) · (?:merged|integrada)\b", cuerpo, re.M)
    return fechas[-1] if fechas else meta.get("updated") or meta.get("date", "?")



def _menciones(cuerpo: str) -> tuple[set, set]:
    """Ids P-NNN del texto de una tarea, separados en (spec, resultado). Spec: todo fuera de "## Result" (título,
    Goal, Criteria, Decisions, Files) más los bloques "### Review N" del Result. Se excluyen Out of scope, Notes,
    How to verify y Resolves (lo declarado va aparte). Acepta también los títulos v1 en español."""
    spec, resultado = set(), set()
    seccion, revision = "", False
    for linea in cuerpo.splitlines():
        if linea.startswith("## "):
            seccion, revision = linea[3:].strip(), False
        elif linea.startswith("### ") and seccion in SECCIONES_RESULTADO:
            revision = linea[4:].startswith(("Revisión", "Review"))
        if seccion in SECCIONES_EXCLUIDAS:
            continue
        destino = resultado if seccion in SECCIONES_RESULTADO and not revision else spec
        destino.update(_normalizar_id(m) for m in re.findall(r"(?<![\w-])[Pp]-\d+\b", linea))
    return spec, resultado



def higiene_pendientes(proyecto: str | None) -> list[str]:
    """ADR-027: pendientes abiertos referenciados por tareas integradas, por proyecto: declarados en `resuelve` y
    mencionados en el texto (spec y Resultado), cada uno con la tarea y su fecha de integración."""
    config = ruta_config()
    try:
        proyectos = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"- sin configuración ({config})"]
    lineas = []
    for nombre, p in proyectos.items():
        if proyecto and nombre != proyecto:
            continue
        mem = _memoria(nombre, p)
        abiertos = set()
        for archivo in _carpeta(mem, "pending").glob("P-*.md"):
            meta, _ = _registro(archivo, "pendiente")
            if meta.get("status") == "open":
                abiertos.add(_normalizar_id(meta.get("id") or archivo.stem))
        grupos = {"declarados en resuelve": defaultdict(list), "mencionados en la spec": defaultdict(list),
                  "mencionados en el Resultado": defaultdict(list)}
        for archivo in _carpeta(mem, "tasks").glob("T-*.md"):
            meta, cuerpo = _registro(archivo, "tarea")
            if meta.get("status") != "merged":
                continue
            id_tarea = _normalizar_id(meta.get("id") or re.match(r"T-\d+", archivo.name).group(0))
            ref = (id_tarea, _fecha_integracion(meta, cuerpo))
            spec, resultado = _menciones(cuerpo)
            for clave, ids in (("declarados en resuelve", {i for i, _ in _ids_resuelve(meta.get("resolves", ""))}),
                               ("mencionados en la spec", spec), ("mencionados en el Resultado", resultado)):
                for i in ids & abiertos:
                    grupos[clave][i].append(ref)
        lineas.append(f"  {nombre}")
        for clave, por_id in grupos.items():
            lineas.append(f"    {clave}:" + ("" if por_id else " (ninguno)"))
            for i in sorted(por_id, key=_numero):
                refs = ", ".join(f"{t} (integrada {fecha})"
                                 for t, fecha in sorted(por_id[i], key=lambda r: _numero(r[0])))
                lineas.append(f"      {i}: {refs}")
    return lineas



def _transiciones(mem: Path) -> dict[str, list[tuple[dt.datetime, str]]]:
    """Cambios de estado de cada tarea según el historial git de la memoria ("memoria: T-001 → in_progress"), en orden
    cronológico. Solo lee; sin git devuelve {}."""
    r = subprocess.run(["git", "-C", str(mem), "log", "--reverse", "--format=%cI%x09%s"], capture_output=True,
                       text=True)
    salida: dict[str, list[tuple[dt.datetime, str]]] = defaultdict(list)
    for linea in r.stdout.splitlines() if r.returncode == 0 else []:
        fecha, _, asunto = linea.partition("\t")
        m = re.search(r"(T-\d+) → ([a-z_]+)$", asunto)
        if m:
            salida[_normalizar_id(m.group(1))].append((dt.datetime.fromisoformat(fecha), m.group(2)))
    return salida


def _duracion(transiciones: list[tuple[dt.datetime, str]]) -> dt.timedelta | None:
    """Del último in_progress al primer in_review posterior."""
    inicio = fin = None
    for fecha, estado in transiciones:
        if estado == "in_progress":
            inicio, fin = fecha, None
        elif estado == "in_review" and inicio and fin is None:
            fin = fecha
    return fin - inicio if inicio and fin else None


def _promedio(valores: list[float]) -> str:
    return f"{sum(valores) / len(valores):.1f}" if valores else "—"


def indicador_delegacion(desde: dt.datetime, proyecto: str | None) -> list[str]:
    """ADR-036 §7: cumplimiento de la política de delegación por proyecto, desde las tareas con `routing:` cambiadas
    en el período (por `at=` del routing cuando existe, ADR-037 §3; si no, por `updated`) (las anteriores a la política, sin `routing:`, se cuentan aparte), y comparación delegadas vs. no
    delegadas en revisiones (changes_requested) y duración in_progress → in_review."""
    from ratifact.delegacion import at_de_routing, politica_de_routing, workers_del_resultado
    config = ruta_config()
    try:
        proyectos = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"- sin configuración ({config})"]
    lineas = []
    for nombre, p in proyectos.items():
        if proyecto and nombre != proyecto or not isinstance(p, dict):
            continue
        mem = _memoria(nombre, p)
        tareas = []
        for archivo in sorted(_carpeta(mem, "tasks").glob("T-*.md")):
            meta, cuerpo = _registro(archivo, "tarea")
            at = at_de_routing(meta.get("routing", ""))      # ADR-037 §3: la hora de la ejecución, si se grabó
            fecha = at.date().isoformat() if at else meta.get("updated") or meta.get("date", "")
            try:
                if dt.date.fromisoformat(str(fecha)[:10]) < desde.date():
                    continue
            except ValueError:
                continue
            tareas.append((meta, cuerpo, archivo))
        if not tareas:
            continue
        con = [(m, c, a) for m, c, a in tareas if m.get("routing")]
        transiciones = _transiciones(mem) if con else {}
        requeridas = cumplen = escaladas = 0
        grupos = {"delegadas": ([], []), "no delegadas": ([], [])}
        for meta, cuerpo, archivo in con:
            resultado = cuerpo.split("\n## Result", 1)[-1]
            trabajadores, _ = workers_del_resultado(resultado)
            delegada = bool(trabajadores and trabajadores.total)
            if politica_de_routing(meta["routing"]) == "required":
                requeridas += 1
                cumplen += delegada
            escaladas += bool(trabajadores and trabajadores.escalados)
            revisiones, horas = grupos["delegadas" if delegada else "no delegadas"]
            revisiones.append(len(re.findall(r"^### (?:Review|Revisión) \d+ · ", cuerpo, re.M)))
            id_ = _normalizar_id(meta.get("id") or re.match(r"T-\d+", archivo.name).group(0))
            duracion = _duracion(transiciones.get(id_, []))
            if duracion is not None:
                horas.append(duracion.total_seconds() / 3600)
        porcentaje = f"{cumplen / requeridas * 100:.0f} %" if requeridas else "—"
        lineas.append(f"  {nombre}: {len(con)} tareas con routing · required {requeridas} · con trabajadores "
                      f"{cumplen} · cumplimiento {porcentaje} · escalamientos {escaladas} · sin routing (anteriores "
                      f"a la política): {len(tareas) - len(con)}")
        for grupo, (revisiones, horas) in grupos.items():
            lineas.append(f"    {grupo}: {len(revisiones)} tareas · revisiones (changes_requested) promedio "
                          f"{_promedio(revisiones)} · in_progress → in_review promedio {_promedio(horas)} h")
    return lineas or ["- ninguna tarea en el período"]
