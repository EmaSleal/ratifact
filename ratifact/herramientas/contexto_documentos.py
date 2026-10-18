"""Herramientas de contexto y documentos: listar_proyectos, obtener_contexto, buscar, listar/leer/crear/guardar
documentos y actualizar_indice."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ratifact.app import _ejecutar, herramienta
from ratifact.busqueda import _resultados
from ratifact.catalogo import _es_carpeta_de_registros, _linea, _registros_en, _resolver_id
from ratifact.config import (CARPETAS_IGNORADAS, EXT_TEXTO, LIMITE_INDICE, LIMITE_LECTURA, MEM, ErrorMemoria, _es_repo,
                             _mem, _proyectos, _raiz, _repos, _ruta_segura)
from ratifact.esquema import _bloqueo, _version_esquema
from ratifact.listado import _listado
from ratifact.registros import _clave_id, _commit, _escribir_atomico, _leer_registro, _resumen_tareas


# ───────────────────────── herramientas ─────────────────────────

@herramienta
def listar_proyectos() -> str:
    """Lista los proyectos registrados, su carpeta de código y si ya tienen memoria."""
    def f():
        filas = []
        for nombre, p in _proyectos().items():
            ruta = Path(p["ruta"]).expanduser()
            try:
                mem = _mem(nombre)
                estado = (f"[memoria lista · esquema v{_version_esquema(mem)}]" if (mem / "INDEX.md").exists()
                          else "[sin memoria]")
            except ErrorMemoria as e:
                estado = f"[configuración inválida: {e}]"
            repos = _repos(nombre) if ruta.is_dir() else []
            filas.append(f"- {nombre}: {ruta} {estado}" + (f" · repos: {', '.join(repos)}" if repos else ""))
        return "\n".join(filas) or "(sin proyectos)"
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
    return (f"⚠ INDEX.md está desactualizado: {len(cambios)} cambios en la memoria desde {fecha}. "
            "El 'Estado actual' de arriba puede no reflejar la realidad; contrasta con acuerdos y tareas, "
            "y propón al usuario regenerarlo con actualizar_indice (o con /cierre).")


@herramienta
def obtener_contexto(proyecto: str) -> str:
    """Carga inicial de un chat: devuelve INDEX.md y las decisiones abiertas. Llamar antes de responder."""
    def f():
        mem = _mem(proyecto)
        if _es_repo(mem):
            with _bloqueo(proyecto):        # verifica y, si hace falta, migra el esquema antes de leer
                pass
        partes = []
        raiz = _raiz(proyecto, verificar_existe=False)
        if not raiz.is_dir():
            partes.append(f"⚠ La ruta registrada de '{proyecto}' ya no existe en disco ({raiz}); el contexto de "
                          f"memoria de abajo sigue siendo válido. Corrígela con actualizar_proyecto(\"{proyecto}\", "
                          "ruta=\"<ruta nueva>\").")
        for nombre in ("INDEX.md", "abiertas.md"):
            r = mem / nombre
            partes.append(r.read_text(encoding="utf-8") if r.exists() else f"({nombre} no existe)")
        propuestas = ["-".join(p.stem.split("-", 2)[:2]) for p in (mem / "decisiones").glob("ADR-*.md")
                      if _leer_registro(p)[0].get("estado") == "propuesta"]
        if propuestas:
            partes.append("Decisiones propuestas pendientes de confirmar por el usuario: "
                          + ", ".join(sorted(propuestas, key=_clave_id)))
        tareas = _resumen_tareas(proyecto)
        if tareas:
            partes.append("# Tareas de código activas\n" + "\n".join(tareas))
        aviso = _aviso_indice(proyecto)
        if aviso:
            partes.append(aviso)
        return "\n\n---\n\n".join(partes)
    return _ejecutar(f)


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
def buscar(proyecto: str, texto: str, max_resultados: int = 20) -> str:
    """Busca texto (sin distinguir mayúsculas) en archivos de texto del proyecto y devuelve
    fragmentos con ruta y línea. Úsala antes de leer documentos completos.
    Primero salen los registros de la memoria ("ID · estado · título (ruta)"): el que tiene `texto` como id (p. ej.
    "T-1", "adr-20") y hasta 5 cuyo título lo contiene al inicio de una palabra; luego las líneas de la memoria y
    las del código, repartiendo el resto a partes iguales. En cada sección van primero los archivos cuyo nombre
    contiene `texto` al inicio de una palabra o tramo camelCase (si ninguna línea coincide: "ruta: (coincide el
    nombre del archivo)"), y se muestra una línea por archivo antes de repetir archivos. `max_resultados` cuenta
    todas las líneas; si se omite algo, la última línea dice cuántas líneas (y archivos) por sección."""
    def f():
        raiz, mem = _raiz(proyecto), _mem(proyecto)
        codigo = [p for p in _archivos_proyecto(raiz) if p != mem and mem not in p.parents]
        return _resultados(proyecto, texto, max_resultados, (mem, MEM + "/", _archivos_proyecto(mem, usar_git=False)),
                           (raiz, "", codigo))
    return _ejecutar(f)


@herramienta
def listar_documentos(proyecto: str, carpeta: str = "docs") -> str:
    """Lista archivos (con tamaño) bajo una carpeta del proyecto.
    En .project/decisiones, pendientes y tareas lista un registro por línea: "ID · estado · título  (ruta)".
    Si el listado completo es demasiado grande, lo resume por niveles: carpetas sin expandir con su cantidad de
    archivos ("modulo/ (38 archivos)"); pide una `carpeta` más específica para ver el detalle."""
    def f():
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
            return "\n".join([_linea(r, "  ") for r in registros] + otros) or "(vacío)"
        entradas = [(p.relative_to(base).as_posix(), p.stat().st_size) for p in archivos]
        return _listado(carpeta, entradas) or "(vacío)"
    return _ejecutar(f)


@herramienta
def leer_documento(proyecto: str, ruta: str, desde_linea: int = 1, hasta_linea: int = 0) -> str:
    """Lee un archivo de texto del proyecto, opcionalmente un rango de líneas (1-indexado).
    Acepta también el id de un registro de la memoria ("T-24", "tareas/T-024.md", "ADR-020-slug.md"): si la ruta no
    existe, lee el registro real y antepone la línea "(→ .project/<carpeta>/<archivo>)"."""
    def f():
        p = _ruta_segura(proyecto, ruta)
        aviso = ""
        if p.is_dir():
            raise ErrorMemoria(f"{ruta} es una carpeta; para ver su contenido usa listar_documentos(\"{proyecto}\", "
                               f"\"{ruta.rstrip('/')}\").")
        if not p.is_file():
            real = _resolver_id(proyecto, ruta)
            if real is None:
                raise ErrorMemoria(f"No existe {ruta}.")
            p, aviso = real, f"(→ {MEM}/{real.relative_to(_mem(proyecto)).as_posix()})\n"
        try:
            lineas = p.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raise ErrorMemoria(f"{ruta} no es un archivo de texto (p. ej. .docx, .pdf o una imagen); "
                               "pídele al usuario que lo abra o lo convierta.")
        fin = hasta_linea if hasta_linea > 0 else len(lineas)
        texto = "\n".join(lineas[max(desde_linea, 1) - 1:fin])
        if len(texto) > LIMITE_LECTURA:
            texto = texto[:LIMITE_LECTURA] + f"\n(… truncado; {len(lineas)} líneas en total, pide un rango)"
        return aviso + texto
    return _ejecutar(f)


def _escribir_documento(proyecto: str, ruta: str, contenido: str, nuevo: bool, anexar: bool, motivo: str) -> str:
    p = _ruta_segura(proyecto, ruta, escribir=True)
    if p.suffix not in EXT_TEXTO:
        raise ErrorMemoria("Solo archivos de texto; los binarios se generan con el agente de código.")
    with _bloqueo(proyecto):
        if nuevo and p.exists():
            raise ErrorMemoria(f"{ruta} ya existe; para modificarlo usa guardar_documento.")
        if not nuevo and not p.exists():
            raise ErrorMemoria(f"{ruta} no existe; para crearlo usa crear_documento.")
        final = (p.read_text(encoding="utf-8").rstrip("\n") + "\n\n" + contenido) if anexar else contenido
        _escribir_atomico(p, final if final.endswith("\n") else final + "\n")
        accion = "crear" if nuevo else ("anexar" if anexar else "reemplazar")
        sha = _commit(proyecto, [p], f"{accion} {ruta}" + (f" — {motivo}" if motivo else ""))
        return f"{ruta} guardado ({accion}) · commit {sha}"


@herramienta
def crear_documento(proyecto: str, ruta: str, contenido: str, motivo: str = "") -> str:
    """Crea un archivo de texto NUEVO en una zona autorizada (por defecto .project/ y docs/). Falla si ya existe.
    Separada de guardar_documento para que el usuario pueda exigir aprobación al crear archivos."""
    return _ejecutar(lambda: _escribir_documento(proyecto, ruta, contenido, True, False, motivo))


@herramienta
def guardar_documento(proyecto: str, ruta: str, contenido: str, modo: str = "reemplazar",
                      motivo: str = "") -> str:
    """Modifica un archivo de texto EXISTENTE en una zona autorizada. modo: 'reemplazar' | 'anexar'.
    Para crear un archivo nuevo usa crear_documento."""
    def f():
        if modo not in ("reemplazar", "anexar"):
            raise ErrorMemoria("modo inválido: 'reemplazar' o 'anexar' (para crear, usa crear_documento).")
        return _escribir_documento(proyecto, ruta, contenido, False, modo == "anexar", motivo)
    return _ejecutar(f)


@herramienta
def actualizar_indice(proyecto: str, contenido: str) -> str:
    """Reescribe INDEX.md (resumen ejecutivo del proyecto). Debe ser un RESUMEN regenerado, no un
    acumulado; límite ~6000 caracteres."""
    def f():
        if len(contenido) > LIMITE_INDICE:
            raise ErrorMemoria(f"INDEX.md excede {LIMITE_INDICE} caracteres ({len(contenido)}). Resume más.")
        with _bloqueo(proyecto):
            p = _mem(proyecto) / "INDEX.md"
            _escribir_atomico(p, contenido.rstrip("\n") + "\n")
            return f"INDEX.md actualizado · commit {_commit(proyecto, [p], 'actualizar INDEX')}"
    return _ejecutar(f)
