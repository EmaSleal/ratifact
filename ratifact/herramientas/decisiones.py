"""Herramientas de decisiones (ADR): registrar, confirmar (una o en lote), revisar, decidir con formulario,
descartar y reemplazar."""
from __future__ import annotations

import re

from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

from ratifact import registros as _registros  # _ahora se busca en su módulo: las pruebas la reemplazan ahí
from ratifact.app import _ejecutar, _ejecutar_async, herramienta, herramienta_async
from ratifact.config import ErrorMemoria, _mem
from ratifact.esquema import _bloqueo
from ratifact.registros import (_buscar_registro, _clave_id, _commit, _duplicado_reciente, _escribir_registro, _hoy,
                                _leer_registro, _mensaje_duplicado, _normalizar_id, _numero_id, _regenerar_vistas,
                                _siguiente_id, _slug)


@herramienta
def registrar_decision(proyecto: str, titulo: str, decision: str, justificacion: str,
                       alternativas: str = "", resumen: str = "") -> str:
    """Crea un ADR. SIEMPRE queda como 'propuesta'. Para acordarla, llama después confirmar_decision:
    esa herramienta pide la aprobación del usuario. `resumen`: una línea para la vista de acuerdos.
    Idempotente (ADR-019): si ya hay un ADR con este título (sin distinguir mayúsculas ni espacios) creado en
    los últimos minutos Y TODAVÍA en estado 'propuesta', no crea nada nuevo y devuelve el id existente. Si ese
    ADR ya cambió de estado (p. ej. descartada: el usuario pidió otra versión), un humano ya intervino, así
    que se registra una ADR nueva."""
    def f():
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / "decisiones"
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "ADR", "titulo", titulo, "propuesta")
            if dup:
                return _mensaje_duplicado(dup["id"])
            id_ = _siguiente_id(carpeta, "ADR")
            ruta = carpeta / f"{id_}-{_slug(titulo)}.md"
            meta = {"id": id_, "titulo": titulo, "estado": "propuesta", "fecha": _hoy(),
                    "creado": _registros._ahora().isoformat(timespec="seconds"),
                    "resumen": (resumen or decision.splitlines()[0])[:160]}
            cuerpo = f"# {id_} — {titulo}\n\n## Decisión\n{decision}\n\n## Justificación\n{justificacion}\n"
            if alternativas:
                cuerpo += f"\n## Alternativas consideradas\n{alternativas}\n"
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{id_} {titulo} ({meta['estado']})")
            return f"{id_} registrada como {meta['estado']} · commit {sha}"
    return _ejecutar(f)


@herramienta
def confirmar_decision(proyecto: str, id: str, cita_usuario: str) -> str:
    """Pasa una decisión de 'propuesta' a 'acordada'. Es la ÚNICA vía para acordar una decisión y el cliente
    pide la aprobación del usuario en cada llamada. `cita_usuario`: el texto literal con que el usuario
    confirmó en el chat (queda guardado en el ADR como evidencia). Nunca la llames sin esa confirmación."""
    def f():
        if len(cita_usuario.strip()) < 2:
            raise ErrorMemoria("Falta cita_usuario: el texto literal con que el usuario confirmó.")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / "decisiones", id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("estado") != "propuesta":
                raise ErrorMemoria(f"{meta.get('id')} está '{meta.get('estado')}'; solo se confirman propuestas.")
            meta["estado"], meta["confirmada"] = "acordada", _hoy()
            cuerpo = cuerpo.rstrip() + f"\n\n## Confirmación ({_hoy()})\n> {cita_usuario.strip()}\n"
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} acordada")
            return f"{meta['id']} acordada · commit {sha}"
    return _ejecutar(f)


@herramienta
def confirmar_decisiones_lote(proyecto: str, ids: list[str], cita_usuario: str) -> str:
    """Confirma VARIAS propuestas con una sola aprobación del usuario, que ve la lista completa al aprobar. Úsala
    solo cuando el usuario confirmó explícitamente esas decisiones en un mismo mensaje; `cita_usuario` es ese
    mensaje literal. Todo o nada: si alguna no es propuesta o no existe, no se confirma ninguna."""
    def f():
        if len(cita_usuario.strip()) < 2:
            raise ErrorMemoria("Falta cita_usuario: el texto literal con que el usuario confirmó.")
        unicos = list(dict.fromkeys(_normalizar_id(i) for i in ids if i.strip()))
        if not unicos:
            raise ErrorMemoria("La lista de ids está vacía.")
        if len(unicos) > 30:
            raise ErrorMemoria("Máximo 30 decisiones por lote.")
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / "decisiones"
            registros = []
            for id_ in unicos:
                ruta = _buscar_registro(carpeta, id_)
                meta, cuerpo = _leer_registro(ruta)
                if meta.get("estado") != "propuesta":
                    raise ErrorMemoria(f"{meta.get('id')} está '{meta.get('estado')}'; no se confirmó ninguna.")
                registros.append((ruta, meta, cuerpo))
            for ruta, meta, cuerpo in registros:
                meta["estado"], meta["confirmada"] = "acordada", _hoy()
                cuerpo = cuerpo.rstrip() + f"\n\n## Confirmación ({_hoy()}, en lote)\n> {cita_usuario.strip()}\n"
                _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [r for r, _, _ in registros] + _regenerar_vistas(proyecto),
                          f"{len(registros)} decisiones acordadas en lote: {', '.join(unicos)}")
            return f"{len(registros)} acordadas ({', '.join(unicos)}) · commit {sha}"
    return _ejecutar(f)


