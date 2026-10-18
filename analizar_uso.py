#!/usr/bin/env python3
"""Resumen del uso de memoria-proyectos a partir de logs/uso.jsonl.

Uso:  python3 analizar_uso.py [--dias N] [--proyecto game] [--log RUTA]
Log: --log, si no MEMORIA_PROYECTOS_LOG, si no <repo>/logs/uso.jsonl (el mismo que escribe el servidor).
Tokens estimados = caracteres / 4 (aproximación; el texto en español suele rondar 3,5–4,5).
El indicador de decisiones no sale del log sino de la memoria de cada proyecto (projects.json): la configuración
se resuelve igual que el servidor (MEMORIA_PROYECTOS_CONFIG o ~/.config/memoria-proyectos/projects.json) y la
memoria con la clave "memoria" o <MEMORIA_PROYECTOS_BASE o ~/Projects>/.memorias/<nombre>. Se replica esa lógica
(ratifact.config la fija al importarse) y se reutiliza el lector de frontmatter de ratifact.registros (sin mcp).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ratifact.registros import _ids_resuelve, _leer_registro, _normalizar_id, _numero_id as _numero  # noqa: E402

LOG_POR_DEFECTO = Path(__file__).resolve().parent / "logs" / "uso.jsonl"   # igual que LOG_USO del servidor
ESTADOS_DECISION = ("acordada", "propuesta", "reemplazada", "descartada")
DIAS_PROPUESTA_VIEJA = 7
TOKENS_ARRANQUE = 2000   # ADR-026: referencia de obtener_contexto (~8.000 caracteres)
SECCIONES_EXCLUIDAS = {"Fuera de alcance", "Notas", "Cómo verificar", "Resuelve"}   # no cuentan como mención
EXT_CODIGO = {".java", ".py", ".ts", ".js", ".vue", ".sql", ".xml", ".yml", ".yaml", ".kt"}


def percentil(valores: list, q: float):
    """Percentil por rango más cercano sobre `valores` ordenados (el mismo criterio que el p95 de ms)."""
    return valores[min(len(valores) - 1, int(len(valores) * q))]


def ruta_log(argumento: str | None) -> Path:
    """--log gana sobre MEMORIA_PROYECTOS_LOG, que gana sobre la ruta por defecto (resuelto en cada llamada)."""
    return Path(argumento or os.environ.get("MEMORIA_PROYECTOS_LOG") or LOG_POR_DEFECTO)


def ruta_config() -> Path:
    """Igual que ratifact.config.CONFIG, resuelto en cada llamada."""
    return Path(os.environ.get("MEMORIA_PROYECTOS_CONFIG",
                               Path.home() / ".config" / "memoria-proyectos" / "projects.json")).expanduser()


def _memoria(nombre: str, p: dict) -> Path:
    """Igual que ratifact.config._mem (sin la validación ADR-010: aquí solo se lee)."""
    if p.get("memoria"):
        return Path(p["memoria"]).expanduser()
    base = Path(os.environ.get("MEMORIA_PROYECTOS_BASE", Path.home() / "Projects")).expanduser()
    return base / ".memorias" / nombre


def _fecha(meta: dict) -> dt.date | None:
    for clave in ("creado", "fecha"):
        try:
            return dt.datetime.fromisoformat(meta[clave]).date() if clave == "creado" else dt.date.fromisoformat(meta[clave])
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
        for archivo in sorted((_memoria(nombre, p) / "decisiones").glob("ADR-*.md")):
            meta, _ = _leer_registro(archivo)
            fecha, estado = _fecha(meta), meta.get("estado", "")
            if fecha and fecha >= desde.date():
                conteo[estado] += 1
            abiertas += estado == "propuesta"
            if estado == "propuesta" and fecha and fecha < limite_vieja:
                viejas.append(f"  {nombre} {meta.get('id', archivo.stem)} {fecha.isoformat()} {meta.get('titulo', '')}")
        por_proyecto[nombre] = conteo
    lineas = ["- Decisiones creadas en el período (según la memoria): "
              + ("; ".join(f"{n}: " + " · ".join(f"{e} {c[e]}" for e in ESTADOS_DECISION)
                           for n, c in por_proyecto.items()) or "ninguna")]
    lineas.append(f"- Propuestas abiertas hoy: {abiertas} · con más de {DIAS_PROPUESTA_VIEJA} días: {len(viejas)}")
    return lineas + viejas


def tamano_contexto(filas: list[dict]) -> list[str]:
    """ADR-026: tamaño de la respuesta de obtener_contexto por proyecto (p50/máx en caracteres y ~tokens = /4)."""
    por = defaultdict(list)
    for f in filas:
        if f["herramienta"] == "obtener_contexto":
            por[f.get("proyecto")].append(f["resp_chars"])
    lineas = []
    for nombre, tam in sorted(por.items(), key=lambda kv: str(kv[0])):
        tam.sort()
        p50, maximo = percentil(tam, 0.5), tam[-1]
        aviso = f"  ⚠ > {TOKENS_ARRANQUE:,} tokens" if p50 / 4 > TOKENS_ARRANQUE else ""
        lineas.append(f"  {nombre}: p50 {p50} caracteres (~{p50 // 4} tokens) · máx {maximo} (~{maximo // 4} tokens) "
                      f"· {len(tam)} llamadas{aviso}")
    return lineas


def _fecha_integracion(meta: dict, cuerpo: str) -> str:
    """Fecha de "### AAAA-MM-DD · integrada" en el Resultado (la última); si no está, `actualizada` o `fecha`."""
    fechas = re.findall(r"^### (\d{4}-\d{2}-\d{2}) · integrada\b", cuerpo, re.M)
    return fechas[-1] if fechas else meta.get("actualizada") or meta.get("fecha", "?")


def _menciones(cuerpo: str) -> tuple[set, set]:
    """Ids P-NNN del texto de una tarea, separados en (spec, resultado). Spec: todo fuera de "## Resultado" (título,
    Objetivo, Criterios, Decisiones, Archivos) más los bloques "### Revisión N" del Resultado. Se excluyen Fuera de
    alcance, Notas, Cómo verificar y Resuelve (lo declarado va aparte)."""
    spec, resultado = set(), set()
    seccion, revision = "", False
    for linea in cuerpo.splitlines():
        if linea.startswith("## "):
            seccion, revision = linea[3:].strip(), False
        elif linea.startswith("### ") and seccion == "Resultado":
            revision = linea[4:].startswith("Revisión")
        if seccion in SECCIONES_EXCLUIDAS:
            continue
        destino = resultado if seccion == "Resultado" and not revision else spec
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
        for archivo in (mem / "pendientes").glob("P-*.md"):
            meta, _ = _leer_registro(archivo)
            if meta.get("estado") == "abierta":
                abiertos.add(_normalizar_id(meta.get("id") or archivo.stem))
        grupos = {"declarados en resuelve": defaultdict(list), "mencionados en la spec": defaultdict(list),
                  "mencionados en el Resultado": defaultdict(list)}
        for archivo in (mem / "tareas").glob("T-*.md"):
            meta, cuerpo = _leer_registro(archivo)
            if meta.get("estado") != "integrada":
                continue
            id_tarea = _normalizar_id(meta.get("id") or re.match(r"T-\d+", archivo.name).group(0))
            ref = (id_tarea, _fecha_integracion(meta, cuerpo))
            spec, resultado = _menciones(cuerpo)
            for clave, ids in (("declarados en resuelve", {i for i, _ in _ids_resuelve(meta.get("resuelve", ""))}),
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--proyecto")
    ap.add_argument("--log", help="ruta del log (por defecto MEMORIA_PROYECTOS_LOG o logs/uso.jsonl)")
    a = ap.parse_args()
    log = ruta_log(a.log)
    if not log.is_file():
        print(f"No existe el log de uso: {log}", file=sys.stderr)
        sys.exit(1)
    desde = dt.datetime.now() - dt.timedelta(days=a.dias)
    filas = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    primera = min((dt.datetime.fromisoformat(f["ts"]) for f in filas), default=None)
    filas = [f for f in filas if dt.datetime.fromisoformat(f["ts"]) >= desde
             and (not a.proyecto or f.get("proyecto") == a.proyecto)]
    if not filas:
        print("Sin llamadas en el período.")
        return

    print(f"Período: últimos {a.dias} días · {len(filas)} llamadas\n")
    por = defaultdict(list)
    for f in filas:
        por[f["herramienta"]].append(f)
    print(f"{'herramienta':<22}{'llamadas':>9}{'errores':>9}{'tokens resp. (prom)':>21}{'ms (p95)':>10}")
    for nombre, fs in sorted(por.items(), key=lambda kv: -len(kv[1])):
        p95 = percentil(sorted(f["ms"] for f in fs), 0.95)
        prom = sum(f["resp_chars"] for f in fs) / len(fs) / 4
        print(f"{nombre:<22}{len(fs):>9}{sum(f['error'] for f in fs):>9}{prom:>21.0f}{p95:>10.0f}")

    print("\nTamaño de respuesta por herramienta (caracteres)")
    print(f"{'herramienta':<22}{'p50':>9}{'p90':>9}{'máx':>9}")
    for nombre, fs in sorted(por.items(), key=lambda kv: -len(kv[1])):
        tam = sorted(f["resp_chars"] for f in fs)
        print(f"{nombre:<22}{percentil(tam, 0.5):>9}{percentil(tam, 0.9):>9}{tam[-1]:>9}")
    print("\nRespuestas más grandes")
    for f in sorted(filas, key=lambda f: (-f["resp_chars"], f["ts"]))[:5]:
        print(f"  {f['ts']} {f['herramienta']} [{f.get('proyecto')}] {f['resp_chars']} caracteres"
              + (f" · {f.get('ruta') or f.get('carpeta')}" if f.get("ruta") or f.get("carpeta") else ""))

    print("\nIndicadores")
    ctx = por.get("obtener_contexto", [])
    if ctx:
        print(f"- Costo de arranque por chat: ~{sum(f['resp_chars'] for f in ctx) / len(ctx) / 4:.0f} tokens "
              f"(objetivo < 2000). Chats iniciados: {len(ctx)}")
    tamanos = tamano_contexto(filas)
    if tamanos:
        print(f"- Tamaño de obtener_contexto por proyecto (referencia {TOKENS_ARRANQUE:,} tokens = "
              f"{TOKENS_ARRANQUE * 4:,} caracteres; aviso si el p50 la supera):")
        for linea in tamanos:
            print(linea)
    lecturas = por.get("leer_documento", [])
    busquedas = por.get("buscar", [])
    if lecturas or busquedas:
        print(f"- Lecturas: {len(lecturas)} vs búsquedas: {len(busquedas)}. "
              "Muchas lecturas y pocas búsquedas = se está gastando contexto de más.")
        codigo = defaultdict(lambda: [0, 0])
        for f in lecturas:
            if Path(f.get("ruta") or "").suffix.lower() in EXT_CODIGO:
                codigo[f.get("proyecto")][0] += 1
                codigo[f.get("proyecto")][1] += f["resp_chars"]
        print("- Lecturas de código con leer_documento: "
              + (", ".join(f"{p}: {n} ({c} caracteres)" for p, (n, c) in sorted(codigo.items(), key=lambda kv: -kv[1][1]))
                 or "ninguna"))
        vacias = sum(1 for f in busquedas if f.get("resultados") == 0)
        if busquedas:
            print(f"- Búsquedas sin resultado: {vacias}/{len(busquedas)}")
        top = Counter(f.get("ruta") for f in lecturas).most_common(5)
        if top:
            print("- Documentos más leídos: " + ", ".join(f"{r} ×{n}" for r, n in top))
    sesiones, indices = len(por.get("registrar_sesion", [])), len(por.get("actualizar_indice", []))
    print(f"- Cierres de sesión: {sesiones} · regeneraciones de INDEX: {indices} "
          f"{'(nunca se usa /cierre: INDEX se queda viejo)' if ctx and not indices else ''}")
    for linea in indicador_decisiones(desde, a.proyecto):
        print(linea)
    creaciones = [f for nombre in ("registrar_decision", "registrar_pendiente", "registrar_tarea")
                  for f in por.get(nombre, [])]
    duplicados = sum(1 for f in creaciones if f.get("duplicado"))
    if creaciones:
        print(f"- Creaciones idempotentes (ADR-019): {len(creaciones)} llamadas · duplicados detectados "
              f"(reintento sin efecto): {duplicados}")
    internos = [f for f in filas if f["error"] and f.get("tipo_error") == "interno"]
    rechazos = [f for f in filas if f["error"] and f.get("tipo_error") != "interno"]
    tasa = len(internos) / len(filas) * 100
    print(f"- Fallas internas del servidor: {len(internos)} ({tasa:.2f} %) · rechazos de validación: {len(rechazos)} "
          "(uso esperado: p. ej. confirmar sin cita o un nombre inválido)")
    dias = {f["ts"][:10] for f in filas}
    # ADR-009: "14 días consecutivos de telemetría" = la telemetría cubre todo el período (días corridos desde el
    # primer registro), no 14 días con uso; un día sin llamadas no rompe la ventana.
    corridos = (dt.datetime.now() - primera).days if primera else 0
    cumple = len(filas) >= 300 and tasa < 1 and a.dias >= 14 and corridos >= 14
    print(f"- ADR-009 criterio 2 (≥300 llamadas, <1 % de fallas internas, 14 días corridos de telemetría): "
          f"{len(filas)} llamadas · {corridos} días corridos desde el primer registro · {len(dias)} días con uso "
          f"→ {'CUMPLE' if cumple else 'aún no'}")
    print("\nPendientes abiertos referenciados por tareas integradas")
    for linea in higiene_pendientes(a.proyecto):
        print(linea)
    errores = internos + rechazos
    if errores:
        print("\nÚltimos errores")
        for f in sorted(errores, key=lambda f: f["ts"])[-5:]:
            print(f"  {f['ts']} [{f.get('tipo_error', 'validacion')}] {f['herramienta']}: {f.get('detalle', '')}")


if __name__ == "__main__":
    main()
