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
    salida = srv.registrar_proyecto(nombre="erp", ruta=str(repo))
    assert "Comando de pruebas (desde la raíz del repositorio): `mvn test`" in salida
    srv.registrar_tarea(proyecto="erp", titulo="Endpoint pedidos", objetivo="o", criterios_aceptacion="c")
    tarea = next((entorno["base"] / ".memorias" / "erp" / "tareas").glob("T-001*.md")).read_text()
    assert "## Cómo verificar" in tarea and "`mvn test`" in tarea


def test_comando_explicito_y_configurar_pruebas(srv, entorno):
    repo = crear_repo(entorno["base"] / "web")
    srv.registrar_proyecto(nombre="web", ruta=str(repo), pruebas="make check")
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["web"]["pruebas"] == "make check"
    assert "No se reconoce" in srv.configurar_pruebas(proyecto="web")          # sin archivos reconocibles
    (repo / "go.mod").write_text("module web")
    assert "`go test ./...` (detectado)" in srv.configurar_pruebas(proyecto="web")
    assert "`npm run e2e`" in srv.configurar_pruebas(proyecto="web", comando="npm run e2e")
    assert "configurar_pruebas" in srv.configurar_pruebas(proyecto="nada") or \
        srv.configurar_pruebas(proyecto="nada").startswith("ERROR")


def test_tarea_sin_comando_pide_configurarlo(srv, proyecto):
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c")
    tarea = next((proyecto["mem"] / "tareas").glob("T-001*.md")).read_text()
    assert "sin comando de pruebas configurado" in tarea


def test_plantilla_tarea_no_asume_proyecto_ni_stack():
    from conftest import RAIZ_REPO
    texto = (RAIZ_REPO / "tarea.md").read_text()
    for especifico in ("game", "godot", "src/sim", "data/*.json"):
        assert especifico not in texto.lower(), especifico
    assert "Cómo verificar" in texto
