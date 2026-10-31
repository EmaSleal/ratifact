"""`ratifact report [--days N] [--project P] [--log RUTA]` (antes analizar_uso.py, que queda como envoltorio hasta 1.1):
resumen del uso a partir del log de telemetría.

Log: --log, si no RATIFACT_LOG (o MEMORIA_PROYECTOS_LOG, respaldo hasta 1.1), si no $XDG_STATE_HOME/ratifact/uso.jsonl
(el mismo que escribe el servidor). Las herramientas se agregan por su nombre inglés (contrato v1, T-011): las filas
viejas con el nombre en español se traducen con HERRAMIENTAS_V0, así el historial sigue sumando por herramienta.
Tokens estimados = caracteres / 4 (aproximación; el texto en español suele rondar 3,5–4,5).
Los indicadores que salen de las memorias (decisiones, higiene de pendientes) están en ratifact.informe_memoria."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ratifact.config import _entorno
from ratifact.informe_memoria import higiene_pendientes, indicador_decisiones, indicador_delegacion
from ratifact.rutas import log_por_defecto
from ratifact.vocabulario import HERRAMIENTAS_V0

TOKENS_ARRANQUE = 2000   # ADR-026: referencia de get_context (~8.000 caracteres)
EXT_CODIGO = {".java", ".py", ".ts", ".js", ".vue", ".sql", ".xml", ".yml", ".yaml", ".kt"}


def percentil(valores: list, q: float):
    """Percentil por rango más cercano sobre `valores` ordenados (el mismo criterio que el p95 de ms)."""
    return valores[min(len(valores) - 1, int(len(valores) * q))]


def ruta_log(argumento: str | None) -> Path:
    """--log gana sobre RATIFACT_LOG / MEMORIA_PROYECTOS_LOG, que ganan sobre la ruta por defecto (en cada llamada)."""
    return Path(argumento or _entorno("LOG") or log_por_defecto())


def herramienta(fila: dict) -> str:
    """Nombre inglés de la herramienta de una fila (las filas anteriores a T-011 traen el nombre en español)."""
    return HERRAMIENTAS_V0.get(fila["herramienta"], fila["herramienta"])


def tamano_contexto(filas: list[dict]) -> list[str]:
    """ADR-026: tamaño de la respuesta de get_context por proyecto (p50/máx en caracteres y ~tokens = /4)."""
    por = defaultdict(list)
    for f in filas:
        if herramienta(f) == "get_context":
            por[f.get("proyecto")].append(f["resp_chars"])
    lineas = []
    for nombre, tam in sorted(por.items(), key=lambda kv: str(kv[0])):
        tam.sort()
        p50, maximo = percentil(tam, 0.5), tam[-1]
        aviso = f"  ⚠ > {TOKENS_ARRANQUE:,} tokens" if p50 / 4 > TOKENS_ARRANQUE else ""
        lineas.append(f"  {nombre}: p50 {p50} caracteres (~{p50 // 4} tokens) · máx {maximo} (~{maximo // 4} tokens) "
                      f"· {len(tam)} llamadas{aviso}")
    return lineas


def usos_alias(filas: list[dict]) -> list[str]:
    """Rutas v1 traducidas por el alias (`alias_ruta` en la telemetría), por proyecto: cuando quede en cero se quita
    el alias en 1.1 (junto con el esquema.json centinela, ADR-030)."""
    por = defaultdict(Counter)
    for f in filas:
        if f.get("alias_ruta"):
            por[f.get("proyecto")][f["alias_ruta"]] += 1
    return [f"  {nombre}: {sum(c.values())} usos · " + ", ".join(f"{r} ×{n}" for r, n in c.most_common(3))
            for nombre, c in sorted(por.items(), key=lambda kv: str(kv[0]))]


def argumentos(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Opciones de `ratifact report` (los nombres en español de analizar_uso.py siguen valiendo hasta 1.1)."""
    ap.add_argument("--days", "--dias", dest="dias", type=int, default=7, help="period in days (default 7)")
    ap.add_argument("--project", "--proyecto", dest="proyecto", help="only this project")
    ap.add_argument("--log", help="log path (default RATIFACT_LOG, MEMORIA_PROYECTOS_LOG or "
                                  "$XDG_STATE_HOME/ratifact/uso.jsonl)")
    return ap


