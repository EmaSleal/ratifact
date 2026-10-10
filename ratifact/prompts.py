"""Prompts MCP reutilizables: inicio y cierre de sesión."""
from __future__ import annotations

from ratifact.app import mcp
from ratifact.plantillas import TEXTO_CIERRE


# ───────────────────────── prompts (comandos reutilizables) ─────────────────────────

def _proyecto_objetivo(proyecto: str) -> str:
    """Texto que fija el proyecto. Sin argumento, el modelo lo toma del contexto del chat: nunca se asume uno."""
    if proyecto.strip():
        return f"el proyecto `{proyecto.strip()}`"
    return ("el proyecto de este chat: tómalo de la línea `proyecto:` de las instrucciones del proyecto de Claude "
            "(o del CLAUDE.md / AGENTS.md del repositorio). Si no hay ninguna o hay duda, llama `listar_proyectos` "
            "y pregúntame cuál antes de seguir. No asumas ningún proyecto por defecto")


@mcp.prompt(name="cierre", description="Cierra la sesión: registra decisiones, pendientes y bitácora, y regenera INDEX.md")
def prompt_cierre(proyecto: str = "") -> str:
    return TEXTO_CIERRE.format(objetivo=_proyecto_objetivo(proyecto))


@mcp.prompt(name="inicio", description="Carga el contexto del proyecto antes de empezar a trabajar")
def prompt_inicio(proyecto: str = "") -> str:
    return (f"Trabaja con {_proyecto_objetivo(proyecto)}. Llama `obtener_contexto` para ese proyecto y resúmeme en "
            "5 líneas: estado actual, tareas activas, pendientes que bloquean y propuestas esperando mi confirmación. "
            "Empieza diciendo qué proyecto cargaste. Si avisa que INDEX.md está desactualizado, dímelo primero.")
