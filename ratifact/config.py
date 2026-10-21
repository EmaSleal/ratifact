"""Configuración y rutas: projects.json, carpeta de proyectos, raíz del código, carpeta de memoria y zonas de
escritura. Las variables de entorno se leen al importar (igual que el servidor original)."""
from __future__ import annotations

import json
import os
import sys
from contextvars import ContextVar
from pathlib import Path

from ratifact import rutas
from ratifact.vocabulario import CARPETAS_V1, VISTAS_V1


# Variables de entorno (ADR-028): RATIFACT_* ganan; MEMORIA_PROYECTOS_* quedan como respaldo hasta 1.1, con una línea
# de aviso en el log del servidor (stderr) la primera vez que se usa cada una.
_AVISOS_ENTORNO: set[str] = set()


def _entorno(sufijo: str) -> str | None:
    """RATIFACT_<sufijo> o, si no está, el respaldo deprecado MEMORIA_PROYECTOS_<sufijo> (aviso único en stderr)."""
    nuevo = os.environ.get(f"RATIFACT_{sufijo}")
    if nuevo:
        return nuevo
    viejo = os.environ.get(f"MEMORIA_PROYECTOS_{sufijo}")
    if viejo and sufijo not in _AVISOS_ENTORNO:
        _AVISOS_ENTORNO.add(sufijo)
        print(f"ratifact: MEMORIA_PROYECTOS_{sufijo} is deprecated; rename it to RATIFACT_{sufijo} "
              "(the fallback is removed in 1.1).", file=sys.stderr)
    return viejo or None


def _ruta_config() -> Path:
    """RATIFACT_CONFIG (o MEMORIA_PROYECTOS_CONFIG); sin variable, ~/.config/ratifact/projects.json si existe, si no
    ~/.config/memoria-proyectos/projects.json. Si la variable apunta a un projects.json que `ratifact upgrade` ya
    renombró a .bak-v1 (ADR-029), se usa el nuevo con un aviso: las configuraciones de los clientes no se rompen."""
    explicita = _entorno("CONFIG")
    nueva = rutas.config_nueva()
    if explicita:
        ruta = Path(explicita).expanduser()
        if not ruta.exists() and rutas.respaldo(ruta).exists() and nueva.exists():
            if "CONFIG_RENOMBRADA" not in _AVISOS_ENTORNO:
                _AVISOS_ENTORNO.add("CONFIG_RENOMBRADA")
                print(f"ratifact: {ruta} was moved to {nueva} by `ratifact upgrade`; using it. Remove the CONFIG "
                      "variable from the client configuration.", file=sys.stderr)
            return nueva
        return ruta
    return nueva if nueva.exists() else rutas.config_vieja()


def _base() -> Path:
    return Path(_entorno("BASE") or Path.home() / "Projects").expanduser().resolve()


CONFIG = _ruta_config()

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


class ErrorMemoria(Exception):
    pass


BASE_PROYECTOS = _base()


# ───────────────────────── configuración y rutas ─────────────────────────

def _proyectos() -> dict:
    if not CONFIG.exists():
        raise ErrorMemoria(f"Configuration file {CONFIG} does not exist.")
    return json.loads(CONFIG.read_text(encoding="utf-8"))


# Claves de cada proyecto en projects.json: se leen en español (v1) y en inglés (ADR-029); si están las dos, gana la
# inglesa. Al escribir se conserva la grafía que ya usa la entrada. El renombrado del archivo es un paso del
# instalador (`ratifact upgrade`), nunca de la migración automática.
CLAVES_CONFIG = {"ruta": "path", "memoria": "memory", "escritura": "writable", "pruebas": "tests",
                 "integraciones": "integrations"}


def _valor(p: dict, clave: str, defecto=None):
    """Valor de `clave` (nombre en español) en la entrada `p` de projects.json, leyendo también la clave inglesa."""
    en = CLAVES_CONFIG[clave]
    return p[en] if en in p else p.get(clave, defecto)


