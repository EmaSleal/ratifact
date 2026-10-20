"""Herramientas de decisiones (ADR): propose, accept (una o en lote), review, decide con formulario, reject y
supersede."""
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
from ratifact.vocabulario import DECISIONES


@herramienta
def propose_decision(project: str, title: str, decision: str, rationale: str,
                     alternatives: str = "", summary: str = "") -> str:
    """Creates an ADR. It is ALWAYS 'proposed'. To accept it, call accept_decision afterwards: that tool asks for
    the user's approval. `summary`: one line for the decisions view.
    Idempotent (ADR-019): if an ADR with this title (ignoring case and spaces) was created in the last minutes AND
    is STILL 'proposed', nothing new is created and the existing id is returned. If that ADR already changed status
    (e.g. rejected: the user asked for another version), a human already intervened, so a new ADR is recorded."""
    proyecto, titulo, justificacion, alternativas, resumen = project, title, rationale, alternatives, summary

    def f():
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / DECISIONES
            carpeta.mkdir(parents=True, exist_ok=True)
            dup = _duplicado_reciente(carpeta, "ADR", "title", titulo, "proposed")
            if dup:
                return _mensaje_duplicado(dup["id"])
            id_ = _siguiente_id(carpeta, "ADR")
            ruta = carpeta / f"{id_}-{_slug(titulo)}.md"
            meta = {"id": id_, "title": titulo, "status": "proposed", "date": _hoy(),
                    "created": _registros._ahora().isoformat(timespec="seconds"),
                    "summary": (resumen or decision.splitlines()[0])[:160]}
            cuerpo = f"# {id_} — {titulo}\n\n## Decision\n{decision}\n\n## Rationale\n{justificacion}\n"
            if alternativas:
                cuerpo += f"\n## Alternatives considered\n{alternativas}\n"
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{id_} {titulo} ({meta['status']})")
            return f"{id_} recorded as {meta['status']} · commit {sha}"
    return _ejecutar(f)


@herramienta
def accept_decision(project: str, id: str, user_quote: str) -> str:
    """Moves a decision from 'proposed' to 'accepted'. It is the ONLY way to accept a decision and the client asks
    for the user's approval on every call. `user_quote`: the user's literal words confirming it in the chat (stored
    in the ADR as evidence). Never call it without that confirmation."""
    proyecto, cita_usuario = project, user_quote

    def f():
        if len(cita_usuario.strip()) < 2:
            raise ErrorMemoria(FALTA_CITA)
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / DECISIONES, id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("status") != "proposed":
                raise ErrorMemoria(f"{meta.get('id')} is '{meta.get('status')}'; only proposed decisions can be accepted.")
            meta["status"], meta["accepted"] = "accepted", _hoy()
            cuerpo = cuerpo.rstrip() + f"\n\n## Acceptance ({_hoy()})\n> {cita_usuario.strip()}\n"
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} accepted")
            return f"{meta['id']} → accepted · commit {sha}"
    return _ejecutar(f)


@herramienta
def accept_decisions(project: str, ids: list[str], user_quote: str) -> str:
    """Accepts SEVERAL proposals with a single user approval; the user sees the full list when approving. Use it only
    when the user explicitly accepted those decisions in the same message; `user_quote` is that literal message.
    All or nothing: if any of them is not proposed or does not exist, none is accepted."""
    proyecto, cita_usuario = project, user_quote

    def f():
        if len(cita_usuario.strip()) < 2:
            raise ErrorMemoria(FALTA_CITA)
        unicos = list(dict.fromkeys(_normalizar_id(i) for i in ids if i.strip()))
        if not unicos:
            raise ErrorMemoria("The list of ids is empty.")
        if len(unicos) > 30:
            raise ErrorMemoria("At most 30 decisions per batch.")
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / DECISIONES
            registros = []
            for id_ in unicos:
                ruta = _buscar_registro(carpeta, id_)
                meta, cuerpo = _leer_registro(ruta)
                if meta.get("status") != "proposed":
                    raise ErrorMemoria(f"{meta.get('id')} is '{meta.get('status')}'; none was accepted.")
                registros.append((ruta, meta, cuerpo))
            for ruta, meta, cuerpo in registros:
                meta["status"], meta["accepted"] = "accepted", _hoy()
                cuerpo = cuerpo.rstrip() + f"\n\n## Acceptance ({_hoy()}, batch)\n> {cita_usuario.strip()}\n"
                _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [r for r, _, _ in registros] + _regenerar_vistas(proyecto),
                          f"{len(registros)} decisions accepted in batch: {', '.join(unicos)}")
            return f"{len(registros)} → accepted ({', '.join(unicos)}) · commit {sha}"
    return _ejecutar(f)


