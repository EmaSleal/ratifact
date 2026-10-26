"""Herramientas de contexto y documentos: list_projects, get_context, search, list/read/create/update_document y
update_index."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ratifact import build as _build
from ratifact.app import _ejecutar, herramienta
from ratifact.busqueda import _resultados
from ratifact.catalogo import _bloque_pendientes, _es_carpeta_de_registros, _linea, _registros_en, _resolver_id
from ratifact.config import (CARPETAS_IGNORADAS, EXT_TEXTO, LIMITE_INDICE, LIMITE_LECTURA, MEM, ErrorMemoria,
                             _aviso_alias, _es_repo, _mem, _proyectos, _raiz, _repos, _ruta_segura, _traducir_alias,
                             _valor)
from ratifact.esquema import _bloqueo, _idioma_contenido, _version_esquema
from ratifact.integraciones import registro as _integraciones
from ratifact.listado import _listado
from ratifact.registros import _clave_id, _commit, _escribir_atomico, _leer_registro, _resumen_tareas
from ratifact.vocabulario import DECISIONES, MODOS_V0


# ───────────────────────── herramientas ─────────────────────────

@herramienta
def list_projects() -> str:
    """Lists the registered projects, their code folder and whether they already have a memory."""
    def f():
        filas = []
        for nombre, p in _proyectos().items():
            ruta = Path(_valor(p, "ruta")).expanduser()
            try:
                mem = _mem(nombre)
                estado = (f"[memory ready · schema v{_version_esquema(mem)}]" if (mem / "INDEX.md").exists()
                          else "[no memory]")
            except ErrorMemoria as e:
                estado = f"[invalid configuration: {e}]"
            repos = _repos(nombre) if ruta.is_dir() else []
            filas.append(f"- {nombre}: {ruta} {estado}" + (f" · repos: {', '.join(repos)}" if repos else ""))
        return "\n".join(filas) or "(no projects)"
    return _ejecutar(f)


UMBRAL_INDICE = 5   # cambios en la memoria tras los cuales INDEX.md se considera desactualizado


def _aviso_indice(proyecto: str) -> str:
    """Si INDEX.md quedó atrás respecto de la memoria, lo dice explícitamente al cargar contexto."""
    mem = _mem(proyecto)
    if not _es_repo(mem):
        return ""
    def git(*a):
        return subprocess.run(["git", "-C", str(mem), *a], capture_output=True, text=True).stdout.strip()
    ultimo = git("log", "-1", "--format=%h|%ad", "--date=short", "--", "INDEX.md")
    if not ultimo:
        return ""
    sha, fecha = ultimo.split("|")
    cambios = git("log", "--format=%s", f"{sha}..HEAD").splitlines()
    if len(cambios) < UMBRAL_INDICE:
        return ""
    return (f"⚠ INDEX.md is out of date: {len(cambios)} changes in the memory since {fecha}. "
            "The status summary above may not reflect reality; cross-check it with decisions and tasks, "
            "and offer the user to regenerate it with update_index (or with the close prompt).")


@herramienta
def get_context(project: str) -> str:
    """Start of a chat: returns INDEX.md and the open items (one line each: id, topic, date; read the detail with
    read_document). Call it before answering.
    The first line is `ratifact <build>` (version + content hash of the running server). Below it, a ⚠ line when
    this server process is older than the installation on disk (restart the client) or when the local source it was
    installed from is newer than the installation (reinstall).
    At the end, if optional integrations are active (codegraph, gentle-ai, engram…), one line listing them and their
    planning guidance; that guidance is conditional: follow it only if you have their tools."""
    proyecto = project

    def f():
        mem = _mem(proyecto)
        if _es_repo(mem):
            with _bloqueo(proyecto):        # verifica y, si hace falta, migra el esquema antes de leer
                pass
        partes = []
        raiz = _raiz(proyecto, verificar_existe=False)
        if not raiz.is_dir():
            partes.append(f"⚠ The registered path of '{proyecto}' no longer exists on disk ({raiz}); the memory "
                          f"context below is still valid. Fix it with update_project(\"{proyecto}\", "
                          "path=\"<new path>\").")
        indice = mem / "INDEX.md"
        partes.append(indice.read_text(encoding="utf-8") if indice.exists() else "(INDEX.md does not exist)")
        partes.append(_bloque_pendientes(proyecto))     # ADR-026: del catálogo, no abiertas.md
        propuestas = ["-".join(p.stem.split("-", 2)[:2]) for p in (mem / DECISIONES).glob("ADR-*.md")
                      if _leer_registro(p)[0].get("status") == "proposed"]
        if propuestas:
            partes.append("Proposed decisions awaiting the user's acceptance: "
                          + ", ".join(sorted(propuestas, key=_clave_id)))
        tareas = _resumen_tareas(proyecto)
        if tareas:
            partes.append("# Active code tasks\n" + "\n".join(tareas))
        aviso = _aviso_indice(proyecto)
        if aviso:
            partes.append(aviso)
        idioma = _idioma_contenido(mem)
        partes.append(f"Content language: {idioma} — write the content of the records you save (decisions, pending "
                      "items, tasks, sessions, INDEX) in this language; the conversation stays in the user's "
                      "language.")
        integraciones = _integraciones._bloque_contexto(proyecto)
        if integraciones:
            partes.append(integraciones)
        return _cabecera() + "\n\n" + "\n\n---\n\n".join(partes)
    return _ejecutar(f)


def _cabecera() -> str:
    """ADR-037 §2 and §4: `ratifact <build>` on the first line and, below it, the stale-server warning and the
    local-source warning when they apply."""
    lineas = [f"ratifact {_build.build_id()}"]
    if _build.obsoleto():
        lineas.append(_build.aviso_obsoleto())
    fuente = _build.aviso_fuente()
    if fuente:
        lineas.append(fuente)
    return "\n".join(lineas)


def _archivos_proyecto(base: Path, usar_git: bool = True) -> list[Path]:
    """Archivos del proyecto respetando .gitignore: en un repo git usa `git ls-files` (versionados + nuevos no
    ignorados); si no, recorre la carpeta y, al encontrar un repo anidado (proyectos de varios repos), usa el
    .gitignore de ese repo. Siempre salta CARPETAS_IGNORADAS y nunca incluye .git."""
    if not base.is_dir():
        return []
    if usar_git and _es_repo(base):
        r = subprocess.run(["git", "-C", str(base), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            rutas = {base / x for x in r.stdout.split("\0")
                     if x and not CARPETAS_IGNORADAS.intersection(Path(x).parts[:-1])}
            return sorted(p for p in rutas if p.is_file())
    salida = []
    for actual, dirs, archivos in os.walk(base):
        anidados = [d for d in dirs if usar_git and _es_repo(Path(actual) / d)]
        for d in anidados:
            salida += _archivos_proyecto(Path(actual) / d)
        dirs[:] = sorted(d for d in dirs if d not in CARPETAS_IGNORADAS and d not in anidados)
        salida += [Path(actual) / a for a in sorted(archivos) if a != ".lock"]
    return salida


@herramienta
def search(project: str, query: str, max_results: int = 20) -> str:
    """Searches text (case-insensitive) in the project's text files and returns snippets with path and line. Use
    it before reading whole documents.
    Memory records come first ("ID · status · title (path)"): the one whose id is `query` (e.g. "T-1", "adr-20")
    and up to 5 whose title contains it at the start of a word; then memory lines and code lines, sharing the rest
    equally. In each section, files whose name contains `query` at the start of a word or camelCase part come first
    (if no line matches: "path: (file name matches)"), and one line per file is shown before repeating files.
    `max_results` counts every line; if something is left out, the last line says how many lines (and files) per
    section."""
    proyecto, texto, max_resultados = project, query, max_results

    def f():
        raiz, mem = _raiz(proyecto), _mem(proyecto)
        codigo = [p for p in _archivos_proyecto(raiz) if p != mem and mem not in p.parents]
        return _resultados(proyecto, texto, max_resultados, (mem, MEM + "/", _archivos_proyecto(mem, usar_git=False)),
                           (raiz, "", codigo))
    return _ejecutar(f)


@herramienta
def list_documents(project: str, folder: str = "docs") -> str:
    """Lists files (with size) under a project folder.
    In .project/decisions, pending and tasks it lists one record per line: "ID · status · title  (path)".
    A path with a v1 folder (.project/tareas, decisiones, pendientes, sesiones) is translated and flagged.
    If the full listing is too large, it is summarized by levels: unexpanded folders with their file count
    ("module/ (38 files)"); ask for a more specific `folder` to see the detail."""
    proyecto, carpeta = project, folder

    def f():
        carpeta_real = _traducir_alias(proyecto, carpeta)
        return _aviso_alias() + _listar(proyecto, carpeta_real)
    return _ejecutar(f)


def _listar(proyecto: str, carpeta: str) -> str:
    base = _ruta_segura(proyecto, carpeta)
    prefijo = _es_carpeta_de_registros(carpeta)
    en_memoria = carpeta.split("/")[0] == MEM
    repo = _mem(proyecto) if en_memoria else _raiz(proyecto)
    archivos = [p for p in _archivos_proyecto(repo, usar_git=not en_memoria) if p == base or base in p.parents]
    if prefijo:
        registros = _registros_en(proyecto, prefijo)
        vistos = {r.ruta.rsplit("/", 1)[1] for r in registros}
        otros = [f"{carpeta.rstrip('/')}/{p.relative_to(base)}  ({p.stat().st_size} B)" for p in archivos
                 if p.relative_to(base).as_posix() not in vistos]
        return "\n".join([_linea(r, "  ") for r in registros] + otros) or "(empty)"
    entradas = [(p.relative_to(base).as_posix(), p.stat().st_size) for p in archivos]
    return _listado(carpeta, entradas) or "(empty)"


@herramienta
def read_document(project: str, path: str, from_line: int = 1, to_line: int = 0) -> str:
    """Reads a project text file, optionally a line range (1-based, inclusive).
    Also accepts a memory record id ("T-24", "tasks/T-024.md", "ADR-020-slug.md"): if the path does not exist, it
    reads the real record and prepends the line "(→ .project/<folder>/<file>)". A path with a v1 folder
    (.project/tareas/…, .project/acuerdos.md…) is translated and flagged the same way.
    For a task, read_task returns a working brief (spec, amendments, the latest relevant block) instead."""
    proyecto, ruta, desde_linea, hasta_linea = project, path, from_line, to_line

    def f():
        p = _ruta_segura(proyecto, ruta)
        aviso = _aviso_alias()
        if p.is_dir():
            raise ErrorMemoria(f"{ruta} is a folder; to see its content use list_documents(\"{proyecto}\", "
                               f"\"{ruta.rstrip('/')}\").")
        if not p.is_file():
            real = _resolver_id(proyecto, ruta)
            if real is None:
                raise ErrorMemoria(f"{ruta} does not exist.")
            p, aviso = real, f"(→ {MEM}/{real.relative_to(_mem(proyecto)).as_posix()})\n"
        try:
            lineas = p.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raise ErrorMemoria(f"{ruta} is not a text file (e.g. .docx, .pdf or an image); "
                               "ask the user to open or convert it.")
        fin = hasta_linea if hasta_linea > 0 else len(lineas)
        texto = "\n".join(lineas[max(desde_linea, 1) - 1:fin])
        if len(texto) > LIMITE_LECTURA:
            texto = texto[:LIMITE_LECTURA] + f"\n(… truncated; {len(lineas)} lines in total, ask for a range)"
        return aviso + texto
    return _ejecutar(f)


def _escribir_documento(proyecto: str, ruta: str, contenido: str, nuevo: bool, anexar: bool, motivo: str) -> str:
    ruta = _traducir_alias(proyecto, ruta, escribir=True)
    p = _ruta_segura(proyecto, ruta, escribir=True)
    if p.suffix not in EXT_TEXTO:
        raise ErrorMemoria("Text files only; binary files are produced by the coding agent.")
    with _bloqueo(proyecto):
        if nuevo and p.exists():
            raise ErrorMemoria(f"{ruta} already exists; to modify it use update_document.")
        if not nuevo and not p.exists():
            raise ErrorMemoria(f"{ruta} does not exist; to create it use create_document.")
        final = (p.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + contenido) if anexar else contenido
        _escribir_atomico(p, final if final.endswith("\n") else final + "\n")
        accion = "crear" if nuevo else ("anexar" if anexar else "reemplazar")
        sha = _commit(proyecto, [p], f"{accion} {ruta}" + (f" — {motivo}" if motivo else ""))
        modo = "create" if nuevo else ("append" if anexar else "replace")
        return f"{_aviso_alias()}{ruta} saved ({modo}) · commit {sha}"


@herramienta
def create_document(project: str, path: str, content: str, reason: str = "") -> str:
    """Creates a NEW text file in an allowed area (by default .project/ and docs/). Fails if it already exists.
    Separate from update_document so the user can require approval for creating files."""
    return _ejecutar(lambda: _escribir_documento(project, path, content, True, False, reason))


@herramienta
def update_document(project: str, path: str, content: str, mode: str = "replace", reason: str = "") -> str:
    """Modifies an EXISTING text file in an allowed area. mode: 'replace' | 'append'.
    To create a new file use create_document."""
    def f():
        modo = MODOS_V0.get(mode.strip().lower(), mode.strip().lower())   # 'reemplazar'/'anexar' hasta 1.1
        if modo not in ("replace", "append"):
            raise ErrorMemoria("Invalid mode: 'replace' or 'append' (to create a file, use create_document).")
        return _escribir_documento(project, path, content, False, modo == "append", reason)
    return _ejecutar(f)


@herramienta
def update_index(project: str, content: str) -> str:
    """Rewrites INDEX.md (the project's executive summary). It must be a regenerated SUMMARY, not an
    accumulation; limit ~6000 characters."""
    def f():
        if len(content) > LIMITE_INDICE:
            raise ErrorMemoria(f"INDEX.md exceeds {LIMITE_INDICE} characters ({len(content)}). Summarize more.")
        with _bloqueo(project):
            p = _mem(project) / "INDEX.md"
            _escribir_atomico(p, content.rstrip("\n") + "\n")
            return f"INDEX.md updated · commit {_commit(project, [p], 'actualizar INDEX')}"
    return _ejecutar(f)