def _clave_escritura(p: dict, clave: str) -> str:
    """Nombre con que se escribe `clave` en la entrada `p`: el que ya tiene; si no tiene ninguno, español solo si la
    entrada ya usa claves en español (una entrada vacía —configuración nueva, T-013— se escribe en inglés)."""
    en = CLAVES_CONFIG[clave]
    if en in p:
        return en
    if clave in p:
        return clave
    return clave if any(k in p for k in CLAVES_CONFIG) and not any(k in p for k in CLAVES_CONFIG.values()) else en


def _sugerencia_nombre(nombre: str, proyectos: dict) -> str | None:
    """Si `nombre` no está registrado pero existe un proyecto equivalente salvo '_'/'-' (p. ej. 'erp-spring-manager'
    vs 'erp_spring_manager'), lo sugiere."""
    def normal(n: str) -> str:
        return n.replace("_", "-")
    for existente in proyectos:
        if existente != nombre and normal(existente) == normal(nombre):
            return existente
    return None


def _pista_nombre(sugerido: str | None, proyectos: dict) -> str:
    return f" Did you mean '{sugerido}'?" if sugerido else f" Available: {', '.join(proyectos)}"


def _raiz(proyecto: str, verificar_existe: bool = True) -> Path:
    proyectos = _proyectos()
    p = proyectos.get(proyecto)
    if not p:
        sugerido = _sugerencia_nombre(proyecto, proyectos)
        raise ErrorMemoria(f"Project '{proyecto}' is not registered.{_pista_nombre(sugerido, proyectos)}")
    raiz = Path(_valor(p, "ruta")).expanduser().resolve()
    if verificar_existe and not raiz.is_dir():
        raise ErrorMemoria(f"The project path does not exist: {raiz}")
    return raiz


def _mem_por_defecto(proyecto: str, base: Path | None = None) -> Path:
    """Memoria de un proyecto sin clave "memory"/"memoria" (ADR-029): <base>/.ratifact/<nombre>; una que todavía vive
    en la ruta por defecto vieja <base>/.memorias/<nombre> se sigue encontrando ahí hasta que `ratifact upgrade` la
    mueve."""
    base = base or BASE_PROYECTOS
    nueva, vieja = base / ".ratifact" / proyecto, base / ".memorias" / proyecto
    return vieja if vieja.exists() and not nueva.exists() else nueva


def _mem(proyecto: str) -> Path:
    """Carpeta de memoria (ADR-010): repo git propio, SIEMPRE fuera del repositorio del código, para que ninguna
    rama ni checkout la afecte. Clave "memoria" de projects.json; si no está, `_mem_por_defecto`.
    No exige que la ruta del código exista: solo se usa aquí para la comparación ADR-010, nunca para leerla."""
    p = _proyectos().get(proyecto) or {}
    mem = (Path(_valor(p, "memoria")).expanduser().resolve() if _valor(p, "memoria")
           else _mem_por_defecto(proyecto))
    raiz = _raiz(proyecto, verificar_existe=False)
    if mem == raiz or raiz in mem.parents:
        raise ErrorMemoria(f"The memory of '{proyecto}' is inside the code repository ({mem}); ADR-010 forbids it. "
                           f"Move it to {BASE_PROYECTOS / '.ratifact' / proyecto} and update projects.json.")
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
    return _valor(_proyectos()[proyecto], "escritura", [MEM, "docs"])


# ───────────────────────── rutas v1 de la memoria (alias) ─────────────────────────
# Tras la migración al esquema v2 siguen circulando rutas v1 (INDEX.md, docs/, cuerpos de registros, chats viejos):
# ".project/tareas/T-024.md". Se traduce SOLO el primer tramo después de .project/, se avisa en la respuesta
# ("(→ .project/<ruta nueva>)") y se registra en la telemetría (`alias_ruta`). Plan: se quita en 1.1, junto con el
# esquema.json centinela (ADR-030) y el respaldo MEMORIA_PROYECTOS_* (ADR-028), cuando analizar_uso muestre que ya no
# se usa.
ALIAS_RUTA: ContextVar[str | None] = ContextVar("alias_ruta", default=None)
VISTAS = {*VISTAS_V1, *VISTAS_V1.values()}


