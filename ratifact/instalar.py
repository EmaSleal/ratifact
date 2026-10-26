"""`ratifact install` (ADR-032, T-013): configures the MCP clients found on this machine so nobody edits their files by
hand. Without `--apply` it only shows the plan. With `--apply`: (1) creates an empty ~/.config/ratifact/projects.json
if there is no configuration at all; (2) writes the `ratifact` server entry of Claude Desktop, Claude Code, Pi and Codex
(ratifact.clientes); (3) renames the Claude Code permissions and (4) the generated CLAUDE.md/AGENTS.md block of the
registered projects; (5) links /run-task (and /tarea until 1.1) to the installed package. It lists what cannot be done
automatically and reports the integrations per project without asking (ADR-025). Idempotent."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ratifact import clientes as cl
from ratifact import instalar_extras as ex
from ratifact import rutas
from ratifact.build import RECORDATORIO
from ratifact.archivos import ErrorInstalacion, escribir_validado, validar_json
from ratifact.config import _ruta_config, _valor
from ratifact.instalacion import Proceso, _integraciones, mensaje_sugerencia, procesos_servidor, sugerencias_config

_BUSCAR = cl._BUSCAR
APROBACIONES = ("propose_decision", "add_pending", "create_task", "create_document", "register_project",
                "accept_decision", "accept_decisions")


def _efimero(ruta: Path) -> bool:
    """An executable inside the uv cache (`uvx ratifact …`) disappears: clients cannot run it."""
    return any(p.startswith("archive-v") for p in ruta.parts) or "/.cache/uv/" in str(ruta)


def ejecutable_instalado() -> tuple[str | None, str]:
    """(absolute path of the installed `ratifact`, problem). The PATH entry (e.g. ~/.local/bin/ratifact) is kept as is:
    it survives `uv tool install --reinstall`."""
    candidatos = [shutil.which("ratifact"), sys.argv[0] if Path(sys.argv[0]).name == "ratifact" else None]
    for c in filter(None, candidatos):
        ruta = Path(c).absolute()
        if not _efimero(ruta):
            return str(ruta), ""
    return None, ("there is no fixed installation of `ratifact` (an executable run by `uvx` lives in the uv cache "
                  "and disappears): run `uv tool install ratifact` (or `uv tool install <repo>`), then "
                  "`ratifact install --apply`")


@dataclass
class Plan:
    ejecutable: str | None
    bloqueo: str = ""                                       # why --apply cannot run at all
    config: Path | None = None                              # projects.json to create
    avisos: list[str] = field(default_factory=list)
    clientes: list[cl.PlanCliente] = field(default_factory=list)
    permisos: list[ex.Cambio] = field(default_factory=list)
    bloques: list[ex.Cambio] = field(default_factory=list)
    enlaces: list[ex.Enlace] = field(default_factory=list)
    manuales: list[str] = field(default_factory=list)
    integraciones: list[str] = field(default_factory=list)

    @property
    def pendientes(self) -> list:
        return ([self.config] if self.config else []) + [c for c in self.clientes if c.cambia] + \
            self.permisos + self.bloques + [e for e in self.enlaces if e.accion in ("create", "replace")]

    @property
    def vacio(self) -> bool:
        return not self.pendientes and not any(c.error for c in self.clientes)


def _config_a_crear(procesos: list[Proceso], plan: Plan) -> None:
    if os.environ.get("RATIFACT_CONFIG") or os.environ.get("MEMORIA_PROYECTOS_CONFIG") or rutas.config_nueva().exists():
        return
    if rutas.config_vieja().exists():
        plan.avisos.append(f"{rutas.config_vieja()} is the configuration of memoria-proyectos: run `ratifact upgrade` "
                           "to move it to English keys (it is not created again here)")
        return
    sugerencia = mensaje_sugerencia(sugerencias_config(procesos, rutas.origen()))
    if sugerencia:
        plan.avisos.append(sugerencia)
    else:
        plan.config = rutas.config_nueva()


def _manuales(plan: Plan) -> None:
    for c in plan.clientes:
        if c.cliente.nombre == "claude-desktop" and c.estado == cl.VIEJA:
            plan.manuales.append("Claude Desktop keeps tool approvals per server name: in Settings → Connectors → "
                                 f"ratifact, mark {', '.join(APROBACIONES)} as 'requires approval' again and leave "
                                 "the rest as 'always allow'")
        if c.error:
            plan.manuales.append(f"{c.cliente.titulo}: {c.error}")
    if any(c.cliente.nombre == "claude-code" for c in plan.clientes):
        try:
            datos = cl.leer_json(Path.home() / ".claude.json")
        except ErrorInstalacion:
            datos = {}
        for carpeta, p in (datos.get("projects") or {}).items():
            if isinstance(p, dict) and cl.CLAVE_VIEJA in (p.get("mcpServers") or {}):
                plan.manuales.append(f"Claude Code has a project-scoped `{cl.CLAVE_VIEJA}` server in {carpeta}: run "
                                     f"`claude mcp remove {cl.CLAVE_VIEJA} --scope local` there")
    plan.manuales += [e.describir() for e in plan.enlaces if e.accion == "skip"]
    plan.manuales += [f"{c.ruta}: {c.error}" for c in plan.permisos if c.error]


def _integraciones_informe(proyectos: list[tuple[str, dict]]) -> list[str]:
    lineas = []
    for nombre, entrada in proyectos:
        ruta = _valor(entrada, "ruta")
        detectadas = _integraciones(entrada, Path(ruta).expanduser().resolve()) if ruta else []
        lineas.append(f"{nombre}: {', '.join(detectadas) or 'none detected'}")
    return lineas


def planificar(ejecutable: str | None, paquete: Path, claude=_BUSCAR, cliente: str | None = None,
               procesos: Callable[[], list[Proceso]] = procesos_servidor, problema: str = "") -> Plan:
    """What --apply would do. Never writes."""
    from ratifact.config import _repos_de
    plan = Plan(ejecutable)
    if not ejecutable:
        plan.bloqueo = problema or "the `ratifact` executable was not found"
    elif rutas.es_copia_de_trabajo(paquete):
        plan.bloqueo = (f"this command runs from the working copy {paquete.parent} (P-017): the links would point to "
                        f"it; run the installed one instead: `{ejecutable} install --apply`")
    _config_a_crear(procesos(), plan)
    elegidos = [c for c in cl.clientes(claude=claude) if cliente in (None, c.nombre)]
    plan.clientes = [cl.planificar(c, ejecutable or "<ratifact executable>") for c in elegidos]
    encontrados = {c.nombre for c in elegidos if c.encontrado}
    proyectos = ex.proyectos_de(_ruta_config())
    codigos = [(n, Path(_valor(e, "ruta")).expanduser().resolve()) for n, e in proyectos if _valor(e, "ruta")]
    if "claude-code" in encontrados:
        plan.permisos = ex.planificar_permisos([(Path.home() / ".claude" / "settings.json", False),
                                                *((c / ".claude" / "settings.json", True) for _, c in codigos)])
    plan.bloques, bloques_a_mano = ex.planificar_bloques([(n, c, _repos_de(c) if c.is_dir() else [])
                                                          for n, c in codigos])
    plan.enlaces = ex.planificar_enlaces(Path.home(), paquete / "skills", encontrados)
    _manuales(plan)
    plan.manuales += bloques_a_mano
    plan.integraciones = _integraciones_informe(proyectos)
    return plan


def describir(plan: Plan) -> list[str]:
    lineas = [f"Executable: {plan.ejecutable or 'not found'}"]
    if plan.config:
        lineas.append(f"Configuration: create {plan.config} (empty; projects are written with English keys)")
    lineas.append("Clients:")
    for c in plan.clientes:
        if c.estado == cl.NO_ENCONTRADO:
            lineas.append(f"  {c.cliente.titulo}: not found (skipped)")
        elif c.error:
            lineas.append(f"  {c.cliente.titulo}: {c.estado}")
        else:
            lineas.append(f"  {c.cliente.titulo}: {c.estado}" + (f" → {c.descripcion} ({c.cliente.archivo})"
                                                                 if c.cambia else ""))
    if plan.permisos:
        lineas.append("Claude Code permissions:")
        lineas += [f"  {c.ruta}: {'; '.join(c.cambios)}" for c in plan.permisos if not c.error]
    if plan.bloques:
        lineas.append("Project block in CLAUDE.md/AGENTS.md (now \"the `ratifact` MCP server\"):")
        lineas += [f"  {c.ruta}" for c in plan.bloques]
    cambian = [e for e in plan.enlaces if e.accion in ("create", "replace")]
    if cambian:
        lineas.append("/run-task links (and the /tarea alias until 1.1):")
        lineas += [f"  {e.describir()}" for e in cambian]
    return lineas


def _final(plan: Plan) -> list[str]:
    lineas = [f"Note: {a}" for a in plan.avisos]
    if plan.manuales:
        lineas.append("Manual steps (cannot be done automatically):")
        lineas += [f"  - {m}" for m in plan.manuales]
    lineas.append("Integrations per project (detected, default auto; never asked — ADR-025):")
    lineas += [f"  {l}" for l in plan.integraciones] or ["  (no registered projects)"]
    lineas += ["  engram is never detected: its guidance is conditional (used only if you have it).",
               '  Turn one off with update_project("<project>", integrations="codegraph=off").']
    return lineas


def _respaldos() -> str:
    return (f"Backups: client files as <file>.bak-ratifact-<date> next to them; files inside a project (CLAUDE.md, "
            f"AGENTS.md, .claude/settings.json) under {rutas.respaldos()}/<date>/<absolute path>, never in the "
            "repository. Files that are not rewritten get no backup.")


def _crear_config(ruta: Path) -> str:
    escribir_validado(ruta, "{}\n", validar_json)
    return f"created {ruta} (empty)"


def ejecutar(plan: Plan, correr: Callable = subprocess.run) -> tuple[list[str], list[str]]:
    """(done, failed). Each part is independent: an error in one client does not stop the others."""
    hecho, fallos = [], []

    def paso(accion: Callable[[], str]) -> None:
        try:
            hecho.append(accion())
        except (ErrorInstalacion, OSError) as e:
            fallos.append(str(e))
    if plan.config:
        paso(lambda: _crear_config(plan.config))
    for c in plan.clientes:
        if c.cambia or c.error:
            paso(lambda c=c: cl.aplicar(c, correr))
    for c in plan.permisos:
        paso(lambda c=c: ex.aplicar_cambio(c, json_=True))
    for c in plan.bloques:
        paso(lambda c=c: ex.aplicar_cambio(c, json_=False))
    for e in plan.enlaces:
        if e.accion in ("create", "replace"):
            paso(lambda e=e: ex.aplicar_enlace(e))
    return hecho, fallos


def main(aplicar: bool = False, cliente: str | None = None, ejecutable=_BUSCAR, paquete: Path | None = None,
         claude=_BUSCAR, correr: Callable = subprocess.run,
         procesos: Callable[[], list[Proceso]] = procesos_servidor) -> int:
    problema = ""
    if ejecutable is _BUSCAR:
        ejecutable, problema = ejecutable_instalado()
    paquete = paquete or Path(__file__).resolve().parent
    plan = planificar(ejecutable, paquete, claude, cliente, procesos, problema)
    print("ratifact install" + ("" if aplicar else " (plan; nothing is changed without --apply)"))
    for linea in describir(plan):
        print(linea)
    if plan.vacio:
        print("\n".join(_final(plan)))
        print("Nothing to do: everything is already installed.")
        return 0
    if not aplicar:
        print("\n".join(_final(plan)))
        print("Dry run: nothing was changed. Run `ratifact install --apply` to do it.")
        print(_respaldos())
        return 1 if any(c.error for c in plan.clientes) else 0
    if plan.bloqueo:
        print(f"Aborted — nothing was changed: {plan.bloqueo}")
        return 1
    hecho, fallos = ejecutar(plan, correr)
    if hecho:
        print("Done:")
        print("\n".join(f"  {l}" for l in hecho))
        print(_respaldos())
    if fallos:
        print("Failed (left untouched):")
        print("\n".join(f"  - {f}" for f in fallos))
    print("\n".join(_final(plan)))
    print(RECORDATORIO)
    return 1 if fallos else 0
