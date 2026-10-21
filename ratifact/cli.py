"""Comando `ratifact` (ADR-032): `serve` (servidor MCP por stdio, lo que lanzan los clientes), `install` (configura
los clientes MCP y /run-task, T-013), `report` (resumen del uso, antes analizar_uso.py), `doctor` (diagnóstico de solo
lectura) y `upgrade` (paso explícito de ADR-029). `install` y `upgrade` sin `--apply` solo muestran el plan.
`ratifact --version` muestra la versión."""
from __future__ import annotations

import argparse
import sys

from ratifact import __version__


def servidor():
    """Carga los módulos de herramientas y prompts (sus decoradores los registran en `app.mcp`) y devuelve `mcp`."""
    from ratifact import app, prompts  # noqa: F401
    from ratifact import herramientas  # noqa: F401
    return app.mcp


def _parser() -> argparse.ArgumentParser:
    from ratifact.informe import argumentos
    ap = argparse.ArgumentParser(prog="ratifact", description="Project memory MCP server (ratifact).")
    ap.add_argument("--version", action="version", version=f"ratifact {__version__}")
    sub = ap.add_subparsers(dest="comando", metavar="{serve,install,report,doctor,upgrade}")
    sub.required = True
    sub.add_parser("serve", help="run the MCP server over stdio (what the clients launch)")
    from ratifact.clientes import NOMBRES
    ins = sub.add_parser("install", help="configure the MCP clients found (Claude Desktop, Claude Code, Pi, Codex) "
                                         "and link /run-task; shows the plan unless --apply")
    modo_ins = ins.add_mutually_exclusive_group()
    modo_ins.add_argument("--apply", action="store_true", help="execute the plan (with backups)")
    modo_ins.add_argument("--dry-run", action="store_true", help="only show the plan (the default)")
    ins.add_argument("--client", choices=list(NOMBRES), help="configure only this client")
    argumentos(sub.add_parser("report", help="usage summary from the telemetry log"))
    sub.add_parser("doctor", help="read-only diagnosis of the installation; exit 1 if there are pending actions")
    up = sub.add_parser("upgrade", help="move memories to .ratifact/ and projects.json to English keys (ADR-029); "
                                        "shows the plan unless --apply")
    modo = up.add_mutually_exclusive_group()
    modo.add_argument("--apply", action="store_true", help="execute the plan (close every client first)")
    modo.add_argument("--dry-run", action="store_true", help="only show the plan (the default)")
    return ap


def main(argv: list[str] | None = None) -> None:
    a = _parser().parse_args(argv)
    if a.comando == "serve":
        servidor().run()
    elif a.comando == "report":
        from ratifact import informe
        informe.main(a=a)
    elif a.comando == "install":
        from ratifact import instalar
        sys.exit(instalar.main(aplicar=a.apply, cliente=a.client))
    elif a.comando == "doctor":
        from ratifact import doctor
        sys.exit(doctor.main())
    else:
        from ratifact import upgrade
        sys.exit(upgrade.main(aplicar=a.apply))


if __name__ == "__main__":
    main()
