"""Configuración y rutas: projects.json, carpeta de proyectos, raíz del código, carpeta de memoria y zonas de
escritura. Las variables de entorno se leen al importar (igual que el servidor original)."""
from __future__ import annotations

import json
import os
from pathlib import Path


CONFIG = Path(os.environ.get(
    "MEMORIA_PROYECTOS_CONFIG",
    Path.home() / ".config" / "memoria-proyectos" / "projects.json",
)).expanduser()

MEM = ".project"
LIMITE_INDICE = 6000          # caracteres (~1.5k tokens)
LIMITE_LECTURA = 40_000       # caracteres por lectura de documento
# Presupuesto de listar_documentos (ADR-023): si el listado completo lo supera, se resume por niveles.
LIMITE_LISTADO_ENTRADAS = 200
LIMITE_LISTADO_CARACTERES = 8000
EXT_TEXTO = {".md", ".txt", ".json", ".gd", ".py", ".sh", ".cfg", ".tscn", ".csv", ".yaml", ".yml", ".toml",
             ".java", ".kt", ".gradle", ".properties", ".xml", ".sql", ".ts", ".tsx", ".js", ".jsx", ".vue",
             ".html", ".css", ".scss", ".go", ".rs", ".env.example", ".ini"}
# Fuera de git (o si git falla) no se recorren estas carpetas: dependencias y artefactos de compilación.
CARPETAS_IGNORADAS = {".git", ".godot", "node_modules", "target", "build", "dist", "out", ".gradle", ".idea",
                      ".venv", "venv", "__pycache__", ".next", ".nuxt", ".angular", "coverage", ".pytest_cache"}
LIMITE_ARCHIVO_BUSQUEDA = 1_000_000   # bytes: archivos más grandes no se recorren en buscar


# Raíz del repositorio de memoria-proyectos (donde están servidor.py, tarea.md y skills/).
_DIR = Path(__file__).resolve().parents[1]


class ErrorMemoria(Exception):
    pass


BASE_PROYECTOS = Path(os.environ.get("MEMORIA_PROYECTOS_BASE", Path.home() / "Projects")).expanduser().resolve()


# ───────────────────────── configuración y rutas ─────────────────────────

def _proyectos() -> dict:
    if not CONFIG.exists():
        raise ErrorMemoria(f"No existe la configuración {CONFIG}.")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _sugerencia_nombre(nombre: str, proyectos: dict) -> str | None:
    """Si `nombre` no está registrado pero existe un proyecto equivalente salvo '_'/'-' (p. ej. 'erp-spring-manager'
    vs 'erp_spring_manager'), lo sugiere."""
    def normal(n: str) -> str:
        return n.replace("_", "-")
    for existente in proyectos:
        if existente != nombre and normal(existente) == normal(nombre):
            return existente
    return None


def _raiz(proyecto: str, verificar_existe: bool = True) -> Path:
    proyectos = _proyectos()
    p = proyectos.get(proyecto)
    if not p:
        sugerido = _sugerencia_nombre(proyecto, proyectos)
        pista = f" ¿Quisiste decir '{sugerido}'?" if sugerido else f" Disponibles: {', '.join(proyectos)}"
        raise ErrorMemoria(f"Proyecto '{proyecto}' no registrado.{pista}")
    raiz = Path(p["ruta"]).expanduser().resolve()
    if verificar_existe and not raiz.is_dir():
        raise ErrorMemoria(f"La ruta del proyecto no existe: {raiz}")
    return raiz


