"""MCP clients that `ratifact install` configures and `ratifact doctor` reports (T-013): Claude Desktop, Claude Code
(`claude mcp add --scope user` if the `claude` executable exists, otherwise ~/.claude.json), Pi and Codex. Each ends with
the server key `ratifact`, the absolute path of the installed executable, args ["serve"] and no environment variables;
an old `memoria-proyectos` entry is replaced (never both). Planning only reads; `aplicar` writes through
ratifact.archivos (validation, backup, atomic replace)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ratifact import clientes_toml
from ratifact.archivos import ErrorInstalacion, escribir_validado, leer_json, respaldar, texto_json

CLAVE, CLAVE_VIEJA = clientes_toml.CLAVE, clientes_toml.CLAVE_VIEJA
CONFIGURADO, VIEJA = "configured with ratifact", "old configuration"
SIN_CONFIGURAR, NO_ENCONTRADO = "not configured", "not found"
NOMBRES = {"claude-desktop": "Claude Desktop", "claude-code": "Claude Code", "pi": "Pi", "codex": "Codex"}
_BUSCAR = object()

__all__ = ["ErrorInstalacion", "clientes", "planificar", "aplicar"]


@dataclass
class Cliente:
    nombre: str
    archivo: Path
    encontrado: bool
    formato: str = "json"                   # json | toml
    cli: str | None = None                  # Claude Code: the `claude` executable, if it exists

    @property
    def titulo(self) -> str:
        return NOMBRES[self.nombre]


def _carpeta_desktop(home: Path) -> Path:
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude"
    return home / ".config" / "Claude"


def clientes(claude=_BUSCAR) -> list[Cliente]:
    """The four clients, with whether they are installed on this machine (read at every call, from HOME)."""
    home = Path.home()
    claude = shutil.which("claude") if claude is _BUSCAR else claude
    desktop = _carpeta_desktop(home)
    return [
        Cliente("claude-desktop", desktop / "claude_desktop_config.json", desktop.is_dir()),
        Cliente("claude-code", home / ".claude.json",
                bool(claude) or (home / ".claude.json").exists() or (home / ".claude").is_dir(), cli=claude),
        Cliente("pi", home / ".pi" / "agent" / "mcp.json", (home / ".pi" / "agent").is_dir()),
        Cliente("codex", home / ".codex" / "config.toml", (home / ".codex").is_dir(), formato="toml"),
    ]


@dataclass
class PlanCliente:
    cliente: Cliente
    estado: str
    error: str = ""
    texto: str | None = None                # new content of the file (edit by file)
    comandos: list[list[str]] = field(default_factory=list)      # `claude …` calls (edit by CLI)
    descripcion: str = ""
    ejecutable: str = ""

    @property
    def cambia(self) -> bool:
        return self.texto is not None or bool(self.comandos)


def estado_servidores(servidores, exe: str | None) -> str:
    if not isinstance(servidores, dict):
        return SIN_CONFIGURAR
    if CLAVE_VIEJA in servidores:
        return VIEJA
    e = servidores.get(CLAVE)
    if e is None:
        return SIN_CONFIGURAR
    ok = isinstance(e, dict) and e.get("args") == ["serve"] and not e.get("env") and (
        e.get("command") == exe if exe else Path(str(e.get("command"))).name == "ratifact")
    return CONFIGURADO if ok else VIEJA


def _servidores(c: Cliente, datos: dict):
    return datos.get("mcp_servers" if c.formato == "toml" else "mcpServers")


def leer(c: Cliente) -> tuple[dict, str]:
    """(parsed data, original text). ErrorInstalacion if the file cannot be parsed."""
    if c.formato == "toml":
        texto = c.archivo.read_text(encoding="utf-8") if c.archivo.exists() else ""
        return clientes_toml.parsear(texto, str(c.archivo)), texto
    return leer_json(c.archivo), c.archivo.read_text(encoding="utf-8") if c.archivo.exists() else ""


def estado(c: Cliente, exe: str | None = None) -> str:
    """configured with ratifact / old configuration / not configured / not found / error: … (doctor)."""
    if not c.encontrado:
        return NO_ENCONTRADO
    try:
        datos, _ = leer(c)
    except ErrorInstalacion as e:
        return f"error: {e}"
    return estado_servidores(_servidores(c, datos), exe)


def _entrada_json(c: Cliente, servidores: dict, exe: str) -> dict:
    fuente = servidores.get(CLAVE) if CLAVE in servidores else servidores.get(CLAVE_VIEJA) or {}
    extra = {k: v for k, v in (fuente if isinstance(fuente, dict) else {}).items()
             if k not in ("type", "command", "args", "env")}
    return {**({"type": "stdio"} if c.nombre == "claude-code" else {}), "command": exe, "args": ["serve"], **extra}


def _reemplazar_json(c: Cliente, datos: dict, exe: str) -> dict:
    """Same data with `ratifact` where the first of ratifact / memoria-proyectos was (or at the end)."""
    servidores = datos.get("mcpServers") or {}
    entrada, nuevos = _entrada_json(c, servidores, exe), {}
    for k, v in servidores.items():
        if k in (CLAVE, CLAVE_VIEJA):
            nuevos.setdefault(CLAVE, entrada)
        else:
            nuevos[k] = v
    nuevos.setdefault(CLAVE, entrada)
    salida = dict(datos)
    salida["mcpServers"] = nuevos
    return salida


def _descripcion(estado_actual: str, servidores) -> str:
    if estado_actual == SIN_CONFIGURAR:
        return f"add `{CLAVE}`"
    if isinstance(servidores, dict) and CLAVE_VIEJA in servidores:
        return f"replace `{CLAVE_VIEJA}` with `{CLAVE}`"
    return f"update `{CLAVE}` (command, args [\"serve\"], no env)"


def planificar(c: Cliente, exe: str) -> PlanCliente:
    """What `aplicar` would do for this client. Never writes."""
    if not c.encontrado:
        return PlanCliente(c, NO_ENCONTRADO, ejecutable=exe)
    try:
        datos, texto = leer(c)
        servidores = _servidores(c, datos)
        if servidores is not None and not isinstance(servidores, dict):
            raise ErrorInstalacion(f"{c.archivo}: the servers entry is not a table/object; nothing was changed.")
        actual = estado_servidores(servidores, exe)
        if actual == CONFIGURADO:
            return PlanCliente(c, actual, ejecutable=exe)
        plan = PlanCliente(c, actual, descripcion=_descripcion(actual, servidores), ejecutable=exe)
        if c.formato == "toml":
            plan.texto = clientes_toml.editar(texto, exe)
        elif c.cli:
            servidores = servidores or {}
            plan.comandos = [["mcp", "remove", k, "--scope", "user"] for k in (CLAVE_VIEJA, CLAVE) if k in servidores]
            plan.comandos.append(["mcp", "add", "--scope", "user", CLAVE, "--", exe, "serve"])
            plan.descripcion += " via `claude mcp add --scope user`"
        else:
            plan.texto = texto_json(_reemplazar_json(c, datos, exe))
        return plan
    except ErrorInstalacion as e:
        return PlanCliente(c, f"error: {e}", error=str(e), ejecutable=exe)
    except OSError as e:
        return PlanCliente(c, f"error: {e}", error=f"cannot read {c.archivo}: {e}", ejecutable=exe)


def _validador(c: Cliente, exe: str) -> Callable[[str], None]:
    def validar(texto: str) -> None:
        if c.formato == "toml":
            datos = clientes_toml.parsear(texto, f"the new {c.archivo.name}")
        else:
            try:
                datos = json.loads(texto)
            except ValueError as e:
                raise ErrorInstalacion(f"the new {c.archivo.name} does not parse ({e}); nothing was changed.")
        if estado_servidores(_servidores(c, datos), exe) != CONFIGURADO:
            raise ErrorInstalacion(f"the new {c.archivo.name} does not have the expected `{CLAVE}` entry; "
                                   "nothing was changed.")
    return validar


def aplicar(plan: PlanCliente, correr: Callable = subprocess.run) -> str:
    """Executes the plan of one client; returns the summary line. ErrorInstalacion if it cannot."""
    c = plan.cliente
    if plan.error:
        raise ErrorInstalacion(plan.error)
    if not plan.cambia:
        return f"{c.titulo}: {plan.estado}"
    if plan.texto is not None:
        bak = escribir_validado(c.archivo, plan.texto, _validador(c, plan.ejecutable))
        return f"{c.titulo}: {plan.descripcion} in {c.archivo}" + (f" (backup: {bak})" if bak else "")
    bak = respaldar(c.archivo)
    for args in plan.comandos:
        r = correr([c.cli, *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise ErrorInstalacion(f"`claude {' '.join(args)}` failed: {(r.stderr or r.stdout).strip()[:300]}"
                                   + (f" (backup of {c.archivo}: {bak})" if bak else ""))
    final = estado(c, plan.ejecutable)
    if final != CONFIGURADO:
        raise ErrorInstalacion(f"after `claude mcp add`, {c.archivo} is in state '{final}'"
                               + (f" (backup: {bak})" if bak else ""))
    return f"{c.titulo}: {plan.descripcion}" + (f" (backup: {bak})" if bak else "")
