#!/usr/bin/env python3
"""Resumen del uso de memoria-proyectos a partir de logs/uso.jsonl.

Uso:  python3 analizar_uso.py [--dias N] [--proyecto game] [--log RUTA]
Log: --log, si no MEMORIA_PROYECTOS_LOG, si no <repo>/logs/uso.jsonl (el mismo que escribe el servidor).
Tokens estimados = caracteres / 4 (aproximación; el texto en español suele rondar 3,5–4,5).
"""
import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

LOG_POR_DEFECTO = Path(__file__).resolve().parent / "logs" / "uso.jsonl"   # igual que LOG_USO del servidor


def ruta_log(argumento: str | None) -> Path:
    """--log gana sobre MEMORIA_PROYECTOS_LOG, que gana sobre la ruta por defecto (resuelto en cada llamada)."""
    return Path(argumento or os.environ.get("MEMORIA_PROYECTOS_LOG") or LOG_POR_DEFECTO)


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
        ms = sorted(f["ms"] for f in fs)
        p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
        prom = sum(f["resp_chars"] for f in fs) / len(fs) / 4
        print(f"{nombre:<22}{len(fs):>9}{sum(f['error'] for f in fs):>9}{prom:>21.0f}{p95:>10.0f}")

    print("\nIndicadores")
    ctx = por.get("obtener_contexto", [])
    if ctx:
        print(f"- Costo de arranque por chat: ~{sum(f['resp_chars'] for f in ctx) / len(ctx) / 4:.0f} tokens "
              f"(objetivo < 2000). Chats iniciados: {len(ctx)}")
    lecturas = por.get("leer_documento", [])
    busquedas = por.get("buscar", [])
    if lecturas or busquedas:
        completas = [f for f in lecturas if f.get("params", {}).get("desde_linea", 1) <= 1
                     and not f.get("params", {}).get("hasta_linea", 0)]
        print(f"- Lecturas: {len(lecturas)} ({len(completas)} sin rango) vs búsquedas: {len(busquedas)}. "
              "Muchas lecturas completas y pocas búsquedas = se está gastando contexto de más.")
        vacias = sum(1 for f in busquedas if f.get("resultados") == 0)
        if busquedas:
            print(f"- Búsquedas sin resultado: {vacias}/{len(busquedas)}")
        top = Counter(f.get("ruta") for f in lecturas).most_common(5)
        if top:
            print("- Documentos más leídos: " + ", ".join(f"{r} ×{n}" for r, n in top))
    sesiones, indices = len(por.get("registrar_sesion", [])), len(por.get("actualizar_indice", []))
    print(f"- Cierres de sesión: {sesiones} · regeneraciones de INDEX: {indices} "
          f"{'(nunca se usa /cierre: INDEX se queda viejo)' if ctx and not indices else ''}")
    dec, conf = por.get("registrar_decision", []), por.get("confirmar_decision", [])
    if dec or conf:
        print(f"- Decisiones propuestas: {len(dec)} · confirmadas por el usuario: "
              f"{sum(1 for f in conf if not f['error'])} · confirmaciones con error: "
              f"{sum(1 for f in conf if f['error'])}")
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
    cumple = len(filas) >= 300 and tasa < 1 and len(dias) >= min(a.dias, 14)
    print(f"- ADR-009 criterio 2 (≥300 llamadas, <1 % de fallas internas, 14 días): "
          f"{len(filas)} llamadas en {len(dias)} días con uso → {'CUMPLE' if cumple else 'aún no'}")
    errores = internos + rechazos
    if errores:
        print("\nÚltimos errores")
        for f in sorted(errores, key=lambda f: f["ts"])[-5:]:
            print(f"  {f['ts']} [{f.get('tipo_error', 'validacion')}] {f['herramienta']}: {f.get('detalle', '')}")


if __name__ == "__main__":
    main()
