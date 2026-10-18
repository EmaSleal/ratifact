"""Descriptor de una integración opcional (ADR-024): qué es, cómo se detecta y qué guía aporta por fase."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

FASES = ("planificar", "ejecutar", "verificar", "cerrar")


@dataclass(frozen=True)
class Integracion:
    nombre: str
    alcance: str                                   # "proyecto" (se detecta en disco) | "usuario" (nunca se detecta)
    prefijo: str                                   # prefijo de sus herramientas, p. ej. "codegraph_"
    rol: str
    limite: str                                    # frontera: nunca decisiones ni estado de tareas
    guia: dict[str, str] = field(default_factory=dict)   # fase → texto, siempre condicional ("si tienes …; si no, …")
    detectar: Callable[[Path], bool] | None = None       # solo alcance proyecto: ¿hay señal en esta carpeta?


def carpeta_existe(nombre: str) -> Callable[[Path], bool]:
    """Detector de señal en disco: la carpeta `nombre` existe en la raíz dada (se lee en cada llamada)."""
    return lambda raiz: (raiz / nombre).is_dir()
