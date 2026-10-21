"""ratifact: paquete del servidor MCP memoria-proyectos. El punto de entrada es el comando `ratifact` (ratifact.cli);
`servidor.py` (raíz del repositorio) queda como envoltorio de `ratifact serve` hasta 1.1.

No importa submódulos: cada uno se importa por separado (sin ciclos) y `ratifact.cli` / `servidor.py` los cargan en
orden."""

__version__ = "1.0.0"    # igual que [project].version de pyproject.toml (tests/test_cli.py lo comprueba)
