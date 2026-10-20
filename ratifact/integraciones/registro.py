"""Registro de integraciones opcionales (ADR-024, ADR-025): cuáles están activas en un proyecto (configuración de
projects.json + señales en disco, leídas en cada llamada: sin caché ni watcher) y la guía que recibe el agente.

Agregar una integración = agregar su módulo en este paquete y sumarla a INTEGRACIONES."""
from __future__ import annotations

from pathlib import Path

from ratifact.config import ErrorMemoria, _proyectos, _raiz, _repos_de
from ratifact.integraciones import codegraph, engram, gentle_ai
from ratifact.integraciones.base import FASES, Integracion

INTEGRACIONES: tuple[Integracion, ...] = (codegraph.INTEGRACION, gentle_ai.INTEGRACION, engram.INTEGRACION)
VALORES = ("auto", "off")
FASES_EJECUCION = FASES[1:]          # execute, verify, close: lo que recibe update_task(..., "in_progress")


def _nombres() -> str:
    return ", ".join(i.nombre for i in INTEGRACIONES)


def _detectada(integ: Integracion, raiz: Path) -> bool:
    """Señal en la raíz del proyecto o, en proyectos de varios repos, en cualquiera de sus repos."""
    if integ.detectar is None or not raiz.is_dir():
        return False
    return integ.detectar(raiz) or any(integ.detectar(raiz / r) for r in _repos_de(raiz))


def _activas(proyecto: str) -> list[tuple[Integracion, bool]]:
    """(integración, detectada) de las que no están en 'off': las de proyecto solo si se detectan; las de
    usuario siempre (nunca se detectan: su guía es condicional)."""
    config = _proyectos().get(proyecto, {}).get("integraciones") or {}
    if not isinstance(config, dict):
        config = {}
    raiz = _raiz(proyecto, verificar_existe=False)
    salida = []
    for i in INTEGRACIONES:
        if config.get(i.nombre) == "off":
            continue
        if i.alcance == "user":
            salida.append((i, False))
        elif _detectada(i, raiz):
            salida.append((i, True))
    return salida


def _linea(activas: list[tuple[Integracion, bool]]) -> str:
    detectadas = ", ".join(f"{i.nombre} (detected)" for i, d in activas if d)
    usuario = ", ".join(f"{i.nombre} (if available)" for i, d in activas if i.alcance == "user")
    partes = [p for p in (detectadas, usuario) if p]
    return "Integrations: " + " · ".join(partes) if partes else ""


def _linea_integraciones(proyecto: str) -> str:
    """La línea de integraciones detectadas (registrar_tarea). Vacía si todas están apagadas."""
    return _linea(_activas(proyecto))


def _bloque_contexto(proyecto: str) -> str:
    """obtener_contexto: la línea de integraciones y una línea `planificar` por integración activa que la tenga."""
    activas = _activas(proyecto)
    lineas = [_linea(activas)] if activas else []
    lineas += [f"- {i.nombre} · plan: {i.guia['plan']} Boundary: {i.limite}."
               for i, _ in activas if "plan" in i.guia]
    return "\n".join(lineas)


def _guia_en_curso(proyecto: str) -> str:
    """actualizar_tarea(..., "in_progress"): guía completa de ejecutar, verificar y cerrar, calculada en ese momento."""
    lineas = []
    for i, detectada in _activas(proyecto):
        fases = [f for f in FASES_EJECUCION if f in i.guia]
        if not fases:
            continue
        lineas.append(f"- {i.nombre} ({'detected' if detectada else 'if available'}) — {i.rol}; "
                      f"boundary: {i.limite}.")
        lineas += [f"  · {f}: {i.guia[f]}" for f in fases]
    if not lineas:
        return ""
    return "Integration guidance (computed now; follow it only if you have those tools):\n" + "\n".join(lineas)


def _parsear_integraciones(texto: str, actual: dict | None) -> tuple[dict, str]:
    """"codegraph=off,gentle-ai=auto" → configuración nueva (las 'auto' se omiten) y la descripción del cambio."""
    validas = f"Valid: {_nombres()}."
    conocidas = {i.nombre for i in INTEGRACIONES}
    nuevo = dict(actual) if isinstance(actual, dict) else {}
    pares = []
    for item in (x.strip() for x in texto.split(",")):
        if not item:
            continue
        nombre, separador, valor = item.partition("=")
        nombre, valor = nombre.strip().lower(), valor.strip().lower()
        if not separador or not nombre:
            raise ErrorMemoria("Format of `integrations`: name=auto|off separated by commas "
                               f"(e.g. \"codegraph=off,gentle-ai=auto\"). {validas}")
        if nombre not in conocidas:
            raise ErrorMemoria(f"Unknown integration '{nombre}'. {validas}")
        if valor not in VALORES:
            raise ErrorMemoria(f"Invalid value '{valor}' for '{nombre}': use {', '.join(VALORES)}. {validas}")
        if valor == "auto":
            nuevo.pop(nombre, None)
        else:
            nuevo[nombre] = valor
        pares.append(f"{nombre}={valor}")
    if not pares:
        raise ErrorMemoria(f"Empty `integrations`: use name=auto|off separated by commas. {validas}")
    return nuevo, ", ".join(pares)
