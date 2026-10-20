"""Prompts MCP reutilizables: start y close de sesión."""
from __future__ import annotations

from ratifact.app import mcp
from ratifact.plantillas import TEXTO_CIERRE


# ───────────────────────── prompts (comandos reutilizables) ─────────────────────────

def _proyecto_objetivo(proyecto: str) -> str:
    """Texto que fija el proyecto. Sin argumento, el modelo lo toma del contexto del chat: nunca se asume uno."""
    if proyecto.strip():
        return f"project `{proyecto.strip()}`"
    return ("this chat's project: take it from the `project:` line of the Claude project instructions (or from the "
            "repository's CLAUDE.md / AGENTS.md). If there is none or you are unsure, call `list_projects` and ask me "
            "which one before going on. Never assume a default project")


@mcp.prompt(name="close", description="Closes the session: records decisions, pending items and the session log, and "
                                      "regenerates INDEX.md")
def prompt_cierre(project: str = "") -> str:
    return TEXTO_CIERRE.format(objetivo=_proyecto_objetivo(project))


@mcp.prompt(name="start", description="Loads the project context before starting to work")
def prompt_inicio(project: str = "") -> str:
    return (f"Work on {_proyecto_objetivo(project)}. Call `get_context` for that project and summarize it for me in "
            "5 lines: current status, active tasks, blocking pending items and proposals awaiting my acceptance. "
            "Start by saying which project you loaded. If it warns that INDEX.md is out of date, tell me first.")