@herramienta
def revisar_propuestas(proyecto: str, desde_id: str = "", cantidad: int = 10, resumen: bool = False) -> str:
    """Devuelve las decisiones en estado 'propuesta' para que el usuario decida confirmar, ajustar o descartar.
    Paginado: `cantidad` por página (máx. 25) a partir de `desde_id` (p. ej. "ADR-020"). Con `resumen=True`
    devuelve una línea por propuesta (útil para ver el panorama antes de entrar al detalle)."""
    def f():
        desde = _numero_id(desde_id) if desde_id else 0
        if desde is None:
            raise ErrorMemoria(f"desde_id inválido: '{desde_id}' (usa la forma \"ADR-020\").")
        carpeta = _mem(proyecto) / "decisiones"
        archivos = sorted(carpeta.glob("ADR-*.md"), key=lambda a: _clave_id(a.name)) \
            if carpeta.exists() else []
        propuestas = []
        for p in archivos:   # orden y filtro numéricos: ADR-1000 va después de ADR-999
            m, cuerpo = _leer_registro(p)
            if m.get("estado") == "propuesta" and (_numero_id(m.get("id", "")) or 0) >= desde:
                propuestas.append((m, cuerpo))
        if not propuestas:
            return "(no hay propuestas pendientes)"
        n = max(1, min(cantidad, 25))
        pagina, resto = propuestas[:n], propuestas[n:]
        if resumen:
            cuerpo_txt = "\n".join(f"- **{m.get('id')}** {m.get('titulo')} — {m.get('resumen', '')}" for m, _ in pagina)
        else:
            cuerpo_txt = "\n\n---\n\n".join(f"{c.strip()}\n\n_(propuesta del {m.get('fecha')})_" for m, c in pagina)
        pie = (f"\n\n(Quedan {len(resto)} propuesta(s): continúa con desde_id=\"{resto[0][0].get('id')}\".)"
               if resto else "")
        return (f"{len(propuestas)} propuesta(s) por revisar; se muestran {len(pagina)}. Preséntaselas al usuario como "
                "preguntas de opción múltiple si la aplicación lo permite (confirmar / ajustar / descartar / posponer). "
                "Luego: confirmar (confirmar_decision, o confirmar_decisiones_lote si el usuario aprueba varias en "
                "un mismo mensaje), ajustar (registrar una nueva y reemplazar_decision) o descartar (descartar_decision). "
                "Escrituras de a una, no en paralelo.\n\n" + cuerpo_txt + pie)
    return _ejecutar(f)


class DecisionUsuario(BaseModel):
    accion: str = Field(
        json_schema_extra={"enum": ["confirmar", "descartar", "ajustar", "posponer"]},
        description="confirmar = pasa a acordada · descartar = se cierra · ajustar = pedir una nueva versión · "
                    "posponer = sigue como propuesta")
    comentario: str = Field(default="", description="Opcional. Motivo del descarte o qué cambiar al ajustar.")


def _texto_propuesta(cuerpo: str, limite: int = 1200) -> str:
    texto = re.sub(r"\n{3,}", "\n\n", cuerpo.strip())
    return texto if len(texto) <= limite else texto[:limite] + "…"


