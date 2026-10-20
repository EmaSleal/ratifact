"""Vocabulario del esquema v2 de la memoria (docs/v1-english-naming.md §5, §6 y addendum 2026-10-18): carpetas,
vistas, estados y claves en inglés, con su equivalente v1 en español. Lo usan la migración v1 → v2 y los parámetros
de estado de las herramientas, que durante la transición aceptan ambos idiomas (ADR-028) y guardan siempre inglés."""
from __future__ import annotations

# carpetas de registros: v1 → v2
CARPETAS_V1 = {"decisiones": "decisions", "pendientes": "pending", "sesiones": "sessions", "tareas": "tasks"}
DECISIONES, PENDIENTES, SESIONES, TAREAS = CARPETAS_V1.values()

# vistas generadas: v1 → v2
VISTAS_V1 = {"acuerdos.md": "DECISIONS.md", "abiertas.md": "OPEN.md"}
VISTA_DECISIONES, VISTA_ABIERTOS = VISTAS_V1.values()

# claves del frontmatter: v1 → v2 (id y commit no cambian; cualquier otra clave queda como está)
CLAVES_V1 = {"titulo": "title", "estado": "status", "fecha": "date", "actualizada": "updated", "resumen": "summary",
             "reemplazada_por": "superseded_by", "tema": "topic", "dueno": "owner", "rama": "branch",
             "repositorio": "repo", "revisiones": "reviews", "creado": "created", "resuelve": "resolves",
             "confirmada": "accepted", "descartada": "rejected", "cerrado": "closed", "resolucion": "resolution"}

# estados por tipo de registro: v1 → v2
ESTADOS_V1 = {
    "decision": {"propuesta": "proposed", "acordada": "accepted", "descartada": "rejected",
                 "reemplazada": "superseded"},
    "pendiente": {"abierta": "open", "cerrada": "closed"},
    "tarea": {"pendiente": "todo", "en_curso": "in_progress", "en_revision": "in_review",
              "devuelta": "changes_requested", "fallida": "failed", "integrada": "merged", "descartada": "discarded"},
}
ESTADOS = {tipo: tuple(m.values()) for tipo, m in ESTADOS_V1.items()}

# tipo de registro de cada carpeta v1 (la migración elige el mapa de estados por carpeta)
TIPO_DE_CARPETA_V1 = {"decisiones": "decision", "pendientes": "pendiente", "tareas": "tarea"}


def _normalizar_estado(tipo: str, valor: str) -> str:
    """Estado recibido en un parámetro, en español (v1) o inglés (v2), → inglés. "en_curso" y "in_progress" →
    "in_progress". Valor desconocido → ErrorMemoria con los válidos."""
    from ratifact.config import ErrorMemoria     # aquí y no arriba: config importa este módulo (alias de rutas)
    v = valor.strip().lower()
    if v in ESTADOS[tipo]:
        return v
    if v in ESTADOS_V1[tipo]:
        return ESTADOS_V1[tipo][v]
    raise ErrorMemoria(f"Invalid status '{valor}'. Use: {', '.join(ESTADOS[tipo])} "
                       f"(Spanish names still accepted until 1.1: {', '.join(ESTADOS_V1[tipo])})")


# ───────────────────────── contrato v1 (T-011, docs/v1-english-naming.md §3, §4 y addenda) ─────────────────────────
# Herramientas: nombre en español (contrato v0) → nombre en inglés. Lo usan analizar_uso (agrega el historial de
# telemetría por herramienta) y la prueba de contrato. amend_task y read_task nacen en inglés (sin predecesor).
HERRAMIENTAS_V0 = {
    "listar_proyectos": "list_projects", "obtener_contexto": "get_context", "registrar_proyecto": "register_project",
    "inicializar_memoria": "init_memory", "instrucciones_proyecto": "project_instructions",
    "actualizar_proyecto": "update_project", "registrar_decision": "propose_decision",
    "confirmar_decision": "accept_decision", "confirmar_decisiones_lote": "accept_decisions",
    "revisar_propuestas": "review_proposals", "decidir_propuestas": "decide_proposals",
    "descartar_decision": "reject_decision", "reemplazar_decision": "supersede_decision",
    "registrar_pendiente": "add_pending", "cerrar_pendiente": "close_pending", "buscar": "search",
    "listar_documentos": "list_documents", "leer_documento": "read_document", "crear_documento": "create_document",
    "guardar_documento": "update_document", "actualizar_indice": "update_index", "registrar_sesion": "log_session",
    "registrar_tarea": "create_task", "actualizar_tarea": "update_task", "devolver_tarea": "request_changes",
    "listar_tareas": "list_tasks", "configurar_pruebas": "update_project",   # configurar_pruebas: eliminada (T-005)
}
HERRAMIENTAS_NUEVAS = ("amend_task", "read_task")
PROMPTS_V0 = {"inicio": "start", "cierre": "close"}

# Parámetros: español → inglés (§4 y addendum 2026-10-18). decision, id, ids y commit no cambian.
PARAMETROS_V0 = {
    "proyecto": "project", "titulo": "title", "justificacion": "rationale", "alternativas": "alternatives",
    "resumen": "summary", "cita_usuario": "user_quote", "desde_id": "from_id", "cantidad": "limit",
    "motivo": "reason", "id_anterior": "old_id", "id_nuevo": "new_id", "tema": "topic", "contexto": "context",
    "dueno": "owner", "resolucion": "resolution", "id_decision": "decision_id", "texto": "query",
    "max_resultados": "max_results", "carpeta": "folder", "ruta": "path", "desde_linea": "from_line",
    "hasta_linea": "to_line", "contenido": "content", "modo": "mode", "objetivo": "goal",
    "criterios_aceptacion": "acceptance_criteria", "decisiones": "decisions", "archivos": "files",
    "fuera_de_alcance": "out_of_scope", "notas": "notes", "repositorio": "repo", "estado": "status",
    "resultado": "result", "observaciones": "findings", "criterios_adicionales": "additional_criteria",
    "incluir_cerradas": "include_closed", "comando": "command", "nombre": "name", "memoria": "memory",
    "pruebas": "tests", "resuelve": "resolves", "integraciones": "integrations", "redetectar": "redetect",
}

# Modos de update_document: los valores v0 se aceptan hasta 1.1.
MODOS_V0 = {"reemplazar": "replace", "anexar": "append"}
