"""Herramientas de alta y mantenimiento de proyectos: init_memory, project_instructions, register_project y
update_project, con la detección del comando de pruebas."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ratifact.app import _ejecutar, herramienta
from ratifact.config import (BASE_PROYECTOS, CONFIG, MEM, _DIR, ErrorMemoria, _clave_escritura, _es_repo, _mem,
                             _pista_nombre, _proyectos, _raiz, _repos, _repos_de, _sugerencia_nombre, _valor)
from ratifact.esquema import ARCHIVO_ESQUEMA, IDIOMA_NUEVAS, _bloqueo, _escribir_esquema
from ratifact.integraciones.registro import _parsear_integraciones
from ratifact.plantillas import PLANTILLA_AGENTES, PLANTILLA_INSTRUCCIONES
from ratifact.registros import _commit, _escribir_atomico, _regenerar_vistas
from ratifact.vocabulario import CARPETAS_V1


@herramienta
def init_memory(project: str) -> str:
    """Creates the empty .project/ structure of a registered project (idempotent), in the current schema (v2:
    decisions/, pending/, sessions/, tasks/, content_language "en")."""
    proyecto = project

    def f():
        with _bloqueo(proyecto):
            mem = _mem(proyecto)
            for sub in CARPETAS_V1.values():
                (mem / sub).mkdir(parents=True, exist_ok=True)
            idx = mem / "INDEX.md"
            tocados = _regenerar_vistas(proyecto)
            if not idx.exists():
                _escribir_atomico(idx, f"# {proyecto}\n\n(Summary not written yet.)\n")
                tocados.append(idx)
            gi = mem / ".gitignore"
            _escribir_atomico(gi, ".lock\n*.tmp\n")
            tocados.append(gi)
            if not (mem / ARCHIVO_ESQUEMA).exists():
                tocados += _escribir_esquema(mem, IDIOMA_NUEVAS)
            if not _es_repo(mem):   # repo propio, independiente de la rama del código (ADR-010)
                subprocess.run(["git", "init", "-q", "-b", "main", str(mem)], capture_output=True)
                tocados = [p for p in mem.rglob("*") if p.is_file() and ".git" not in p.parts and p.name != ".lock"]
            return f"Memory initialized · commit {_commit(proyecto, tocados, 'inicializar memoria')}"
    return _ejecutar(f)


# ───────────────────────── alta de proyectos ─────────────────────────


def _detectar_pruebas(ruta: Path) -> str:
    """Propone el comando de pruebas según los archivos del proyecto. Vacío si no reconoce nada."""
    def hay(*nombres):
        return any((ruta / n).exists() for n in nombres)
    if hay("pom.xml"):
        return "./mvnw test" if hay("mvnw") else "mvn test"
    if hay("build.gradle", "build.gradle.kts"):
        return "./gradlew test" if hay("gradlew") else "gradle test"
    if hay("package.json"):
        try:
            if "test" not in json.loads((ruta / "package.json").read_text(encoding="utf-8")).get("scripts", {}):
                return ""
        except (ValueError, OSError):
            return ""
        return "pnpm test" if hay("pnpm-lock.yaml") else "yarn test" if hay("yarn.lock") else "npm test"
    if hay("project.godot"):
        runners = sorted(p.name for p in (ruta / "tests").glob("run_tests*.gd")) if hay("tests") else []
        return " && ".join(f"godot --headless --path . -s res://tests/{r}" for r in runners)
    if hay("Cargo.toml"):
        return "cargo test"
    if hay("go.mod"):
        return "go test ./..."
    if hay("pyproject.toml", "pytest.ini", "setup.cfg", "tests/conftest.py"):
        return "uv run pytest -q" if hay("uv.lock") else "python -m pytest -q"
    return ""


def _detectar_pruebas_proyecto(raiz: Path) -> str | dict:
    """Un comando para proyectos de un repo; un comando por repo en proyectos de varios repos."""
    if _es_repo(raiz) or _detectar_pruebas(raiz):
        return _detectar_pruebas(raiz)
    subrepos = sorted(d for d in raiz.iterdir() if d.is_dir() and _es_repo(d)) if raiz.is_dir() else []
    return {d.name: c for d in subrepos if (c := _detectar_pruebas(d))}


def _linea_pruebas(proyecto: str) -> str:
    cfg = _valor(_proyectos().get(proyecto, {}), "pruebas", "")
    if isinstance(cfg, dict) and cfg:
        return "\nTest commands per repository:\n" + "\n".join(f"- `{r}/`: `{c}`" for r, c in cfg.items())
    return (f"\nTest command (from the repository root): `{cfg}`" if cfg
            else "\nTest command: not configured (use update_project).")


def _instrucciones(proyecto: str) -> str:
    return (f"Instructions for project `{proyecto}`.\n\n"
            "1) Paste this into the Claude project instructions (Claude Desktop / claude.ai):\n\n"
            f"```\n{PLANTILLA_INSTRUCCIONES.format(proyecto=proyecto)}\n```\n\n"
            "2) Add this to the repository's CLAUDE.md (Claude Code) and AGENTS.md (Pi, Codex)"
            + (" — in a multi-repo project, in the root folder AND in each repo (Codex only reads AGENTS.md from the "
               "git repo root downwards)" if _repos(proyecto) else "") + ":\n\n"
            f"```\n{PLANTILLA_AGENTES.format(proyecto=proyecto)}{_linea_pruebas(proyecto)}\n```\n\n"
            f"3) Once per machine, so that `/run-task` exists in every project (Claude Code, Pi and Codex):\n\n"
            f"```\n{_enlaces_run_task()}\n```\n"
            "(Codex does not follow a SKILL.md linked as a file: the whole folder is linked. Depending on the version "
            "it reads ~/.codex/skills or ~/.agents/skills; it is installed in both. If a run-task/ folder already "
            "exists there, delete it first.)")


def _enlaces_run_task() -> str:
    """Comandos para enlazar /run-task (y el alias deprecado /tarea, hasta 1.1) en Claude Code, Pi y Codex."""
    return (f"mkdir -p ~/.claude/commands ~/.pi/agent/prompts ~/.codex/skills ~/.agents/skills\n"
            f"ln -sf {_DIR / 'run-task.md'} ~/.claude/commands/run-task.md\n"
            f"ln -sf {_DIR / 'run-task.md'} ~/.pi/agent/prompts/run-task.md\n"
            f"ln -sfn {_DIR / 'skills' / 'run-task'} ~/.codex/skills/run-task\n"
            f"ln -sfn {_DIR / 'skills' / 'run-task'} ~/.agents/skills/run-task")


@herramienta
def project_instructions(project: str) -> str:
    """Returns, ready to copy, the Claude project instructions and the CLAUDE.md/AGENTS.md block with the right
    project name. Give them to the user as they are, without summarizing."""
    def f():
        _raiz(project)   # valida que exista
        return _instrucciones(project)
    return _ejecutar(f)


def _validar_ruta_proyecto(ruta: str, mem: Path, alta: bool = False) -> Path:
    """Valida una ruta de código candidata, para alta (registrar_proyecto) o corrección (actualizar_proyecto):
    debe quedar dentro de la carpeta de proyectos, ser una carpeta existente, y no contener la memoria (ADR-010).
    `alta=True` usa la redacción de registrar_proyecto para el choque con la memoria (todavía no hay memoria
    elegida, se puede omitir `memoria`); `alta=False` (actualizar_proyecto) usa la redacción de corrección
    (la memoria ya existe en otro lado y moverla no está soportado aquí)."""
    r = Path(ruta).expanduser().resolve()
    if r != BASE_PROYECTOS and BASE_PROYECTOS not in r.parents:
        raise ErrorMemoria(f"The path must be inside {BASE_PROYECTOS}.")
    if not r.is_dir():
        raise ErrorMemoria(f"Folder {r} does not exist.")
    if mem == r or r in mem.parents:
        if alta:
            raise ErrorMemoria("The memory cannot live inside the code repository (ADR-010); "
                               "omit `memory` to use .memorias/<name>.")
        raise ErrorMemoria("The memory cannot live inside the code repository (ADR-010); "
                           "choose another path (moving an existing project's memory is not supported here).")
    return r


@herramienta
def register_project(name: str, path: str, memory: str = "", tests: str = "") -> str:
    """Registers a project: adds it to projects.json, initializes its memory (its own git repo) and returns the
    instructions to paste into Claude and into CLAUDE.md/AGENTS.md. `path`: the code folder (must exist inside the
    projects folder). `memory`: optional; by default <projects folder>/.memorias/<name>, outside the code
    repository. `tests`: command to run the tests; if omitted it is detected (Maven, Gradle, npm/pnpm/yarn, Godot,
    pytest, cargo, go). Only with the user's confirmation."""
    nombre, ruta, memoria, pruebas = name, path, memory, tests

    def f():
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", nombre):
            raise ErrorMemoria("Invalid name: lowercase letters, digits, '-' and '_' (2–41 characters).")
        proyectos = _proyectos() if CONFIG.exists() else {}
        if nombre in proyectos:
            raise ErrorMemoria(f"'{nombre}' is already registered. Use project_instructions('{nombre}').")
        m = Path(memoria).expanduser().resolve() if memoria else BASE_PROYECTOS / ".memorias" / nombre
        if m != BASE_PROYECTOS and BASE_PROYECTOS not in m.parents:
            raise ErrorMemoria(f"The memory must be inside {BASE_PROYECTOS}.")
        r = _validar_ruta_proyecto(ruta, m, alta=True)
        anterior = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else None
        # grafía de las claves: la de la primera entrada existente (español si el archivo está vacío)
        modelo = next(iter(proyectos.values()), {})
        valores = {"ruta": str(r), "memoria": str(m), "escritura": [MEM, "docs"],
                   "pruebas": pruebas.strip() or _detectar_pruebas_proyecto(r)}
        proyectos[nombre] = {_clave_escritura(modelo, k): v for k, v in valores.items()}
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _escribir_atomico(CONFIG, json.dumps(proyectos, indent=2, ensure_ascii=False) + "\n")
        resultado = init_memory(project=nombre)
        if resultado.startswith("ERROR") or "git failed" in resultado:
            if anterior is None:     # deshacer el alta: no dejar proyectos a medio registrar
                CONFIG.unlink()
            else:
                _escribir_atomico(CONFIG, anterior)
            raise ErrorMemoria(f"Could not initialize the memory; registration reverted. {resultado}")
        aviso = "" if _es_repo(r) else ("\n⚠ The code folder is not a git repository: documents in docs/ will "
                                        "not be versioned until you run `git init`.")
        repos = _repos(nombre)
        if repos:
            aviso = (f"\nMulti-repo project: {', '.join(repos)}. Each task says which one it works in; add the "
                     "block below to the CLAUDE.md/AGENTS.md of the root and of each repo."
                     + ("" if _es_repo(r) else " The root folder is not a repo: what is saved in its docs/ is "
                        "not versioned (use <repo>/docs/ or the memory)."))
        return f"{resultado}{aviso}\n\n{_instrucciones(nombre)}"
    return _ejecutar(f)


