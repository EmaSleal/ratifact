"""Estructura del paquete ratifact (ADR-020): servidor.py delgado, módulos acotados, sin importaciones circulares,
rutas por defecto en la raíz del repositorio y aislamiento del entorno entre pruebas."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import RAIZ_REPO, crear_repo, recargar_servidor

PAQUETE = RAIZ_REPO / "ratifact"
MODULOS = sorted(PAQUETE.rglob("*.py"))


def _nombre_modulo(p: Path) -> str:
    partes = p.relative_to(RAIZ_REPO).with_suffix("").parts
    return ".".join(partes[:-1] if partes[-1] == "__init__" else partes)


def test_servidor_es_un_punto_de_entrada_delgado():
    assert len((RAIZ_REPO / "servidor.py").read_text(encoding="utf-8").splitlines()) <= 60


@pytest.mark.parametrize("modulo", MODULOS, ids=lambda p: str(p.relative_to(RAIZ_REPO)))
def test_ningun_modulo_supera_300_lineas(modulo):
    assert len(modulo.read_text(encoding="utf-8").splitlines()) <= 300


@pytest.mark.parametrize("nombre", [_nombre_modulo(p) for p in MODULOS])
def test_cada_modulo_se_importa_solo(nombre, entorno):
    """En un proceso nuevo y sin importar nada antes: falla si hay importaciones circulares."""
    r = subprocess.run([sys.executable, "-c", f"import {nombre}"], cwd=RAIZ_REPO, capture_output=True, text=True,
                       env={**os.environ, **entorno["env"]})
    assert r.returncode == 0, r.stderr


def test_rutas_por_defecto_en_la_raiz_del_repositorio(srv, monkeypatch):
    """Sin MEMORIA_PROYECTOS_LOG, la telemetría va a <repo>/logs/uso.jsonl (no a ratifact/logs). No escribe nada."""
    monkeypatch.delenv("MEMORIA_PROYECTOS_LOG")
    srv = recargar_servidor()
    from ratifact import app, config
    assert app.LOG_USO == RAIZ_REPO / "logs" / "uso.jsonl"
    assert srv.LOG_USO == app.LOG_USO
    assert config._DIR == RAIZ_REPO
    assert (config._DIR / "skills" / "tarea" / "SKILL.md").is_file()


_BASES_VISTAS = []


@pytest.mark.parametrize("nombre", ["uno", "dos"])
def test_cada_prueba_registra_bajo_su_propia_base(srv, entorno, nombre):
    """Dos pruebas seguidas con MEMORIA_PROYECTOS_BASE distintas: cada una registra solo bajo la suya."""
    from ratifact import config
    base = entorno["base"].resolve()
    assert config.BASE_PROYECTOS == base
    assert config.CONFIG == Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    repo = crear_repo(entorno["base"] / nombre / "codigo")
    salida = srv.registrar_proyecto(nombre=nombre, ruta=str(repo))
    assert not salida.startswith("ERROR"), salida
    proyectos = json.loads(config.CONFIG.read_text(encoding="utf-8"))
    assert list(proyectos) == [nombre]
    assert Path(proyectos[nombre]["memoria"]) == base / ".memorias" / nombre
    assert (base / ".memorias" / nombre / ".git").exists()
    if nombre == "dos" and not _BASES_VISTAS:
        pytest.skip("la comparación necesita que 'uno' haya corrido antes en la misma sesión")
    for anterior in _BASES_VISTAS:
        assert anterior != base
        assert not (anterior / ".memorias" / nombre).exists()
    _BASES_VISTAS.append(base)
