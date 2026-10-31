"""Parts of `ratifact install` beyond the server entries (T-013): Claude Code permissions `mcp__memoria-proyectos__*` →
`mcp__ratifact__*` (same lists, v0 Spanish tool names translated), the generated CLAUDE.md/AGENTS.md block of the
registered projects (only the exact v1 text) and the /run-task links to the skills of
the installed package. Planning only reads; applying goes through ratifact.archivos."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ratifact.archivos import ErrorInstalacion, escribir_validado, leer_json, texto_json, validar_json
from ratifact.plantillas import PLANTILLA_AGENTES, PLANTILLA_AGENTES_V1
from ratifact.vocabulario import HERRAMIENTAS_V0

PREFIJO_VIEJO, PREFIJO = "mcp__memoria-proyectos", "mcp__ratifact"
LISTAS_PERMISOS = ("allow", "ask", "deny")
ARCHIVOS_BLOQUE = ("CLAUDE.md", "AGENTS.md")
SKILLS = ("run-task",)


@dataclass
class Cambio:
    """A text file to rewrite: path, new content and the description of each change."""
    ruta: Path
    texto: str | None = None
    cambios: list[str] = field(default_factory=list)
    error: str = ""
    en_repo: bool = False            # inside a project: the backup goes to the state dir, never next to it


# ───────────────────────── permissions ─────────────────────────

def _regla(regla: str) -> str:
    if regla == PREFIJO_VIEJO:
        return PREFIJO
    if regla.startswith(PREFIJO_VIEJO + "__"):
        herramienta = regla[len(PREFIJO_VIEJO) + 2:]
        return f"{PREFIJO}__{HERRAMIENTAS_V0.get(herramienta, herramienta)}"
    return regla


def migrar_permisos(datos: dict) -> tuple[dict, list[str]]:
    """Same settings with the rules renamed in place (a rule already present is not duplicated)."""
    permisos = datos.get("permissions")
    if not isinstance(permisos, dict):
        return datos, []
    nuevos, cambios = dict(permisos), []
    for lista in LISTAS_PERMISOS:
        reglas = permisos.get(lista)
        if not isinstance(reglas, list):
            continue
        salida: list = []
        for r in reglas:
            nueva = _regla(r) if isinstance(r, str) else r
            if nueva != r:
                cambios.append(f"{lista}: {r} → {nueva}" + (" (already present)" if nueva in reglas else ""))
            if nueva not in salida:
                salida.append(nueva)
        nuevos[lista] = salida
    if not cambios:
        return datos, []
    return {**datos, "permissions": nuevos}, cambios


def planificar_permisos(archivos: list[tuple[Path, bool]]) -> list[Cambio]:
    """(settings.json, is inside a project) → the files whose permissions change."""
    salida, vistos = [], set()
    for ruta, en_repo in archivos:
        if not ruta.is_file() or ruta.resolve() in vistos:
            continue
        vistos.add(ruta.resolve())
        try:
            nuevo, cambios = migrar_permisos(leer_json(ruta))
        except ErrorInstalacion as e:
            salida.append(Cambio(ruta, error=str(e), en_repo=en_repo))
            continue
        if cambios:
            salida.append(Cambio(ruta, texto_json(nuevo), cambios, en_repo=en_repo))
    return salida


# ───────────────────────── CLAUDE.md / AGENTS.md block ─────────────────────────

def planificar_bloques(proyectos: list[tuple[str, Path, list[str]]]) -> tuple[list[Cambio], list[str]]:
    """(name, code folder, repos) → (the files whose exact v1 block is replaced by the current one, manual steps for
    the files that still name the `memoria-proyectos` server in a text written by hand, never edited here)."""
    salida, manuales, vistos = [], [], set()
    for nombre, codigo, repos in proyectos:
        viejo, nuevo = PLANTILLA_AGENTES_V1.format(proyecto=nombre), PLANTILLA_AGENTES.format(proyecto=nombre)
        for carpeta in [codigo, *(codigo / r for r in repos)]:
            for archivo in ARCHIVOS_BLOQUE:
                ruta = carpeta / archivo
                if not ruta.is_file() or ruta.resolve() in vistos:
                    continue
                vistos.add(ruta.resolve())
                texto = ruta.read_text(encoding="utf-8")
                if viejo in texto:
                    salida.append(Cambio(ruta.resolve() if ruta.is_symlink() else ruta, texto.replace(viejo, nuevo),
                                         [f"{nombre}: project block → the `ratifact` MCP server"], en_repo=True))
                elif "memoria-proyectos" in texto.replace(nuevo, ""):      # a project may be named so
                    manuales.append(f"{ruta} mentions `memoria-proyectos` outside the generated block (written by "
                                    f"hand or before v1): replace it with the block of project_instructions(\"{nombre}\")")
    return salida, manuales


def aplicar_cambio(c: Cambio, json_: bool) -> str:
    if c.error:
        raise ErrorInstalacion(c.error)
    bak = escribir_validado(c.ruta, c.texto, validar_json if json_ else lambda t: None, en_estado=c.en_repo)
    return f"{c.ruta}: {'; '.join(c.cambios)}" + (f" (backup: {bak})" if bak else "")


# ───────────────────────── /run-task links ─────────────────────────

@dataclass
class Enlace:
    destino: Path
    objetivo: Path
    accion: str                  # create | replace | ok | skip
    previo: str = ""

    def describir(self) -> str:
        if self.accion == "skip":
            return (f"{self.destino} exists and is not a link: remove {self.destino} by hand and run "
                    "`ratifact install --apply` again")
        antes = f" (was → {self.previo})" if self.previo else ""
        return f"{'link' if self.accion == 'create' else 'relink'} /run-task: {self.destino} → {self.objetivo}{antes}"


def _destinos(home: Path, clientes: set[str]) -> list[tuple[Path, str, bool]]:
    """(link, skill, link the folder instead of SKILL.md). Codex only follows a linked folder, not a linked file."""
    salida = []
    for s in SKILLS:
        if "claude-code" in clientes:
            salida.append((home / ".claude" / "commands" / f"{s}.md", s, False))
            salida.append((home / ".claude" / "skills" / s, s, True))
        if "pi" in clientes:
            salida.append((home / ".pi" / "agent" / "prompts" / f"{s}.md", s, False))
            if (home / ".pi" / "agent" / "skills").is_dir():
                salida.append((home / ".pi" / "agent" / "skills" / s, s, True))
        if "codex" in clientes:       # depending on the version, Codex reads ~/.codex/skills or ~/.agents/skills
            salida += [(home / ".codex" / "skills" / s, s, True), (home / ".agents" / "skills" / s, s, True)]
    return salida


def planificar_enlaces(home: Path, skills: Path, clientes: set[str]) -> list[Enlace]:
    salida = []
    for destino, skill, carpeta in _destinos(home, clientes):
        objetivo = skills / skill if carpeta else skills / skill / "SKILL.md"
        if destino.is_symlink():
            previo = os.readlink(destino)
            igual = Path(previo) == objetivo
            salida.append(Enlace(destino, objetivo, "ok" if igual else "replace", "" if igual else previo))
        elif destino.exists():
            salida.append(Enlace(destino, objetivo, "skip"))
        else:
            salida.append(Enlace(destino, objetivo, "create"))
    return salida


def aplicar_enlace(e: Enlace) -> str:
    """Creates or replaces the link atomically (temporary link + os.replace); never touches a real file/folder."""
    if e.accion == "skip":
        raise ErrorInstalacion(e.describir())
    e.destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = e.destino.with_name(f".{e.destino.name}.ratifact-tmp")
    tmp.unlink(missing_ok=True)
    os.symlink(e.objetivo, tmp)
    if e.destino.exists() and not e.destino.is_symlink():
        tmp.unlink()
        raise ErrorInstalacion(f"{e.destino} appeared and is not a link; left alone.")
    os.replace(tmp, e.destino)
    return e.describir()


def proyectos_de(config: Path) -> list[tuple[str, dict]]:
    """Entries of projects.json (none if it does not exist or cannot be read)."""
    try:
        datos = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [(n, e) for n, e in datos.items() if isinstance(e, dict)] if isinstance(datos, dict) else []
