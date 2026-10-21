# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2,<2"]
# ///
"""
Envoltorio deprecado de `ratifact serve` (se quita en 1.1): las configuraciones de clientes que lanzan
`uv run --script servidor.py` siguen funcionando. Lo nuevo es instalar el paquete (`uv tool install <ruta del repo>`)
y configurar los clientes con el comando `ratifact serve` (docs/upgrade-v1.md).

ratifact (memoria-proyectos) — servidor MCP local que convierte cada repositorio en la memoria persistente de su
proyecto. Fuente de verdad: la carpeta .project/ (memoria con repo git propio); DECISIONS.md y OPEN.md son vistas
generadas. Configuración: RATIFACT_CONFIG, o ~/.config/ratifact/projects.json si existe, o
~/.config/memoria-proyectos/projects.json (MEMORIA_PROYECTOS_CONFIG / _LOG / _BASE siguen funcionando, con aviso,
hasta 1.1).
"""
import sys
from pathlib import Path

# El paquete ratifact/ vive junto a este archivo: se agrega su carpeta a sys.path para arrancar desde cualquier cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ratifact import app, cli, config, esquema, plantillas, prompts, registros  # noqa: E402
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
    cli.main(["serve"])
