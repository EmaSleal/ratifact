"""Herramientas de alta y mantenimiento de proyectos: inicializar_memoria, instrucciones_proyecto,
registrar_proyecto y actualizar_proyecto, con la detección del comando de pruebas."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ratifact.app import _ejecutar, herramienta
from ratifact.config import (BASE_PROYECTOS, CONFIG, MEM, _DIR, ErrorMemoria, _clave_escritura, _es_repo, _mem,
                             _proyectos, _raiz, _repos, _repos_de, _sugerencia_nombre, _valor)
from ratifact.esquema import ARCHIVO_ESQUEMA, IDIOMA_NUEVAS, _bloqueo, _escribir_esquema
from ratifact.integraciones.registro import _parsear_integraciones
from ratifact.plantillas import PLANTILLA_AGENTES, PLANTILLA_INSTRUCCIONES
from ratifact.registros import _commit, _escribir_atomico, _regenerar_vistas
from ratifact.vocabulario import CARPETAS_V1


@herramienta
def inicializar_memoria(proyecto: str) -> str:
    """Crea la estructura .project/ vacía de un proyecto registrado (idempotente), en el esquema actual (v2:
    decisions/, pending/, sessions/, tasks/, content_language "en")."""
    def f():
        with _bloqueo(proyecto):
            mem = _mem(proyecto)
            for sub in CARPETAS_V1.values():
                (mem / sub).mkdir(parents=True, exist_ok=True)
            idx = mem / "INDEX.md"
            tocados = _regenerar_vistas(proyecto)
            if not idx.exists():
                _escribir_atomico(idx, f"# {proyecto}\n\n(Resumen pendiente de redactar.)\n")
                tocados.append(idx)
            gi = mem / ".gitignore"
            _escribir_atomico(gi, ".lock\n*.tmp\n")
            tocados.append(gi)
            if not (mem / ARCHIVO_ESQUEMA).exists():
                tocados += _escribir_esquema(mem, IDIOMA_NUEVAS)
            if not _es_repo(mem):   # repo propio, independiente de la rama del código (ADR-010)
                subprocess.run(["git", "init", "-q", "-b", "main", str(mem)], capture_output=True)
                tocados = [p for p in mem.rglob("*") if p.is_file() and ".git" not in p.parts and p.name != ".lock"]
            return f"Memoria inicializada · commit {_commit(proyecto, tocados, 'inicializar memoria')}"
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
        return "\nComandos de pruebas por repositorio:\n" + "\n".join(f"- `{r}/`: `{c}`" for r, c in cfg.items())
    return (f"\nComando de pruebas (desde la raíz del repositorio): `{cfg}`" if cfg
            else "\nComando de pruebas: sin configurar (usa actualizar_proyecto).")


def _instrucciones(proyecto: str) -> str:
    return (f"Instrucciones para el proyecto `{proyecto}`.\n\n"
            "1) Pega esto en las instrucciones del proyecto de Claude (Claude Desktop / claude.ai):\n\n"
            f"```\n{PLANTILLA_INSTRUCCIONES.format(proyecto=proyecto)}\n```\n\n"
            "2) Agrega esto al CLAUDE.md (Claude Code) y al AGENTS.md (Pi, Codex) del repositorio"
            + (" — en un proyecto de varios repos, en la carpeta raíz Y en cada repo (Codex solo lee el AGENTS.md "
               "desde la raíz del repo git hacia abajo)" if _repos(proyecto) else "") + ":\n\n"
            f"```\n{PLANTILLA_AGENTES.format(proyecto=proyecto)}{_linea_pruebas(proyecto)}\n```\n\n"
            "3) Una sola vez por equipo, para que `/tarea` exista en todos los proyectos (Claude Code, Pi y Codex):\n\n"
            f"```\nmkdir -p ~/.claude/commands ~/.pi/agent/prompts ~/.codex/skills ~/.agents/skills\n"
            f"ln -sf {_DIR / 'tarea.md'} ~/.claude/commands/tarea.md\n"
            f"ln -sf {_DIR / 'tarea.md'} ~/.pi/agent/prompts/tarea.md\n"
            f"ln -sfn {_DIR / 'skills' / 'tarea'} ~/.codex/skills/tarea\n"
            f"ln -sfn {_DIR / 'skills' / 'tarea'} ~/.agents/skills/tarea\n```\n"
            "(Codex no sigue un SKILL.md enlazado como archivo: se enlaza la carpeta completa. Según la versión, "
            "lee ~/.codex/skills o ~/.agents/skills; se instala en ambas. Si ya existía una carpeta tarea/ ahí, bórrela antes.)")


@herramienta
def instrucciones_proyecto(proyecto: str) -> str:
    """Devuelve, listas para copiar, las instrucciones del proyecto de Claude y el bloque para CLAUDE.md/AGENTS.md
    con el nombre correcto del proyecto. Entrégaselas al usuario tal cual, sin resumir."""
    def f():
        _raiz(proyecto)   # valida que exista
        return _instrucciones(proyecto)
    return _ejecutar(f)


def _validar_ruta_proyecto(ruta: str, mem: Path, alta: bool = False) -> Path:
    """Valida una ruta de código candidata, para alta (registrar_proyecto) o corrección (actualizar_proyecto):
    debe quedar dentro de la carpeta de proyectos, ser una carpeta existente, y no contener la memoria (ADR-010).
    `alta=True` usa la redacción de registrar_proyecto para el choque con la memoria (todavía no hay memoria
    elegida, se puede omitir `memoria`); `alta=False` (actualizar_proyecto) usa la redacción de corrección
    (la memoria ya existe en otro lado y moverla no está soportado aquí)."""
    r = Path(ruta).expanduser().resolve()
    if r != BASE_PROYECTOS and BASE_PROYECTOS not in r.parents:
        raise ErrorMemoria(f"La ruta debe estar dentro de {BASE_PROYECTOS}.")
    if not r.is_dir():
        raise ErrorMemoria(f"No existe la carpeta {r}.")
    if mem == r or r in mem.parents:
        if alta:
            raise ErrorMemoria("La memoria no puede ir dentro del repositorio del código (ADR-010); "
                               "omite `memoria` para usar .memorias/<nombre>.")
        raise ErrorMemoria("La memoria no puede ir dentro del repositorio del código (ADR-010); "
                           "elige otra ruta (mover la memoria de un proyecto existente no está soportado aquí).")
    return r


@herramienta
def registrar_proyecto(nombre: str, ruta: str, memoria: str = "", pruebas: str = "") -> str:
    """Da de alta un proyecto: lo agrega a projects.json, inicializa su memoria (repo git propio) y devuelve las
    instrucciones para pegar en Claude y en CLAUDE.md/AGENTS.md. `ruta`: carpeta del código (debe existir dentro de
    la carpeta de proyectos). `memoria`: opcional; por defecto <carpeta de proyectos>/.memorias/<nombre>,
    fuera del repositorio del código. `pruebas`: comando para correr las pruebas; si se omite se detecta
    (Maven, Gradle, npm/pnpm/yarn, Godot, pytest, cargo, go). Solo con confirmación del usuario."""
    def f():
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", nombre):
            raise ErrorMemoria("Nombre inválido: minúsculas, números, '-' y '_' (2–41 caracteres).")
        proyectos = _proyectos() if CONFIG.exists() else {}
        if nombre in proyectos:
            raise ErrorMemoria(f"'{nombre}' ya está registrado. Usa instrucciones_proyecto('{nombre}').")
        m = Path(memoria).expanduser().resolve() if memoria else BASE_PROYECTOS / ".memorias" / nombre
        if m != BASE_PROYECTOS and BASE_PROYECTOS not in m.parents:
            raise ErrorMemoria(f"La memoria debe estar dentro de {BASE_PROYECTOS}.")
        r = _validar_ruta_proyecto(ruta, m, alta=True)
        anterior = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else None
        # grafía de las claves: la de la primera entrada existente (español si el archivo está vacío)
        modelo = next(iter(proyectos.values()), {})
        valores = {"ruta": str(r), "memoria": str(m), "escritura": [MEM, "docs"],
                   "pruebas": pruebas.strip() or _detectar_pruebas_proyecto(r)}
        proyectos[nombre] = {_clave_escritura(modelo, k): v for k, v in valores.items()}
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        _escribir_atomico(CONFIG, json.dumps(proyectos, indent=2, ensure_ascii=False) + "\n")
        resultado = inicializar_memoria(proyecto=nombre)
        if resultado.startswith("ERROR") or "git falló" in resultado:
            if anterior is None:     # deshacer el alta: no dejar proyectos a medio registrar
                CONFIG.unlink()
            else:
                _escribir_atomico(CONFIG, anterior)
            raise ErrorMemoria(f"No se pudo inicializar la memoria; alta revertida. {resultado}")
        aviso = "" if _es_repo(r) else ("\n⚠ La carpeta del código no es un repositorio git: los documentos "
                                                  "en docs/ no quedarán versionados hasta que ejecutes `git init`.")
        repos = _repos(nombre)
        if repos:
            aviso = (f"\nProyecto de varios repositorios: {', '.join(repos)}. Cada tarea indica en cuál se trabaja; "
                     "agrega el bloque de abajo al CLAUDE.md/AGENTS.md de la raíz y de cada repo."
                     + ("" if _es_repo(r) else " La carpeta raíz no es un repo: lo que se guarde en "
                        "su docs/ no queda versionado (usa <repo>/docs/ o la memoria)."))
        return f"{resultado}{aviso}\n\n{_instrucciones(nombre)}"
    return _ejecutar(f)


@herramienta
def actualizar_proyecto(nombre: str, ruta: str = "", pruebas: str = "", repositorio: str = "",
                        redetectar: bool = False, integraciones: str = "") -> str:
    """Actualiza un proyecto ya registrado en projects.json sin editarlo a mano. Reemplaza a configurar_pruebas
    (eliminada). Indica al menos uno de `ruta`, `pruebas`, `repositorio`, `redetectar=True` o `integraciones`;
    sin ninguno, devuelve error y no toca el archivo.
    `ruta`: nueva carpeta del código, cuando se movió. Mismas validaciones que registrar_proyecto (debe quedar
    dentro de la carpeta de proyectos, ser una carpeta existente, y no contener la memoria del proyecto —
    ADR-010). Si el proyecto es de varios repos y el `pruebas` guardado queda con claves que ya no son repos
    bajo la ruta nueva, el cambio se aplica igual pero la respuesta avisa cuáles y sugiere `redetectar=True`.
    `pruebas`: comando con que el agente de código verifica las tareas (/tarea). En proyectos de varios repos,
    `repositorio` indica a cuál se aplica.
    `redetectar`: True para volver a detectar el comando a partir de los archivos del proyecto en vez de darlo
    con `pruebas` (ambos a la vez son incompatibles: no tiene sentido pedir redetección y dar el comando).
    En un proyecto de un solo repo redetecta el comando completo; en uno de varios repos redetecta todos, o
    solo `repositorio` si se indica.
    `integraciones`: activa o apaga integraciones opcionales del proyecto, p. ej. "codegraph=off,gentle-ai=auto"
    (valores auto|off; por defecto auto: se usan si se detectan). Una apagada no aparece en ninguna respuesta."""
    def f():
        proyectos = _proyectos()
        if nombre not in proyectos:
            sugerido = _sugerencia_nombre(nombre, proyectos)
            pista = f" ¿Quisiste decir '{sugerido}'?" if sugerido else f" Disponibles: {', '.join(proyectos)}"
            raise ErrorMemoria(f"Proyecto '{nombre}' no registrado.{pista}")
        if not (ruta.strip() or pruebas.strip() or repositorio.strip() or redetectar or integraciones.strip()):
            raise ErrorMemoria("Nada para actualizar: indica `ruta`, `pruebas`, `repositorio`, `redetectar=True` "
                               "o `integraciones`.")
        if redetectar and pruebas.strip():
            raise ErrorMemoria("`redetectar` y `pruebas` son incompatibles: pedir que se redetecte el comando "
                               "y darlo a la vez no tiene sentido; usa uno de los dos.")

        cambios = []
        raiz = None
        if ruta.strip():
            mem = _mem(nombre)
            anterior = _valor(proyectos[nombre], "ruta")
            raiz = _validar_ruta_proyecto(ruta.strip(), mem)
            proyectos[nombre][_clave_escritura(proyectos[nombre], "ruta")] = str(raiz)
            cambios.append(f"ruta: {anterior} → {raiz}")

        if pruebas.strip() or repositorio.strip() or redetectar:
            if raiz is None:
                raiz = _raiz(nombre)
            repos = _repos_de(raiz)
            actual = _valor(proyectos[nombre], "pruebas", "")
            repo = repositorio.strip()
            if repo:
                if repo not in repos:
                    raise ErrorMemoria(f"'{repo}' no es un repositorio del proyecto. "
                                       f"Disponibles: {', '.join(repos) or '(ninguno)'}")
                cmd = pruebas.strip() or _detectar_pruebas(raiz / repo)
                if not cmd:
                    raise ErrorMemoria("No se reconoce el tipo de repositorio; indica el comando explícitamente.")
                nuevo = dict(actual) if isinstance(actual, dict) else {}
                nuevo[repo] = cmd
                descripcion = f"`{repo}/`: `{cmd}`"
            else:
                if repos and pruebas.strip():
                    raise ErrorMemoria(f"Proyecto de varios repositorios: indica `repositorio` ({', '.join(repos)}).")
                nuevo = pruebas.strip() or _detectar_pruebas_proyecto(raiz)
                if not nuevo:
                    raise ErrorMemoria("No se reconoce el tipo de proyecto; indica el comando explícitamente.")
                descripcion = (", ".join(f"`{r}/`: `{c}`" for r, c in nuevo.items()) if isinstance(nuevo, dict)
                               else f"`{nuevo}`")
            proyectos[nombre][_clave_escritura(proyectos[nombre], "pruebas")] = nuevo
            cambios.append(f"pruebas {descripcion}" + ("" if pruebas.strip() else " (detectado)"))

        if ruta.strip():
            pruebas_final = _valor(proyectos[nombre], "pruebas", "")
            if isinstance(pruebas_final, dict):
                vigentes = _repos_de(raiz)
                huerfanas = sorted(k for k in pruebas_final if k not in vigentes)
                if huerfanas:
                    cambios.append(f"⚠ pruebas huérfanas (sin repo bajo la ruta nueva): {', '.join(huerfanas)}; "
                                   f"usa actualizar_proyecto('{nombre}', redetectar=True) para regenerarlas.")

        if integraciones.strip():
            nuevas, descripcion = _parsear_integraciones(integraciones, proyectos[nombre].get("integraciones"))
            if nuevas:
                proyectos[nombre]["integraciones"] = nuevas
            else:
                proyectos[nombre].pop("integraciones", None)
            cambios.append(f"integraciones: {descripcion}")

        _escribir_atomico(CONFIG, json.dumps(proyectos, indent=2, ensure_ascii=False) + "\n")
        mensaje = f"'{nombre}' actualizado:\n" + "\n".join(f"- {c}" for c in cambios)
        if pruebas.strip() or repositorio.strip() or redetectar:
            mensaje += ("\n\nBloque actualizado para CLAUDE.md/AGENTS.md (reemplaza el anterior):\n\n"
                       f"```\n{PLANTILLA_AGENTES.format(proyecto=nombre)}{_linea_pruebas(nombre)}\n```")
        return mensaje
    return _ejecutar(f)