def main(argv: list[str] | None = None, a: argparse.Namespace | None = None) -> None:
    a = a or argumentos(argparse.ArgumentParser(prog="ratifact report")).parse_args(argv)
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
        por[herramienta(f)].append(f)
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
        print(f"  {f['ts']} {herramienta(f)} [{f.get('proyecto')}] {f['resp_chars']} caracteres"
              + (f" · {f.get('ruta') or f.get('carpeta')}" if f.get("ruta") or f.get("carpeta") else ""))

    print("\nIndicadores")
    ctx = por.get("get_context", [])
    if ctx:
        print(f"- Costo de arranque por chat: ~{sum(f['resp_chars'] for f in ctx) / len(ctx) / 4:.0f} tokens "
              f"(objetivo < 2000). Chats iniciados: {len(ctx)}")
    tamanos = tamano_contexto(filas)
    if tamanos:
        print(f"- Tamaño de get_context por proyecto (referencia {TOKENS_ARRANQUE:,} tokens = "
              f"{TOKENS_ARRANQUE * 4:,} caracteres; aviso si el p50 la supera):")
        for linea in tamanos:
            print(linea)
    lecturas = por.get("read_document", [])
    busquedas = por.get("search", [])
    if lecturas or busquedas:
        print(f"- Lecturas: {len(lecturas)} vs búsquedas: {len(busquedas)}. "
              "Muchas lecturas y pocas búsquedas = se está gastando contexto de más.")
        codigo = defaultdict(lambda: [0, 0])
        for f in lecturas:
            if Path(f.get("ruta") or "").suffix.lower() in EXT_CODIGO:
                codigo[f.get("proyecto")][0] += 1
                codigo[f.get("proyecto")][1] += f["resp_chars"]
        print("- Lecturas de código con read_document: "
              + (", ".join(f"{p}: {n} ({c} caracteres)" for p, (n, c) in sorted(codigo.items(), key=lambda kv: -kv[1][1]))
                 or "ninguna"))
        vacias = sum(1 for f in busquedas if f.get("resultados") == 0)
        if busquedas:
            print(f"- Búsquedas sin resultado: {vacias}/{len(busquedas)}")
        top = Counter(f.get("ruta") for f in lecturas).most_common(5)
        if top:
            print("- Documentos más leídos: " + ", ".join(f"{r} ×{n}" for r, n in top))
    sesiones, indices = len(por.get("log_session", [])), len(por.get("update_index", []))
    print(f"- Cierres de sesión: {sesiones} · regeneraciones de INDEX: {indices} "
          f"{'(nunca se usa el prompt close: INDEX se queda viejo)' if ctx and not indices else ''}")
    for linea in indicador_decisiones(desde, a.proyecto):
        print(linea)
    creaciones = [f for nombre in ("propose_decision", "add_pending", "create_task")
                  for f in por.get(nombre, [])]
    duplicados = sum(1 for f in creaciones if f.get("duplicado"))
    if creaciones:
        print(f"- Creaciones idempotentes: {len(creaciones)} llamadas · duplicados detectados "
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
    print(f"- Criterio de uso real de 1.0 (≥300 llamadas, <1 % de fallas internas, 14 días corridos de telemetría): "
          f"{len(filas)} llamadas · {corridos} días corridos desde el primer registro · {len(dias)} días con uso "
          f"→ {'CUMPLE' if cumple else 'aún no'}")
    alias = usos_alias(filas)
    print("- Rutas v1 traducidas (alias, se quita en 1.1): " + ("ninguna" if not alias else ""))
    for linea in alias:
        print(linea)
    print("\nDelegación: tareas con `routing:` cambiadas en el período")
    for linea in indicador_delegacion(desde, a.proyecto):
        print(linea)
    print("\nPendientes abiertos referenciados por tareas integradas")
    for linea in higiene_pendientes(a.proyecto):
        print(linea)
    errores = internos + rechazos
    if errores:
        print("\nÚltimos errores")
        for f in sorted(errores, key=lambda f: f["ts"])[-5:]:
            print(f"  {f['ts']} [{f.get('tipo_error', 'validacion')}] {herramienta(f)}: {f.get('detalle', '')}")
