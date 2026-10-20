"""Herramientas de pendientes (add_pending, close_pending) y bitácora de sesiones (log_session)."""
from __future__ import annotations

from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, herramienta
from ratifact.config import _mem
from ratifact.esquema import _bloqueo
from ratifact.registros import (_buscar_registro, _commit, _duplicado_reciente, _escribir_atomico, _escribir_registro,
                                _hoy, _leer_registro, _mensaje_duplicado, _normalizar_id, _regenerar_vistas,
                                _siguiente_id, _slug)
from ratifact.vocabulario import PENDIENTES, SESIONES


@herramienta
def add_pending(project: str, topic: str, context: str, owner: str = "") -> str:
    """Records an open question or unresolved topic. Idempotent (ADR-019): if a pending item with this topic
    (ignoring case and spaces) was created in the last minutes AND is STILL 'open', nothing new is created and the
    existing id is returned. If that item was already closed, a human already intervened, so a new one is recorded."""
    proyecto, tema, contexto, dueno = project, topic, context, owner

    def f():
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / PENDIENTES
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "P", "topic", tema, "open")
            if dup:
                return _mensaje_duplicado(dup["id"])
            id_ = _siguiente_id(carpeta, "P")
            ruta = carpeta / f"{id_}-{_slug(tema)}.md"
            meta = {"id": id_, "topic": tema, "status": "open", "date": _hoy(),
                    "created": _registros._ahora().isoformat(timespec="seconds")}
            if dueno:
                meta["owner"] = dueno
            _escribir_registro(ruta, meta, contexto)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{id_} {tema}")
            return f"{id_} recorded · commit {sha}"
    return _ejecutar(f)


@herramienta
def close_pending(project: str, id: str, resolution: str, decision_id: str = "") -> str:
    """Closes a pending item (status 'closed'). If the resolution produced a decision, give its decision_id."""
    proyecto, resolucion, id_decision = project, resolution, decision_id

    def f():
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / PENDIENTES, id)
            meta, cuerpo = _leer_registro(ruta)
            meta.update(status="closed", closed=_hoy(),
                        resolution=(resolucion + (f" ({_normalizar_id(id_decision)})" if id_decision else ""))[:200])
            _escribir_registro(ruta, meta, cuerpo + f"\n\n## Resolution ({_hoy()})\n{resolucion}\n")
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} closed")
            return f"{meta['id']} → closed · commit {sha}"
    return _ejecutar(f)


@herramienta
def log_session(project: str, summary: str) -> str:
    """End of a chat (close prompt): appends the session summary to sessions/YYYY-MM-DD.md."""
    proyecto, resumen = project, summary

    def f():
        with _bloqueo(proyecto):
            p = _mem(proyecto) / SESIONES / f"{_hoy()}.md"
            previo = p.read_text(encoding="utf-8") if p.exists() else f"# Sessions {_hoy()}\n"
            hora = _registros._ahora().strftime("%H:%M")
            _escribir_atomico(p, previo.rstrip("\n") + f"\n\n## {hora}\n{resumen.strip()}\n")
            return f"Session logged · commit {_commit(proyecto, [p], f'sesión {_hoy()} {hora}')}"
    return _ejecutar(f)