@herramienta
def review_proposals(project: str, from_id: str = "", limit: int = 10, summary: bool = False) -> str:
    """Returns the decisions in 'proposed' status so the user can decide to accept, adjust or reject them.
    Paginated: `limit` per page (max 25) starting at `from_id` (e.g. "ADR-020"). With `summary=True` it returns one
    line per proposal (useful to see the overview before going into detail)."""
    proyecto, desde_id, cantidad, resumen = project, from_id, limit, summary

    def f():
        desde = _numero_id(desde_id) if desde_id else 0
        if desde is None:
            raise ErrorMemoria(f"Invalid from_id: '{desde_id}' (use the form \"ADR-020\").")
        carpeta = _mem(proyecto) / DECISIONES
        archivos = sorted(carpeta.glob("ADR-*.md"), key=lambda a: _clave_id(a.name)) \
            if carpeta.exists() else []
        propuestas = []
        for p in archivos:   # orden y filtro numéricos: ADR-1000 va después de ADR-999
            m, cuerpo = _leer_registro(p)
            if m.get("status") == "proposed" and (_numero_id(m.get("id", "")) or 0) >= desde:
                propuestas.append((m, cuerpo))
        if not propuestas:
            return SIN_PROPUESTAS
        n = max(1, min(cantidad, 25))
        pagina, resto = propuestas[:n], propuestas[n:]
        if resumen:
            cuerpo_txt = "\n".join(f"- **{m.get('id')}** {m.get('title')} — {m.get('summary', '')}" for m, _ in pagina)
        else:
            cuerpo_txt = "\n\n---\n\n".join(f"{c.strip()}\n\n_(proposed on {m.get('date')})_" for m, c in pagina)
        pie = (f"\n\n({len(resto)} proposal(s) left: continue with from_id=\"{resto[0][0].get('id')}\".)"
               if resto else "")
        return (f"{len(propuestas)} proposal(s) to review; showing {len(pagina)}. Present them to the user as "
                "multiple-choice questions if the app supports it (accept / adjust / reject / postpone). "
                "Then: accept (accept_decision, or accept_decisions if the user approves several in the same "
                "message), adjust (propose a new one and supersede_decision) or reject (reject_decision). "
                "One write at a time, not in parallel.\n\n" + cuerpo_txt + pie)
    return _ejecutar(f)


FALTA_CITA = "Missing user_quote: the user's literal words confirming the decision."
SIN_PROPUESTAS = "(no proposals awaiting review)"


class DecisionUsuario(BaseModel):
    action: str = Field(
        json_schema_extra={"enum": ["accept", "reject", "adjust", "postpone"]},
        description="accept = becomes accepted · reject = closed (rejected) · adjust = ask for a new version · "
                    "postpone = stays proposed")
    comment: str = Field(default="", description="Optional. Reason for rejecting, or what to change when adjusting.")


def _texto_propuesta(cuerpo: str, limite: int = 1200) -> str:
    texto = re.sub(r"\n{3,}", "\n\n", cuerpo.strip())
    return texto if len(texto) <= limite else texto[:limite] + "…"


