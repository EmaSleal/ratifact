"""Catálogo de la memoria (ADR-022): id, tipo, título, estado y ruta de cada registro de .project/decisiones,
pendientes y tareas, leído del frontmatter en cada llamada. No se guarda nada en disco: sin índice, sin caché, sin
watcher. Alimenta la resolución de ids de leer_documento, el listado de registros y los resultados de buscar."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import NamedTuple

from ratifact.config import MEM, ErrorMemoria, _mem
from ratifact.registros import _buscar_registro, _clave_id, _leer_registro, _normalizar_id

# prefijo del id → (carpeta de la memoria, tipo)
TIPOS = {"ADR": ("decisiones", "decision"), "P": ("pendientes", "pendiente"), "T": ("tareas", "tarea")}
CARPETAS = {carpeta: prefijo for prefijo, (carpeta, _) in TIPOS.items()}


class Registro(NamedTuple):
    id: str
    tipo: str
    titulo: str
    estado: str
    ruta: str        # relativa al proyecto: ".project/<carpeta>/<archivo>"


def _registros_de(mem: Path, prefijo: str) -> list[Registro]:
    carpeta, tipo = TIPOS[prefijo]
    d = mem / carpeta
    filas = []
    for p in sorted(d.glob(f"{prefijo}-*.md"), key=lambda a: _clave_id(a.name)) if d.is_dir() else []:
        if not re.match(rf"{prefijo}-\d+", p.name):
            continue
        meta, _ = _leer_registro(p)
        id_ = _normalizar_id(meta.get("id") or re.match(rf"{prefijo}-\d+", p.name).group(0))
        filas.append(Registro(id_, tipo, meta.get("titulo") or meta.get("tema", ""), meta.get("estado", ""),
                              f"{MEM}/{carpeta}/{p.name}"))
    return filas


def _catalogo(proyecto: str) -> list[Registro]:
    """Todos los registros del proyecto (decisiones, pendientes, tareas), cada tipo en orden numérico de id."""
    mem = _mem(proyecto)
    return [r for prefijo in TIPOS for r in _registros_de(mem, prefijo)]


def _linea(r: Registro, separador: str = " ") -> str:
    return f"{r.id} · {r.estado} · {r.titulo}{separador}({r.ruta})"


def _id_de_ruta(ruta: str) -> str | None:
    """Id que se pidió con una ruta que no existe: "T-24", "T-024.md", "tareas/T-024.md", ".project/tareas/T-024.md",
    ".project/decisiones/ADR-020-<slug equivocado>.md". Solo si el resto de la ruta apunta a la memoria (nada, una
    carpeta de registros, .project o .project/<carpeta de registros>) y el prefijo es de un tipo conocido; así una ruta
    de código como "docs/T-001.md" o "src/T-1.java" nunca se resuelve a un registro."""
    partes = Path(ruta.strip()).parts
    if not partes:
        return None
    padre = partes[:-1]
    if padre and padre[0] == MEM:
        padre = padre[1:]
    if len(padre) > 1 or (padre and padre[0] not in CARPETAS):
        return None
    m = re.fullmatch(r"([A-Za-z]+-\d+)(-[^/]*)?(\.md)?", partes[-1])
    id_ = _normalizar_id(m.group(1)) if m else ""
    return id_ if id_.split("-")[0] in TIPOS else None


def _resolver_id(proyecto: str, ruta: str) -> Path | None:
    """Archivo real del registro al que se refiere `ruta` (que no existe), o None si `ruta` no tiene forma de id.
    Solo lee, y solo dentro de la carpeta de memoria. Id desconocido → ErrorMemoria con el último id de su tipo."""
    id_ = _id_de_ruta(ruta)
    if id_ is None:
        return None
    prefijo = id_.split("-")[0]
    mem = _mem(proyecto)
    carpeta = mem / TIPOS[prefijo][0]
    try:
        return _buscar_registro(carpeta, id_)
    except ErrorMemoria:
        existentes = _registros_de(mem, prefijo)
        if not existentes:
            raise ErrorMemoria(f"No existe {id_}; todavía no hay registros en {MEM}/{TIPOS[prefijo][0]}.")
        raise ErrorMemoria(f"No existe {id_}; el último es {existentes[-1].id}.")


def _es_carpeta_de_registros(carpeta: str) -> str | None:
    """Prefijo si `carpeta` es .project/decisiones|pendientes|tareas (con o sin "/" final)."""
    partes = Path(carpeta.strip()).parts
    return CARPETAS.get(partes[1]) if len(partes) == 2 and partes[0] == MEM else None


def _registros_en(proyecto: str, prefijo: str) -> list[Registro]:
    return _registros_de(_mem(proyecto), prefijo)


TOPE_TITULOS = 5   # coincidencias por título que buscar muestra (el id exacto no cuenta)


def _plano(texto: str) -> str:
    """Sin acentos ni mayúsculas, para comparar títulos: "Navegación" → "navegacion"."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).casefold()


def _coincidencias(proyecto: str, texto: str) -> tuple[list[Registro], int]:
    """Registros para buscar: primero el cuyo id es `texto` (en cualquier forma que acepte _normalizar_id), luego hasta
    TOPE_TITULOS cuyo título contiene `texto` al inicio de una palabra (sin distinguir mayúsculas ni acentos: "id" no
    coincide con "híbrido"; "asiento" sí con "Asientos"). Devuelve también cuántos títulos quedaron fuera del tope."""
    buscado = _plano(texto.strip())
    if not buscado:
        return [], 0
    objetivo = _normalizar_id(texto)
    patron = re.compile(rf"(?<!\w){re.escape(buscado)}")
    filas = _catalogo(proyecto)
    exactos = [r for r in filas if r.id == objetivo]
    titulos = [r for r in filas if r.id != objetivo and patron.search(_plano(r.titulo))]
    return exactos + titulos[:TOPE_TITULOS], max(len(titulos) - TOPE_TITULOS, 0)
