"""Backlog punto 4: cada proyecto declara cómo se verifica; /tarea no asume ningún stack."""
import json
from pathlib import Path

import pytest

from conftest import crear_repo


@pytest.mark.parametrize("archivos, esperado", [
    ({"pom.xml": ""}, "mvn test"),
    ({"pom.xml": "", "mvnw": ""}, "./mvnw test"),
    ({"build.gradle.kts": "", "gradlew": ""}, "./gradlew test"),
    ({"package.json": '{"scripts": {"test": "jest"}}', "pnpm-lock.yaml": ""}, "pnpm test"),
    ({"package.json": '{"scripts": {"build": "tsc"}}'}, ""),
    ({"project.godot": "", "tests/run_tests.gd": "", "tests/run_tests_hito1.gd": "", "tests/otro.gd": ""},
     "godot --headless --path . -s res://tests/run_tests.gd && godot --headless --path . -s res://tests/run_tests_hito1.gd"),
    ({"pyproject.toml": ""}, "python -m pytest -q"),
    ({"pyproject.toml": "", "uv.lock": ""}, "uv run pytest -q"),
    ({"go.mod": ""}, "go test ./..."),
    ({"README.md": ""}, ""),
])
def test_deteccion_por_tipo_de_proyecto(srv, tmp_path, archivos, esperado):
    for nombre, contenido in archivos.items():
        (tmp_path / nombre).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / nombre).write_text(contenido)
    assert srv._detectar_pruebas(tmp_path) == esperado


def test_alta_detecta_y_lo_muestra_en_instrucciones_y_tareas(srv, entorno):
    repo = crear_repo(entorno["base"] / "erp")
    (repo / "pom.xml").write_text("<project/>")
    salida = srv.register_project(name="erp", path=str(repo))
    assert "Test command (from the repository root): `mvn test`" in salida
    srv.create_task(project="erp", title="Endpoint pedidos", goal="o", acceptance_criteria="c")
    tarea = next((entorno["base"] / ".memorias" / "erp" / "tasks").glob("T-001*.md")).read_text()
    assert "## How to verify" in tarea and "`mvn test`" in tarea


def test_comando_explicito_y_actualizar_proyecto(srv, entorno):
    """configurar_pruebas se eliminó; update_project(pruebas=..., repositorio=...) la reemplaza con el
    mismo comportamiento (comando explícito, auto-detección, error si no se reconoce el tipo de proyecto)."""
    repo = crear_repo(entorno["base"] / "web")
    srv.register_project(name="web", path=str(repo), tests="make check")
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["web"]["pruebas"] == "make check"
    (repo / "go.mod").write_text("module web")
    assert "`go test ./...`" in srv.update_project(name="web", tests="go test ./...")
    assert "`npm run e2e`" in srv.update_project(name="web", tests="npm run e2e")
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["web"]["pruebas"] == "npm run e2e"
    assert "is not registered" in srv.update_project(name="nada", tests="x") or \
        srv.update_project(name="nada", tests="x").startswith("ERROR")


def test_tarea_sin_comando_pide_configurarlo(srv, proyecto):
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    tarea = next((proyecto["mem"] / "tasks").glob("T-001*.md")).read_text()
    assert "no test command configured" in tarea


def test_plantilla_tarea_no_asume_proyecto_ni_stack():
    from conftest import RAIZ_REPO
    texto = (RAIZ_REPO / "run-task.md").read_text()
    for especifico in ("game", "godot", "src/sim", "data/*.json"):
        assert especifico not in texto.lower(), especifico
    assert "How to verify" in texto