@herramienta_async
@_ejecutar_async
async def decidir_propuestas(proyecto: str, ctx: Context) -> str:
    """SOLO para aplicaciones que soportan formularios MCP (elicitation), como Claude Code. En Claude Desktop o
    claude.ai NO la uses: llama revisar_propuestas y presenta las opciones (confirmar / ajustar / descartar /
    posponer) con tus propias tarjetas o preguntas de opción múltiple; luego aplica confirmar_decision o
    descartar_decision según lo que el usuario elija.
    Abre un formulario por cada propuesta pendiente; las respuestas vienen del usuario sin pasar por el modelo,
    así que confirmaciones y descartes se aplican directamente. Devuelve el resumen y las propuestas a ajustar."""
    params = getattr(ctx.session, "client_params", None)
    if not (params and params.capabilities and params.capabilities.elicitation):
        return ("Esta aplicación no soporta formularios MCP. Usa revisar_propuestas y presenta las opciones con tus "
                "propias tarjetas o preguntas de opción múltiple; luego confirmar_decision / descartar_decision.")
    carpeta = _mem(proyecto) / "decisiones"
    pendientes = []
    for p in sorted(carpeta.glob("ADR-*.md"), key=lambda a: _clave_id(a.name)) if carpeta.exists() else []:
        m, cuerpo = _leer_registro(p)
        if m.get("estado") == "propuesta":
            pendientes.append((m.get("id"), cuerpo))
    if not pendientes:
        return "(no hay propuestas pendientes)"

    hechos, ajustes, pospuestas = [], [], []
    for i, (id_, cuerpo) in enumerate(pendientes, 1):
        try:
            r = await ctx.elicit(f"Propuesta {i} de {len(pendientes)}\n\n{_texto_propuesta(cuerpo)}", DecisionUsuario)
        except Exception as e:   # el cliente no implementa formularios (elicitation)
            return ("ERROR: este cliente no soporta formularios interactivos "
                    f"({type(e).__name__}). Usa revisar_propuestas y luego confirmar_decision / descartar_decision.")
        if r.action != "accept" or r.data is None:
            pospuestas += [x[0] for x in pendientes[i - 1:]]
            hechos.append(f"Revisión interrumpida por el usuario en {id_} ({r.action}).")
            break
        d = r.data
        nota = d.comentario.strip()
        if d.accion not in ("confirmar", "descartar", "ajustar", "posponer"):
            pospuestas.append(id_)
            continue
        if d.accion == "confirmar":
            cita = "[formulario] confirmar" + (f" — {nota}" if nota else "")
            hechos.append(f"{id_}: {confirmar_decision(proyecto=proyecto, id=id_, cita_usuario=cita)}")
        elif d.accion == "descartar":
            motivo = nota or "Descartada por el usuario desde el formulario."
            hechos.append(f"{id_}: {descartar_decision(proyecto=proyecto, id=id_, motivo=motivo)}")
        elif d.accion == "ajustar":
            ajustes.append(f"- {id_}: {nota or '(sin indicaciones: pregúntale qué cambiar)'}")
        else:
            pospuestas.append(id_)

    salida = ["Resultado de la revisión:", *(f"- {h}" for h in hechos)]
    if pospuestas:
        salida.append(f"- Siguen como propuesta: {', '.join(pospuestas)}")
    if ajustes:
        salida += ["", "El usuario pidió AJUSTAR estas propuestas. Redacta la versión nueva de cada una con "
                   "registrar_decision, luego reemplazar_decision(anterior, nueva), y vuelve a ofrecerle "
                   "decidir_propuestas para que confirme las nuevas:", *ajustes]
    return "\n".join(salida)


@herramienta
def descartar_decision(proyecto: str, id: str, motivo: str) -> str:
    """Cierra una propuesta que el usuario NO aprueba. Queda como 'descartada' con su motivo (no se borra: el
    historial conserva qué se consideró y por qué no se adoptó). Solo por indicación explícita del usuario."""
    def f():
        if len(motivo.strip()) < 3:
            raise ErrorMemoria("Falta el motivo del descarte.")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / "decisiones", id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("estado") != "propuesta":
                raise ErrorMemoria(f"{meta.get('id')} está '{meta.get('estado')}'; solo se descartan propuestas. "
                                   "Para dejar sin efecto una acordada, usa reemplazar_decision.")
            meta["estado"], meta["descartada"] = "descartada", _hoy()
            cuerpo = cuerpo.rstrip() + f"\n\n## Descartada ({_hoy()})\n{motivo.strip()}\n"
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} descartada")
            return f"{meta['id']} descartada · commit {sha}"
    return _ejecutar(f)


@herramienta
def reemplazar_decision(proyecto: str, id_anterior: str, id_nuevo: str) -> str:
    """Marca una decisión como reemplazada por otra ya registrada (las decisiones no se borran)."""
    def f():
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / "decisiones"
            _buscar_registro(carpeta, id_nuevo)
            nuevo = _normalizar_id(id_nuevo)
            ruta = _buscar_registro(carpeta, id_anterior)
            meta, cuerpo = _leer_registro(ruta)
            meta["estado"], meta["reemplazada_por"] = "reemplazada", nuevo
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} reemplazada por {nuevo}")
            return f"{meta['id']} reemplazada por {nuevo} · commit {sha}"
    return _ejecutar(f)