def _mem(proyecto: str) -> Path:
    """Carpeta de memoria (ADR-010): repo git propio, SIEMPRE fuera del repositorio del código, para que ninguna
    rama ni checkout la afecte. Clave "memoria" de projects.json; por defecto <carpeta de proyectos>/.memorias/<nombre>.
    No exige que la ruta del código exista: solo se usa aquí para la comparación ADR-010, nunca para leerla."""
    p = _proyectos().get(proyecto) or {}
    mem = Path(p["memoria"]).expanduser().resolve() if p.get("memoria") else BASE_PROYECTOS / ".memorias" / proyecto
    raiz = _raiz(proyecto, verificar_existe=False)
    if mem == raiz or raiz in mem.parents:
        raise ErrorMemoria(f"La memoria de '{proyecto}' está dentro del repositorio del código ({mem}); ADR-010 lo "
                           f"impide. Muévela a {BASE_PROYECTOS / '.memorias' / proyecto} y actualiza projects.json.")
    return mem


def _es_repo(d: Path) -> bool:
    """¿`d` es un repositorio git real? Un `.git` vacío no cuenta: el sandbox de Codex crea `.git`, `.agents` y
    `.codex` vacíos en la carpeta donde se abre para protegerlos, y eso no convierte la carpeta en un repo."""
    g = d / ".git"
    return g.is_file() or (g / "HEAD").exists()


def _repos_de(raiz: Path) -> list[str]:
    """Igual que `_repos`, a partir de una ruta ya resuelta (para no releer projects.json en medio de una
    actualización, p. ej. en actualizar_proyecto cuando `ruta` cambia en la misma llamada)."""
    if _es_repo(raiz):
        return []
    return sorted(d.name for d in raiz.iterdir() if d.is_dir() and _es_repo(d))


def _repos(proyecto: str) -> list[str]:
    """Subcarpetas que son repositorios git, para proyectos de varios repos (p. ej. backend + frontend).
    Vacío si la raíz misma es un repositorio."""
    return _repos_de(_raiz(proyecto))


def _repo_de(ruta: Path, tope: Path) -> Path | None:
    """Repositorio git más cercano que contiene `ruta`, sin salir de `tope`."""
    for d in [ruta, *ruta.parents]:
        if _es_repo(d):
            return d
        if d == tope:
            break
    return None


def _zonas_escritura(proyecto: str) -> list[str]:
    return _proyectos()[proyecto].get("escritura", [MEM, "docs"])


def _ruta_segura(proyecto: str, relativa: str, escribir: bool = False) -> Path:
    """Resuelve una ruta relativa dentro del proyecto; bloquea escapes, .git y zonas no autorizadas.
    Las rutas '.project/...' apuntan siempre a la carpeta de memoria, esté donde esté."""
    raiz = _raiz(proyecto)
    if not relativa or Path(relativa).is_absolute():
        raise ErrorMemoria("La ruta debe ser relativa a la raíz del proyecto.")
    partes_rel = Path(relativa).parts
    if partes_rel and partes_rel[0] == MEM:
        mem = _mem(proyecto)
        destino = (mem / Path(*partes_rel[1:])) if len(partes_rel) > 1 else mem
        destino = destino.resolve()
        if destino != mem and mem not in destino.parents or ".git" in destino.relative_to(mem).parts:
            raise ErrorMemoria("Ruta fuera de la memoria del proyecto.")
        if escribir and MEM not in _zonas_escritura(proyecto):
            raise ErrorMemoria("Escritura no permitida en la memoria.")
        return destino
    destino = (raiz / relativa).resolve()
    if destino != raiz and raiz not in destino.parents:
        raise ErrorMemoria("Ruta fuera del proyecto.")
    partes = destino.relative_to(raiz).parts
    if partes and partes[0] == ".git":
        raise ErrorMemoria("No se permite acceder a .git.")
    if escribir:
        zonas = _zonas_escritura(proyecto)
        en_subrepo = len(partes) > 1 and partes[0] in _repos(proyecto) and partes[1] in zonas
        if not partes or not (partes[0] in zonas or en_subrepo):
            raise ErrorMemoria(f"Escritura solo permitida en: {', '.join(zonas)}"
                               + (f" (o <repo>/{zonas[-1]} con repo en {', '.join(_repos(proyecto))})"
                                  if _repos(proyecto) else ""))
    return destino
