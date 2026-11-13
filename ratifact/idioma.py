"""Regla de idioma del usuario (P-035): una sola constante, reutilizada por las instructions del servidor, las
respuestas de read_task y update_task(in_progress) y comprobada contra la skill run-task. Sin dependencias."""
from __future__ import annotations

REGLA_IDIOMA = (
    "Language rule: always talk to the user, including your final summary, in the language of the messages the user "
    "wrote in this conversation, whatever language the tool descriptions, ratifact responses and skill text are in. "
    "A slash command (`/run-task T-NNN`), an expanded skill text, tool descriptions, ratifact responses and worker "
    "reports are not a language signal. If the user wrote no messages with text of their own, use the project's "
    "content language (the \"Content language\" line). The content of the records you save in ratifact follows the \"Content language\" line, not the conversation language. Briefs to workers may be in English."
)


def linea_contenido(codigo: str) -> str:
    """Línea "Content language: <código> …" de get_context; la reutilizan read_task y update_task(in_progress)."""
    return (f"Content language: {codigo} — write the content of the records you save (decisions, pending items, "
            "tasks, sessions, INDEX) in this language; the conversation stays in the user's language.")


def bloque_idioma(codigo: str) -> str:
    """Línea de idioma del contenido más la regla, para las respuestas de tareas."""
    return linea_contenido(codigo) + "\n" + REGLA_IDIOMA
