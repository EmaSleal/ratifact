"""Herramientas de pendientes (registrar_pendiente, cerrar_pendiente) y bitácora de sesiones (registrar_sesion)."""
from __future__ import annotations

from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, herramienta
from ratifact.config import _mem
from ratifact.esquema import _bloqueo
from ratifact.registros import (_buscar_registro, _commit, _duplicado_reciente, _escribir_atomico, _escribir_registro,
                                _hoy, _leer_registro, _mensaje_duplicado, _regenerar_vistas, _siguiente_id, _slug)


@herramienta
def registrar_pendiente(proyecto: str, tema: str, contexto: str, dueno: str = "") -> str:
    """Registra una decisión abierta o tema sin resolver. Idempotente (ADR-019): si ya hay un pendiente con
    este tema (sin distinguir mayúsculas ni espacios) creado en los últimos minutos Y TODAVÍA en estado
    'abierta', no crea nada nuevo y devuelve el id existente. Si ese pendiente ya se cerró, un humano ya
    intervino, así que se registra un pendiente nuevo."""
    def f():
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / "pendientes"
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "P", "tema", tema, "abierta")
            if dup:
                return _mensaje_duplicado(dup["id"])
            id_ = _siguiente_id(carpeta, "P")
            ruta = carpeta / f"{id_}-{_slug(tema)}.md"
            meta = {"id": id_, "tema": tema, "estado": "abierta", "fecha": _hoy(),
                    "creado": _registros._ahora().isoformat(timespec="seconds")}
            if dueno:
                meta["dueno"] = dueno
            _escribir_registro(ruta, meta, contexto)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{id_} {tema}")
            return f"{id_} registrado · commit {sha}"
    return _ejecutar(f)


@herramienta
def cerrar_pendiente(proyecto: str, id: str, resolucion: str, id_decision: str = "") -> str:
    """Cierra un pendiente. Si la resolución generó una decisión, indica su id_decision."""
    def f():
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / "pendientes", id)
            meta, cuerpo = _leer_registro(ruta)
            meta.update(estado="cerrada", cerrado=_hoy(),
                        resolucion=(resolucion + (f" ({id_decision.upper()})" if id_decision else ""))[:200])
            _escribir_registro(ruta, meta, cuerpo + f"\n\n## Resolución ({_hoy()})\n{resolucion}\n")
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} cerrado")
            return f"{meta['id']} cerrado · commit {sha}"
    return _ejecutar(f)


@herramienta
def registrar_sesion(proyecto: str, resumen: str) -> str:
    """Cierre de chat (/cierre): anexa el resumen de la sesión a sesiones/AAAA-MM-DD.md."""
    def f():
        with _bloqueo(proyecto):
            p = _mem(proyecto) / "sesiones" / f"{_hoy()}.md"
            previo = p.read_text(encoding="utf-8") if p.exists() else f"# Sesiones {_hoy()}\n"
            hora = _registros._ahora().strftime("%H:%M")
            _escribir_atomico(p, previo.rstrip("\n") + f"\n\n## {hora}\n{resumen.strip()}\n")
            return f"Sesión registrada · commit {_commit(proyecto, [p], f'sesión {_hoy()} {hora}')}"
    return _ejecutar(f)
