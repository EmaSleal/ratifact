"""Fixtures comunes: cada prueba corre contra una carpeta de proyectos temporal, con su propio projects.json,
log de telemetría y configuración de git aislada (no toca la configuración ni los proyectos reales)."""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_REPO))


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Carpeta de proyectos vacía + variables de entorno que el servidor y git respetan."""
    base = tmp_path / "Projects"
    base.mkdir()
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("")
    variables = {
        "MEMORIA_PROYECTOS_CONFIG": str(tmp_path / "projects.json"),
        "MEMORIA_PROYECTOS_LOG": str(tmp_path / "logs" / "uso.jsonl"),
        "MEMORIA_PROYECTOS_BASE": str(base),
        "GIT_CONFIG_GLOBAL": str(gitconfig),     # sin firmas ni hooks del usuario
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "pruebas", "GIT_AUTHOR_EMAIL": "pruebas@local",
        "GIT_COMMITTER_NAME": "pruebas", "GIT_COMMITTER_EMAIL": "pruebas@local",
    }
    for k, v in variables.items():
        monkeypatch.setenv(k, v)
    return {"base": base, "tmp": tmp_path, "env": variables}


# Módulos de ratifact en orden de dependencias. app va antes que las herramientas: al recargarlo se crea un `mcp`
# nuevo, y al recargar cada módulo de herramientas sus decoradores las registran en ese `mcp` (sin duplicados).
MODULOS_RATIFACT = [
    "ratifact.config", "ratifact.registros", "ratifact.esquema", "ratifact.plantillas", "ratifact.app",
    "ratifact.herramientas.contexto_documentos", "ratifact.herramientas.decisiones",
    "ratifact.herramientas.pendientes_sesiones", "ratifact.herramientas.tareas", "ratifact.herramientas.proyectos",
    "ratifact.herramientas", "ratifact.prompts",
]


def recargar_servidor():
    """Recarga cada módulo de ratifact (en orden de dependencias) y luego servidor, para que lean las variables
    de entorno actuales (MEMORIA_PROYECTOS_CONFIG / _LOG / _BASE se leen al importar)."""
    import servidor
    for nombre in MODULOS_RATIFACT:
        importlib.reload(importlib.import_module(nombre))
    return importlib.reload(servidor)


@pytest.fixture
def srv(entorno):
    """Módulo del servidor recargado para que lea la configuración del entorno de prueba."""
    return recargar_servidor()


def crear_repo(ruta: Path) -> Path:
    ruta.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(ruta)], check=True)
    (ruta / "docs").mkdir(exist_ok=True)
    (ruta / "docs" / "vision.md").write_text("# Visión\nUn lobo alfa lidera la manada.\n")
    subprocess.run(["git", "-C", str(ruta), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(ruta), "commit", "-q", "-m", "base"], check=True)
    return ruta


@pytest.fixture
def proyecto(srv, entorno):
    """Proyecto 'demo' registrado con registrar_proyecto (memoria en <base>/.memorias/demo)."""
    repo = crear_repo(entorno["base"] / "demo" / "codigo")
    salida = srv.registrar_proyecto(nombre="demo", ruta=str(repo))
    assert not salida.startswith("ERROR"), salida
    return {"nombre": "demo", "repo": repo, "mem": entorno["base"] / ".memorias" / "demo"}


def log_git(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-C", str(repo), "log", "--format=%s"], capture_output=True, text=True)
    return r.stdout.splitlines()
