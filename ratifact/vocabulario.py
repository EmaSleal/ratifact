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
    raise ErrorMemoria(f"Estado inválido. Usa: {', '.join(ESTADOS[tipo])} "
                       f"(o en español: {', '.join(ESTADOS_V1[tipo])})")
