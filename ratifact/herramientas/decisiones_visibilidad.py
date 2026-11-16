"""Renderiza la edad y el estado actual de decisiones citadas por las herramientas."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from ratifact import registros as _registros
from ratifact.config import ErrorMemoria, _mem
from ratifact.registros import _buscar_registro, _clave_id, _leer_registro, _normalizar_id
from ratifact.vocabulario import DECISIONES

UMBRAL_ANTIGUEDAD_PROPUESTA_DIAS = 14
MAX_PROPUESTAS_ANTIGUAS_A_DECIDIR = 3


def _propuestas_con_antiguedad(mem: Path) -> list[tuple[str, _dt.date | None]]:
    """Devuelve propuestas de más antiguas a más nuevas; las fechas inválidas quedan al final."""
    propuestas = []
    for ruta in (mem / DECISIONES).glob("ADR-*.md"):
        meta, _ = _leer_registro(ruta)
        if meta.get("status") != "proposed":
            continue
        id_ = "-".join(ruta.stem.split("-", 2)[:2])
        try:
            fecha = _dt.date.fromisoformat(str(meta.get("date", "")))
        except ValueError:
            fecha = None
        propuestas.append((id_, fecha))
    return sorted(propuestas, key=lambda p: (p[1] is None, p[1] or _dt.date.max, _clave_id(p[0])))


def _linea_propuestas(mem: Path) -> str:
    """Renderiza edad y sugerencia de decisión por lote sin alterar los ADR."""
    propuestas = _propuestas_con_antiguedad(mem)
    if not propuestas:
        return ""
    hoy = _registros._ahora().date()
    elementos, antiguas = [], []
    for id_, fecha in propuestas:
        if fecha is None or fecha > hoy:
            elementos.append(id_)
            continue
        dias = (hoy - fecha).days
        elementos.append(f"{id_} ({'today' if dias == 0 else f'{dias} d'})")
        if dias >= UMBRAL_ANTIGUEDAD_PROPUESTA_DIAS:
            antiguas.append(id_)
    linea = "Proposed decisions awaiting the user's acceptance: " + ", ".join(elementos)
    if antiguas:
        lote = ", ".join(antiguas[:MAX_PROPUESTAS_ANTIGUAS_A_DECIDIR])
        cantidad = len(antiguas[:MAX_PROPUESTAS_ANTIGUAS_A_DECIDIR])
        if cantidad == 1:
            linea += f"\nOffer the user to decide the oldest proposal: {lote}"
        else:
            linea += f"\nOffer the user to decide the {cantidad} oldest proposals: {lote}"
    return linea


def _avisos_decisiones(proyecto: str, decisiones: str) -> str:
    """Informa estados no aceptados sin cambiar el formato guardado en la tarea."""
    avisos = []
    for id_ in decisiones.split(", ") if decisiones else ():
        meta, _ = _leer_registro(_buscar_registro(_mem(proyecto) / DECISIONES, id_))
        estado = meta.get("status", "unknown")
        if estado == "accepted":
            continue
        if estado == "proposed":
            avisos.append(f"⚠ {id_} is proposed; the coding agent will treat it as a reference, not as a rule. "
                          "Accept it before starting or clarify in the task notes how to treat it.")
        elif estado == "superseded":
            reemplazo = meta.get("superseded_by", "")
            if reemplazo:
                try:
                    reemplazo = _normalizar_id(reemplazo)
                except ErrorMemoria:
                    pass
                avisos.append(f"⚠ {id_} is superseded by {reemplazo}; do not treat it as current guidance.")
            else:
                avisos.append(f"⚠ {id_} is superseded; do not treat it as current guidance.")
        else:
            avisos.append(f"⚠ {id_} is {estado}; it is not applicable as current guidance and must not be treated as a rule.")
    return "\n".join(avisos)
