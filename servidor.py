# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2"]
# ///
"""
ratifact (memoria-proyectos) — servidor MCP local que convierte cada repositorio en la
memoria persistente de su proyecto (acuerdos, pendientes, sesiones y documentos).

Fuente de verdad: la carpeta .project/ dentro del repositorio del proyecto.
- decisions/ADR-NNN.md, pending/P-NNN.md y tasks/T-NNN.md son los registros (un archivo cada uno; esquema v2).
- DECISIONS.md y OPEN.md son VISTAS generadas a partir de esos registros; no se editan a mano.
- Cada escritura hace un commit de git con solo los archivos tocados.

Configuración: RATIFACT_CONFIG, o ~/.config/ratifact/projects.json si existe, o ~/.config/memoria-proyectos/projects.json
(MEMORIA_PROYECTOS_CONFIG / _LOG / _BASE siguen funcionando como respaldo, con aviso, hasta 1.1)
{
  "game": {"ruta": "/home/usuario/Projects/game/prototipo-godot",
           "memoria": "/home/usuario/Projects/game/.project",   # opcional; recomendado fuera del repo
           "escritura": [".project", "docs"]}
}
"""
import sys
from pathlib import Path

# El paquete ratifact/ vive junto a este archivo: se agrega su carpeta a sys.path para arrancar desde cualquier cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ratifact import app, config, esquema, plantillas, prompts, registros  # noqa: E402
from ratifact.herramientas import (contexto_documentos, decisiones, pendientes_sesiones,  # noqa: E402
                                   proyectos, tareas, tareas_brief)

# Reexporta herramientas, constantes y ayudantes de todos los módulos, para quien importe `servidor` (p. ej. las
# pruebas). Reemplazar un nombre aquí no afecta a quien lo usa: hay que reemplazarlo en el módulo donde se busca.
for _modulo in (config, registros, esquema, plantillas, app, contexto_documentos, decisiones, pendientes_sesiones,
                tareas, tareas_brief, proyectos, prompts):
    globals().update({k: v for k, v in vars(_modulo).items() if not k.startswith("__")})
del _modulo

mcp = app.mcp

if __name__ == "__main__":
    mcp.run()
