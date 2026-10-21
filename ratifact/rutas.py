"""Rutas que no dependen de projects.json (sin importar nada de ratifact): configuración nueva y vieja, log de
telemetría por defecto (XDG, fuera del paquete) y de dónde corre el paquete (instalación fija o copia de trabajo, y el
repositorio de origen). Todas se calculan en cada llamada, con el entorno de ese momento."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

SUFIJO_RESPALDO = ".bak-v1"     # ratifact upgrade renombra el projects.json viejo a projects.json.bak-v1 (ADR-029)


def config_nueva() -> Path:
    return Path.home() / ".config" / "ratifact" / "projects.json"


def config_vieja() -> Path:
    return Path.home() / ".config" / "memoria-proyectos" / "projects.json"


def respaldo(config: Path) -> Path:
    return config.with_name(config.name + SUFIJO_RESPALDO)


def log_por_defecto() -> Path:
    """$XDG_STATE_HOME/ratifact/uso.jsonl (por defecto ~/.local/state/ratifact/uso.jsonl): nunca dentro del paquete."""
    estado = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(estado).expanduser() / "ratifact" / "uso.jsonl"


def _paquete() -> Path:
    return Path(__file__).resolve().parent


def es_copia_de_trabajo(paquete: Path | None = None) -> bool:
    """¿El paquete corre desde el repositorio (pyproject.toml y servidor.py al lado) y no desde una instalación?"""
    raiz = (paquete or _paquete()).parent
    return (raiz / "pyproject.toml").is_file() and (raiz / "servidor.py").is_file()


def origen(paquete: Path | None = None) -> Path | None:
    """Repositorio de donde viene el código: la copia de trabajo misma o, en una instalación fija (`uv tool install
    <ruta>`), la carpeta que registró el instalador en direct_url.json (PEP 610). None si no se sabe."""
    paquete = paquete or _paquete()
    if es_copia_de_trabajo(paquete):
        return paquete.parent
    try:
        from importlib.metadata import PackageNotFoundError, distribution
        try:
            datos = json.loads(distribution("ratifact").read_text("direct_url.json") or "{}")
        except PackageNotFoundError:
            return None
    except (ValueError, OSError):
        return None
    url = urlparse(datos.get("url", ""))
    ruta = Path(unquote(url.path)) if url.scheme == "file" else None
    return ruta if ruta and ruta.is_dir() else None


def log_viejo(paquete: Path | None = None) -> Path | None:
    """<repo>/logs/uso.jsonl, donde escribía el servidor antes de T-012 (None si no se conoce el repositorio)."""
    repo = origen(paquete)
    return repo / "logs" / "uso.jsonl" if repo else None
