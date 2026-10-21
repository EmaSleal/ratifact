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
    salida = srv.register_project(name="fractall", path=str(raiz))
    return {"raiz": raiz, "salida": salida, "mem": entorno["base"] / ".ratifact" / "fractall"}


def test_alta_detecta_repos_y_pruebas_por_repo(srv, multi, entorno):
    assert "Multi-repo project: app, backend, frontend" in multi["salida"]
    assert "in the root folder AND in each repo" in multi["salida"]      # Codex no sube más allá del repo git
    assert "- `backend/`: `./mvnw test`" in multi["salida"] and "- `frontend/`: `npm test`" in multi["salida"]
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["fractall"]["tests"] == {"backend": "./mvnw test", "frontend": "npm test"}
    assert "repos: app, backend, frontend" in srv.list_projects()


def test_tarea_exige_repositorio_y_verifica_en_el_suyo(srv, multi):
    assert "give `repo`" in srv.create_task(project="fractall", title="T", goal="o", acceptance_criteria="c")
    assert "give `repo`" in srv.create_task(project="fractall", title="T", goal="o",
                                                         acceptance_criteria="c", repo="otro")
    srv.create_task(project="fractall", title="Consecutivos", goal="o", acceptance_criteria="c",
                        repo="backend")
    tarea = next((multi["mem"] / "tasks").glob("T-001*.md")).read_text()
    assert "\nrepo: backend\n" in tarea and "From `backend/`: `./mvnw test`" in tarea
    assert "in backend/" in srv.list_tasks(project="fractall")


def test_un_solo_repo_ignora_repositorio(srv, proyecto):
    """T-007: antes era un error; ahora el valor se ignora y la respuesta lo avisa (ver test_catalogo.py)."""
    salida = srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", repo="x")
    assert not salida.startswith("ERROR") and "`repo` was ignored" in salida


def test_buscar_respeta_el_gitignore_de_cada_repo(srv, multi):
    salida = srv.search(project="fractall", query="factura")
    assert "frontend/src/factura.ts" in salida
    assert "dist/bundle" not in salida and "node_modules" not in salida


def test_documentos_en_subrepo_se_commitean_en_ese_repo(srv, multi):
    assert "(create)" in srv.create_document(project="fractall", path="backend/docs/api.md", content="# API")
    assert log_git(multi["raiz"] / "backend")[0] == "memoria: crear backend/docs/api.md"
    assert "Writing is only allowed" in srv.create_document(project="fractall", path="backend/src/A.java", content="x")
    assert "(no git)" in srv.create_document(project="fractall", path="docs/notas.md", content="raíz sin repo")


def test_actualizar_proyecto_pruebas_por_repo(srv, multi):
    assert "give `repo`" in srv.update_project(name="fractall", tests="make test")
    assert "Unrecognized" in srv.update_project(name="fractall", repo="app")  # sin comando ni archivos reconocibles
    salida = srv.update_project(name="fractall", repo="app", tests="uv run pytest")
    assert "`app/`: `uv run pytest`" in salida
    assert "Updated block" in salida and "- `app/`: `uv run pytest`" in salida   # el bloque ya trae el cambio
    assert "is not a repository" in srv.update_project(name="fractall", repo="nada")
    assert "app/: uv run pytest" in srv._comando_pruebas("fractall")
    # auto-detección si se omite `pruebas` (criterio 4): mismo comportamiento que configurar_pruebas
    assert "`backend/`: `./mvnw test` (detected)" in srv.update_project(name="fractall", repo="backend")


def test_git_vacio_del_sandbox_de_codex_no_rompe_la_deteccion(srv, multi):
    """Hallazgo Codex/Fractall: al abrir Codex en la raíz, su sandbox crea .git/.agents/.codex vacíos ahí.
    Con eso la raíz parecía un repo y el proyecto dejaba de verse como multi-repo."""
    for d in (".git", ".agents", ".codex"):
        (multi["raiz"] / d).mkdir()
    assert srv._repos("fractall") == ["app", "backend", "frontend"]
    assert "suggested branch" in srv.create_task(project="fractall", title="Y", goal="o",
                                                  acceptance_criteria="c", repo="backend")
