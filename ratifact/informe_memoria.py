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
from ratifact.plurales import contar
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
        return [f"- Decisions: no configuration ({config})"]
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
    lineas = ["- Decisions created in the period (per the memory): "
              + ("; ".join(f"{n}: " + " · ".join(f"{e} {c[e]}" for e in ESTADOS_DECISION)
                           for n, c in por_proyecto.items()) or "none")]
    lineas.append(f"- Open proposals today: {abiertas} · older than {contar(DIAS_PROPUESTA_VIEJA, 'day')}: {len(viejas)}")
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
        return [f"- no configuration ({config})"]
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
        grupos = {"declared in resolves": defaultdict(list), "mentioned in the spec": defaultdict(list),
                  "mentioned in the Result": defaultdict(list)}
        for archivo in _carpeta(mem, "tasks").glob("T-*.md"):
            meta, cuerpo = _registro(archivo, "tarea")
            if meta.get("status") != "merged":
                continue
            id_tarea = _normalizar_id(meta.get("id") or re.match(r"T-\d+", archivo.name).group(0))
            ref = (id_tarea, _fecha_integracion(meta, cuerpo))
            spec, resultado = _menciones(cuerpo)
            for clave, ids in (("declared in resolves", {i for i, _ in _ids_resuelve(meta.get("resolves", ""))}),
                               ("mentioned in the spec", spec), ("mentioned in the Result", resultado)):
                for i in ids & abiertos:
                    grupos[clave][i].append(ref)
        lineas.append(f"  {nombre}")
        for clave, por_id in grupos.items():
            lineas.append(f"    {clave}:" + ("" if por_id else " (none)"))
            for i in sorted(por_id, key=_numero):
                refs = ", ".join(f"{t} (merged {fecha})"
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
            # git writes "Z" for UTC commits; fromisoformat accepts it only from Python 3.11.
            fecha = fecha[:-1] + "+00:00" if fecha.endswith("Z") else fecha
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


def _porcentaje(parte: int, total: int) -> str:
    return f"{parte / total * 100:.0f} %" if total else "—"


def indicador_delegacion(desde: dt.datetime, proyecto: str | None) -> list[str]:
    """Delegation indicator (see ratifact.informe_delegacion); kept here as the import path the tests and callers use.
    Imported on call: informe_delegacion reads this module's helpers."""
    from ratifact.informe_delegacion import indicador_delegacion as _indicador
    return _indicador(desde, proyecto)