@herramienta_async
@_ejecutar_async
async def decide_proposals(project: str, ctx: Context) -> str:
    """ONLY for apps that support MCP forms (elicitation), such as Claude Code. In Claude Desktop or claude.ai do NOT
    use it: call review_proposals and present the options (accept / adjust / reject / postpone) with your own cards
    or multiple-choice questions; then apply accept_decision or reject_decision as the user chooses.
    Opens one form per pending proposal; the answers come from the user without going through the model, so
    acceptances and rejections are applied directly. Returns the summary and the proposals to adjust."""
    proyecto = project
    params = getattr(ctx.session, "client_params", None)
    if not (params and params.capabilities and params.capabilities.elicitation):
        return ("This app does not support MCP forms. Use review_proposals and present the options with your own "
                "cards or multiple-choice questions; then accept_decision / reject_decision.")
    carpeta = _mem(proyecto) / DECISIONES
    pendientes = []
    for p in sorted(carpeta.glob("ADR-*.md"), key=lambda a: _clave_id(a.name)) if carpeta.exists() else []:
        m, cuerpo = _leer_registro(p)
        if m.get("status") == "proposed":
            pendientes.append((m.get("id"), cuerpo))
    if not pendientes:
        return SIN_PROPUESTAS

    hechos, ajustes, pospuestas = [], [], []
    for i, (id_, cuerpo) in enumerate(pendientes, 1):
        try:
            r = await ctx.elicit(f"Proposal {i} of {len(pendientes)}\n\n{_texto_propuesta(cuerpo)}", DecisionUsuario)
        except Exception as e:   # el cliente no implementa formularios (elicitation)
            return ("ERROR: this client does not support interactive forms "
                    f"({type(e).__name__}). Use review_proposals and then accept_decision / reject_decision.")
        if r.action != "accept" or r.data is None:
            pospuestas += [x[0] for x in pendientes[i - 1:]]
            hechos.append(f"Review interrupted by the user at {id_} ({r.action}).")
            break
        d = r.data
        nota = d.comment.strip()
        if d.action not in ("accept", "reject", "adjust", "postpone"):
            pospuestas.append(id_)
            continue
        if d.action == "accept":
            cita = "[form] accept" + (f" — {nota}" if nota else "")
            hechos.append(f"{id_}: {accept_decision(project=proyecto, id=id_, user_quote=cita)}")
        elif d.action == "reject":
            motivo = nota or "Rejected by the user from the form."
            hechos.append(f"{id_}: {reject_decision(project=proyecto, id=id_, reason=motivo)}")
        elif d.action == "adjust":
            ajustes.append(f"- {id_}: {nota or '(no instructions: ask the user what to change)'}")
        else:
            pospuestas.append(id_)

    salida = ["Review result:", *(f"- {h}" for h in hechos)]
    if pospuestas:
        salida.append(f"- Still proposed: {', '.join(pospuestas)}")
    if ajustes:
        salida += ["", "The user asked to ADJUST these proposals. Draft the new version of each with "
                   "propose_decision, then supersede_decision(old, new), and offer decide_proposals again so "
                   "the user can accept the new ones:", *ajustes]
    return "\n".join(salida)


@herramienta
def reject_decision(project: str, id: str, reason: str) -> str:
    """Closes a proposal the user does NOT approve. It becomes 'rejected' with its reason (it is not deleted: the
    history keeps what was considered and why it was not adopted). Only on the user's explicit instruction."""
    proyecto, motivo = project, reason

    def f():
        if len(motivo.strip()) < 3:
            raise ErrorMemoria("Missing the reason for rejecting.")
        with _bloqueo(proyecto):
            ruta = _buscar_registro(_mem(proyecto) / DECISIONES, id)
            meta, cuerpo = _leer_registro(ruta)
            if meta.get("status") != "proposed":
                raise ErrorMemoria(f"{meta.get('id')} is '{meta.get('status')}'; only proposed decisions can be "
                                   "rejected. To revoke an accepted one, use supersede_decision.")
            meta["status"], meta["rejected"] = "rejected", _hoy()
            cuerpo = cuerpo.rstrip() + f"\n\n## Rejected ({_hoy()})\n{motivo.strip()}\n"
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} rejected")
            return f"{meta['id']} → rejected · commit {sha}"
    return _ejecutar(f)


@herramienta
def supersede_decision(project: str, old_id: str, new_id: str) -> str:
    """Marks a decision as superseded by another one already recorded (status 'superseded'; decisions are never
    deleted)."""
    proyecto, id_anterior, id_nuevo = project, old_id, new_id

    def f():
        with _bloqueo(proyecto):
            carpeta = _mem(proyecto) / DECISIONES
            _buscar_registro(carpeta, id_nuevo)
            nuevo = _normalizar_id(id_nuevo)
            ruta = _buscar_registro(carpeta, id_anterior)
            meta, cuerpo = _leer_registro(ruta)
            meta["status"], meta["superseded_by"] = "superseded", nuevo
            _escribir_registro(ruta, meta, cuerpo)
            sha = _commit(proyecto, [ruta, *_regenerar_vistas(proyecto)], f"{meta['id']} superseded by {nuevo}")
            return f"{meta['id']} → superseded (by {nuevo}) · commit {sha}"
    return _ejecutar(f)