def _traducir_alias(proyecto: str, relativa: str, escribir: bool = False) -> str:
    """".project/tareas/x" → ".project/tasks/x" (y acuerdos.md/abiertas.md → DECISIONS.md/OPEN.md, solo lectura). Las
    rutas fuera de .project/ nunca se traducen. Si la memoria tiene la carpeta v1 y la v2 a la vez, ErrorMemoria."""
    partes = Path(relativa).parts if relativa else ()
    if len(partes) < 2 or partes[0] != MEM:
        return relativa
    if escribir and partes[1] in VISTAS and len(partes) == 2:
        raise ErrorMemoria(f"{MEM}/{partes[1]} is a view: it is regenerated from the records (decisions and "
                           "pending items) and is never written by hand.")
    nuevo = CARPETAS_V1.get(partes[1]) or (VISTAS_V1.get(partes[1]) if len(partes) == 2 else None)
    if not nuevo:
        return relativa
    mem = _mem(proyecto)
    if (mem / partes[1]).exists() and (mem / nuevo).exists():
        raise ErrorMemoria(f"The memory of '{proyecto}' ({mem}) is inconsistent: it has both {partes[1]} (v1) and "
                           f"{nuevo} (v2). Check it with git before continuing; the path was not translated.")
    traducida = Path(MEM, nuevo, *partes[2:]).as_posix()
    ALIAS_RUTA.set(traducida)
    return traducida


def _aviso_alias() -> str:
    """Línea "(→ .project/<ruta nueva>)" si esta llamada tradujo una ruta v1; vacía si no."""
    alias = ALIAS_RUTA.get()
    return f"(→ {alias})\n" if alias else ""


def _ruta_segura(proyecto: str, relativa: str, escribir: bool = False) -> Path:
    """Resuelve una ruta relativa dentro del proyecto; bloquea escapes, .git y zonas no autorizadas.
    Las rutas '.project/...' apuntan siempre a la carpeta de memoria, esté donde esté."""
    raiz = _raiz(proyecto)
    if not relativa or Path(relativa).is_absolute():
        raise ErrorMemoria("The path must be relative to the project root.")
    relativa = _traducir_alias(proyecto, relativa, escribir)
    partes_rel = Path(relativa).parts
    if partes_rel and partes_rel[0] == MEM:
        mem = _mem(proyecto)
        destino = (mem / Path(*partes_rel[1:])) if len(partes_rel) > 1 else mem
        destino = destino.resolve()
        if destino != mem and mem not in destino.parents or ".git" in destino.relative_to(mem).parts:
            raise ErrorMemoria("Path outside the project memory.")
        if escribir and MEM not in _zonas_escritura(proyecto):
            raise ErrorMemoria("Writing to the memory is not allowed.")
        return destino
    destino = (raiz / relativa).resolve()
    if destino != raiz and raiz not in destino.parents:
        raise ErrorMemoria("Path outside the project.")
    partes = destino.relative_to(raiz).parts
    if partes and partes[0] == ".git":
        raise ErrorMemoria("Access to .git is not allowed.")
    if escribir:
        zonas = _zonas_escritura(proyecto)
        en_subrepo = len(partes) > 1 and partes[0] in _repos(proyecto) and partes[1] in zonas
        if not partes or not (partes[0] in zonas or en_subrepo):
            raise ErrorMemoria(f"Writing is only allowed in: {', '.join(zonas)}"
                               + (f" (or <repo>/{zonas[-1]} with repo in {', '.join(_repos(proyecto))})"
                                  if _repos(proyecto) else ""))
    return destino