@herramienta
def update_project(name: str, path: str = "", tests: str = "", repo: str = "", redetect: bool = False,
                   integrations: str = "") -> str:
    """Updates a project already registered in projects.json without editing it by hand. Give at least one of
    `path`, `tests`, `repo`, `redetect=True` or `integrations`; with none, it returns an error and leaves the file
    untouched.
    `path`: new code folder, when it moved. Same checks as register_project (inside the projects folder, an
    existing folder, and not containing the project's memory — ADR-010). If the project is multi-repo and the stored
    `tests` keeps keys that are no longer repos under the new path, the change is applied anyway but the response
    lists them and suggests `redetect=True`.
    `tests`: command the coding agent uses to verify tasks (/run-task). In multi-repo projects, `repo` says which
    repo it applies to.
    `redetect`: True to detect the command again from the project files instead of giving it with `tests` (both at
    once are incompatible). In a single-repo project it redetects the whole command; in a multi-repo one it
    redetects all repos, or only `repo` if given.
    `integrations`: turns optional integrations of the project on or off, e.g. "codegraph=off,gentle-ai=auto"
    (values auto|off; default auto: used when detected). One turned off never appears in any response."""
    nombre, ruta, pruebas, repositorio, redetectar, integraciones = name, path, tests, repo, redetect, integrations

    def f():
        proyectos = _proyectos()
        if nombre not in proyectos:
            raise ErrorMemoria(f"Project '{nombre}' is not registered."
                               f"{_pista_nombre(_sugerencia_nombre(nombre, proyectos), proyectos)}")
        if not (ruta.strip() or pruebas.strip() or repositorio.strip() or redetectar or integraciones.strip()):
            raise ErrorMemoria("Nothing to update: give `path`, `tests`, `repo`, `redetect=True` or "
                               "`integrations`.")
        if redetectar and pruebas.strip():
            raise ErrorMemoria("`redetect` and `tests` are incompatible: asking to redetect the command and giving "
                               "it at the same time makes no sense; use one of them.")

        cambios = []
        raiz = None
        if ruta.strip():
            mem = _mem(nombre)
            anterior = _valor(proyectos[nombre], "ruta")
            raiz = _validar_ruta_proyecto(ruta.strip(), mem)
            proyectos[nombre][_clave_escritura(proyectos[nombre], "ruta")] = str(raiz)
            cambios.append(f"path: {anterior} → {raiz}")

        if pruebas.strip() or repositorio.strip() or redetectar:
            if raiz is None:
                raiz = _raiz(nombre)
            repos = _repos_de(raiz)
            actual = _valor(proyectos[nombre], "pruebas", "")
            repo = repositorio.strip()
            if repo:
                if repo not in repos:
                    raise ErrorMemoria(f"'{repo}' is not a repository of the project. "
                                       f"Available: {', '.join(repos) or '(none)'}")
                cmd = pruebas.strip() or _detectar_pruebas(raiz / repo)
                if not cmd:
                    raise ErrorMemoria("Unrecognized repository type; give the command explicitly.")
                nuevo = dict(actual) if isinstance(actual, dict) else {}
                nuevo[repo] = cmd
                descripcion = f"`{repo}/`: `{cmd}`"
            else:
                if repos and pruebas.strip():
                    raise ErrorMemoria(f"Multi-repo project: give `repo` ({', '.join(repos)}).")
                nuevo = pruebas.strip() or _detectar_pruebas_proyecto(raiz)
                if not nuevo:
                    raise ErrorMemoria("Unrecognized project type; give the command explicitly.")
                descripcion = (", ".join(f"`{r}/`: `{c}`" for r, c in nuevo.items()) if isinstance(nuevo, dict)
                               else f"`{nuevo}`")
            proyectos[nombre][_clave_escritura(proyectos[nombre], "pruebas")] = nuevo
            cambios.append(f"tests {descripcion}" + ("" if pruebas.strip() else " (detected)"))

        if ruta.strip():
            pruebas_final = _valor(proyectos[nombre], "pruebas", "")
            if isinstance(pruebas_final, dict):
                vigentes = _repos_de(raiz)
                huerfanas = sorted(k for k in pruebas_final if k not in vigentes)
                if huerfanas:
                    cambios.append(f"⚠ orphan tests (no repo under the new path): {', '.join(huerfanas)}; "
                                   f"use update_project('{nombre}', redetect=True) to regenerate them.")

        if integraciones.strip():
            nuevas, descripcion = _parsear_integraciones(integraciones, proyectos[nombre].get("integraciones"))
            if nuevas:
                proyectos[nombre]["integraciones"] = nuevas
            else:
                proyectos[nombre].pop("integraciones", None)
            cambios.append(f"integrations: {descripcion}")

        _escribir_atomico(CONFIG, json.dumps(proyectos, indent=2, ensure_ascii=False) + "\n")
        mensaje = f"'{nombre}' updated:\n" + "\n".join(f"- {c}" for c in cambios)
        if pruebas.strip() or repositorio.strip() or redetectar:
            mensaje += ("\n\nUpdated block for CLAUDE.md/AGENTS.md (replaces the previous one):\n\n"
                       f"```\n{PLANTILLA_AGENTES.format(proyecto=nombre)}{_linea_pruebas(nombre)}\n```")
        return mensaje
    return _ejecutar(f)
