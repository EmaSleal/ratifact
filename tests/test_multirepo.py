"""Proyectos de varios repositorios (p. ej. backend + app + frontend bajo una carpeta común)."""
import json
from pathlib import Path

import pytest

from conftest import crear_repo, log_git


@pytest.fixture
def multi(srv, entorno):
    raiz = entorno["base"] / "fractall"
    back = crear_repo(raiz / "backend")
    (back / "pom.xml").write_text("<project/>")
    (back / "mvnw").write_text("")
    front = crear_repo(raiz / "frontend")
    (front / "package.json").write_text('{"scripts": {"test": "vitest"}}')
    (front / ".gitignore").write_text("dist/\n")
    (front / "dist").mkdir()
    (front / "dist" / "bundle.js").write_text("// factura compilada\n")
    (front / "node_modules" / "x").mkdir(parents=True)
    (front / "node_modules" / "x" / "i.js").write_text("// factura dependencia\n")
    (front / "src").mkdir()
    (front / "src" / "factura.ts").write_text("export const factura = 1;\n")
    crear_repo(raiz / "app")                                     # repo sin pruebas reconocibles
    (raiz / "docs").mkdir()
    salida = srv.registrar_proyecto(nombre="fractall", ruta=str(raiz))
    return {"raiz": raiz, "salida": salida, "mem": entorno["base"] / ".memorias" / "fractall"}


def test_alta_detecta_repos_y_pruebas_por_repo(srv, multi, entorno):
    assert "varios repositorios: app, backend, frontend" in multi["salida"]
    assert "- `backend/`: `./mvnw test`" in multi["salida"] and "- `frontend/`: `npm test`" in multi["salida"]
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["fractall"]["pruebas"] == {"backend": "./mvnw test", "frontend": "npm test"}
    assert "repos: app, backend, frontend" in srv.listar_proyectos()


def test_tarea_exige_repositorio_y_verifica_en_el_suyo(srv, multi):
    assert "indica `repositorio`" in srv.registrar_tarea(proyecto="fractall", titulo="T", objetivo="o", criterios_aceptacion="c")
    assert "indica `repositorio`" in srv.registrar_tarea(proyecto="fractall", titulo="T", objetivo="o",
                                                         criterios_aceptacion="c", repositorio="otro")
    srv.registrar_tarea(proyecto="fractall", titulo="Consecutivos", objetivo="o", criterios_aceptacion="c",
                        repositorio="backend")
    tarea = next((multi["mem"] / "tareas").glob("T-001*.md")).read_text()
    assert "repositorio: backend" in tarea and "Desde `backend/`: `./mvnw test`" in tarea
    assert "en backend/" in srv.listar_tareas(proyecto="fractall")


def test_un_solo_repo_rechaza_repositorio(srv, proyecto):
    assert "un solo repositorio" in srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o",
                                                        criterios_aceptacion="c", repositorio="x")


def test_buscar_respeta_el_gitignore_de_cada_repo(srv, multi):
    salida = srv.buscar(proyecto="fractall", texto="factura")
    assert "frontend/src/factura.ts" in salida
    assert "dist/bundle" not in salida and "node_modules" not in salida


def test_documentos_en_subrepo_se_commitean_en_ese_repo(srv, multi):
    assert "(crear)" in srv.crear_documento(proyecto="fractall", ruta="backend/docs/api.md", contenido="# API")
    assert log_git(multi["raiz"] / "backend")[0] == "memoria: crear backend/docs/api.md"
    assert "Escritura solo permitida" in srv.crear_documento(proyecto="fractall", ruta="backend/src/A.java", contenido="x")
    assert "(sin git)" in srv.crear_documento(proyecto="fractall", ruta="docs/notas.md", contenido="raíz sin repo")


def test_configurar_pruebas_por_repo(srv, multi):
    assert "indica `repositorio`" in srv.configurar_pruebas(proyecto="fractall", comando="make test")
    assert "`app/`: `uv run pytest`" in srv.configurar_pruebas(proyecto="fractall", repositorio="app", comando="uv run pytest")
    assert "no es un repositorio" in srv.configurar_pruebas(proyecto="fractall", repositorio="nada")
    assert "app/: uv run pytest" in srv._comando_pruebas("fractall")
