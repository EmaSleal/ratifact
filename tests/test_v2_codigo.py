"""T-010, código sobre el schema v2: estados en los dos idiomas (criterio 10), idioma del contenido en el arranque
(11), claves de projects.json en español e inglés (12), analizar_uso con memorias v1 y v2 (13) y rutas v1 de la
memoria traducidas de forma visible, registrada y acotada (19–23)."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from conftest import crear_repo, log_git
from test_analizar_uso import _correr, _log_filas


def _config(entorno) -> Path:
    return Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])


def _filas_log(entorno) -> list[dict]:
    return [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]


# ───────────────────────── criterio 10: estados en español o inglés ─────────────────────────

@pytest.mark.parametrize("en_curso,en_revision,fallida,integrada", [
    ("en_curso", "en_revision", "fallida", "integrada"), ("in_progress", "in_review", "failed", "merged"),
    ("EN_CURSO", " In_Review ", "Failed", "INTEGRADA")])
def test_actualizar_tarea_acepta_los_dos_idiomas_y_guarda_ingles(srv, proyecto, en_curso, en_revision, fallida,
                                                                 integrada):
    """update_task es la única herramienta que recibe un estado (las demás lo fijan por sí mismas)."""
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    for dado, guardado in ((en_curso, "in_progress"), (en_revision, "in_review"), (fallida, "failed"),
                           (en_revision, "in_review"), (integrada, "merged")):
        salida = srv.update_task(project="demo", id="T-001", status=dado, result=f"paso {guardado}")
        assert re.match(rf"T-001 → {guardado} · commit \S+", salida), salida
        meta, cuerpo = srv._leer_registro(next((proyecto["mem"] / "tasks").glob("T-001*.md")))
        assert meta["status"] == guardado and f"· {guardado}\npaso {guardado}" in cuerpo


@pytest.mark.parametrize("estado", ["devuelta", "changes_requested"])
def test_devolver_por_estado_se_rechaza_en_los_dos_idiomas(srv, proyecto, estado):
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    assert "request_changes" in srv.update_task(project="demo", id="T-001", status=estado)


@pytest.mark.parametrize("estado", ["pendiente", "todo"])
def test_en_revision_no_vuelve_a_todo_en_los_dos_idiomas(srv, proyecto, estado):
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    srv.update_task(project="demo", id="T-001", status="in_review")
    assert "request_changes" in srv.update_task(project="demo", id="T-001", status=estado)


def test_estado_desconocido_lista_los_validos(srv, proyecto):
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    salida = srv.update_task(project="demo", id="T-001", status="hecha")
    assert salida.startswith("ERROR: Invalid status 'hecha'. Use: todo, in_progress, in_review") and "en_curso" in salida


def test_en_curso_en_ingles_trae_la_guia_de_integraciones(srv, proyecto):
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    assert "Integration guidance" in srv.update_task(project="demo", id="T-001", status="in_progress")


def test_merged_en_ingles_recuerda_los_pendientes(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="c")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", resolves="P-1 (partial)")
    assert "P-001 (partial) is still open" in srv.update_task(project="demo", id="T-001", status="merged")


# ───────────────────────── criterio 9 y 11: memoria nueva e idioma del contenido ─────────────────────────

def test_memoria_nueva_en_v2(srv, proyecto):
    mem = proyecto["mem"]
    assert sorted(p.name for p in mem.iterdir() if p.is_dir() and p.name != ".git") == \
        ["decisions", "pending", "sessions", "tasks"]
    assert (mem / "DECISIONS.md").read_text().startswith("# Decisions\n")
    assert (mem / "OPEN.md").read_text().startswith("# Open items\n")
    assert not (mem / "acuerdos.md").exists() and not (mem / "abiertas.md").exists()


def test_obtener_contexto_dice_el_idioma_del_contenido(srv, proyecto):
    linea = [l for l in srv.get_context(project="demo").splitlines() if l.startswith("Content language")]
    assert len(linea) == 1 and linea[0].startswith("Content language: en — write the content of the records")
    (proyecto["mem"] / "schema.json").write_text('{"version": 2, "content_language": "es"}\n')
    assert "Content language: es — " in srv.get_context(project="demo")


def test_registros_nuevos_en_formato_v2(srv, proyecto):
    srv.propose_decision(project="demo", title="A", decision="d", rationale="j", alternatives="x")
    srv.accept_decision(project="demo", id="ADR-1", user_quote="sí")
    srv.propose_decision(project="demo", title="B", decision="d", rationale="j")
    srv.reject_decision(project="demo", id="ADR-2", reason="no va")
    srv.add_pending(project="demo", topic="P", context="c", owner="Ema")
    srv.close_pending(project="demo", id="P-1", resolution="listo")
    srv.log_session(project="demo", summary="hecho")
    mem = proyecto["mem"]
    a = next((mem / "decisions").glob("ADR-001*")).read_text()
    assert re.search(r"\nstatus: accepted\n.*\naccepted: \d{4}-", a, re.S)
    assert "## Decision\nd" in a and "## Rationale\nj" in a and "## Alternatives considered\nx" in a
    assert re.search(r"## Acceptance \(\d{4}-\d{2}-\d{2}\)\n> sí", a)
    b = next((mem / "decisions").glob("ADR-002*")).read_text()
    assert "\nstatus: rejected\n" in b and "\nrejected: " in b and "## Rejected (" in b
    p = next((mem / "pending").glob("P-001*")).read_text()
    assert all(f"\n{k}: " in p for k in ("topic", "status", "date", "created", "owner", "closed", "resolution"))
    assert "## Resolution (" in p and "\nstatus: closed\n" in p
    assert next((mem / "sessions").glob("*.md")).read_text().startswith("# Sessions ")
    for texto in (a, b, p):
        assert not re.search(r"^(titulo|estado|fecha|resumen|tema|dueno|creado|cerrado|resolucion|confirmada|"
                             r"descartada):", texto, re.M), texto


# ───────────────────────── criterio 12: projects.json en español o inglés ─────────────────────────

def _proyecto_en_ingles(entorno, **extra) -> dict:
    repo = crear_repo(entorno["base"] / "ing" / "codigo")
    mem = entorno["base"] / ".memorias" / "ing"
    entrada = {"path": str(repo), "memory": str(mem), "writable": [".project", "docs"], "tests": "make test", **extra}
    datos = json.loads(_config(entorno).read_text()) if _config(entorno).exists() else {}
    _config(entorno).write_text(json.dumps({**datos, "ing": entrada}, indent=2))
    return {"repo": repo, "mem": mem}


def test_claves_inglesas_de_projects_json(srv, proyecto, entorno):
    p = _proyecto_en_ingles(entorno)
    assert srv.init_memory(project="ing").startswith("Memory initialized")
    assert (p["mem"] / "schema.json").exists()
    srv.create_task(project="ing", title="T", goal="o", acceptance_criteria="c")
    assert "From the repository root: `make test`" in next((p["mem"] / "tasks").glob("T-*")).read_text()
    assert "saved (create)" in srv.create_document(project="ing", path="docs/nuevo.md", content="x")
    assert f"- ing: {p['repo']}" in srv.list_projects()


def test_si_estan_las_dos_gana_la_inglesa(srv, proyecto, entorno):
    p = _proyecto_en_ingles(entorno, ruta="/no/existe", pruebas="viejo", escritura=["docs"])
    srv.init_memory(project="ing")
    srv.create_task(project="ing", title="T", goal="o", acceptance_criteria="c")
    assert "`make test`" in next((p["mem"] / "tasks").glob("T-*")).read_text()
    assert not srv.create_document(project="ing", path=".project/x.md", content="x").startswith("ERROR")


def test_las_escrituras_conservan_la_grafia_existente(srv, proyecto, entorno):
    _proyecto_en_ingles(entorno)
    datos = json.loads(_config(entorno).read_text())        # demo as written before T-013 (Spanish keys)
    datos["demo"] = {{"path": "ruta", "memory": "memoria", "writable": "escritura", "tests": "pruebas"}.get(k, k): v
                     for k, v in datos["demo"].items()}
    _config(entorno).write_text(json.dumps(datos))
    srv.update_project(name="ing", tests="pytest -q")
    srv.update_project(name="demo", tests="npm test")
    datos = json.loads(_config(entorno).read_text())
    assert datos["ing"]["tests"] == "pytest -q" and "pruebas" not in datos["ing"]
    assert datos["demo"]["pruebas"] == "npm test" and "tests" not in datos["demo"]


def test_alta_nueva_usa_la_grafia_del_archivo(srv, entorno):
    repo = crear_repo(entorno["base"] / "uno" / "codigo")
    _config(entorno).write_text(json.dumps({"base": {"path": str(repo), "memory": str(entorno["base"] / "m")}}))
    repo2 = crear_repo(entorno["base"] / "dos" / "codigo")
    assert not srv.register_project(name="dos", path=str(repo2)).startswith("ERROR")
    assert set(json.loads(_config(entorno).read_text())["dos"]) == {"path", "memory", "writable", "tests"}


def test_la_migracion_nunca_reescribe_projects_json(srv, proyecto_v1, entorno):
    antes = _config(entorno).read_bytes()
    assert "migrated to schema v2" in srv.get_context(project="demo")
    assert _config(entorno).read_bytes() == antes


# ───────────────────────── criterio 13: analizar_uso con memorias v1 y v2 ─────────────────────────

def test_analizar_uso_higiene_y_arranque_con_memoria_v1_y_v2(srv, proyecto_v1, entorno, monkeypatch, capsys):
    """'demo' queda en v1 (nadie la abrió con el servidor nuevo); 'ing' es v2. Ambas aparecen en la higiene."""
    p = _proyecto_en_ingles(entorno)
    srv.init_memory(project="ing")
    srv.add_pending(project="ing", topic="Abierto", context="c")
    srv.create_task(project="ing", title="T", goal="cubre P-001", acceptance_criteria="c", resolves="P-1")
    srv.update_task(project="ing", id="T-1", status="merged")
    assert (proyecto_v1["mem"] / "tareas").is_dir() and not (proyecto_v1["mem"] / "tasks").exists()   # sigue v1
    hoy = dt.date.today().isoformat()
    filas = [{"herramienta": "get_context", "resp_chars": 4000, "proyecto": n} for n in ("demo", "ing")]
    _correr(monkeypatch, "--log", str(_log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)))
    salida = capsys.readouterr().out
    assert "  demo: p50 4000 characters" in salida and "  ing: p50 4000 characters" in salida
    seccion = salida.split("Open pending items referenced by merged tasks\n")[1]
    demo, ing = seccion.split("  ing\n")
    assert "declared in resolves:\n      P-001: T-001 (merged 2026-10-06)" in demo      # v1: "integrada", "resuelve"
    assert f"declared in resolves:\n      P-001: T-001 (merged {hoy})" in ing          # v2: "merged", "resolves"
    assert (proyecto_v1["mem"] / "tareas").is_dir()                                        # analizar_uso no migra
    assert p["mem"].is_dir()


# ───────────────────────── criterios 19–23: rutas v1 de la memoria ─────────────────────────

@pytest.fixture
def con_registros(srv, proyecto):
    srv.create_task(project="demo", title="Uno", goal="o", acceptance_criteria="c")
    srv.add_pending(project="demo", topic="Abierto", context="c")
    srv.log_session(project="demo", summary="hecho")
    return proyecto


def test_leer_con_carpeta_v1_avisa_la_ruta_nueva(srv, con_registros):
    real = next((con_registros["mem"] / "tasks").glob("T-001*")).name
    salida = srv.read_document(project="demo", path=f".project/tareas/{real}")
    assert salida.startswith(f"(→ .project/tasks/{real})\n---\nid: T-001")
    hoy = dt.date.today().isoformat()
    assert srv.read_document(project="demo", path=f".project/sesiones/{hoy}.md").startswith(
        f"(→ .project/sessions/{hoy}.md)\n# Sessions {hoy}")
    vista = srv.read_document(project="demo", path=".project/abiertas.md")
    assert vista.startswith("(→ .project/OPEN.md)\n# Open items")
    assert srv.read_document(project="demo", path=".project/acuerdos.md").startswith("(→ .project/DECISIONS.md)\n")


def test_listar_con_carpeta_v1_avisa_en_una_linea_antes(srv, con_registros):
    salida = srv.list_documents(project="demo", folder=".project/pendientes").splitlines()
    assert salida[0] == "(→ .project/pending)" and salida[1].startswith("P-001 · open · Abierto  (.project/pending/")
    assert srv.list_documents(project="demo", folder=".project/pending").splitlines()[0].startswith("P-001")


def test_escribir_con_carpeta_v1_avisa(srv, con_registros):
    salida = srv.create_document(project="demo", path=".project/tareas/notas.md", content="x")
    assert salida.startswith("(→ .project/tasks/notas.md)\n.project/tasks/notas.md saved (create)")
    assert (con_registros["mem"] / "tasks" / "notas.md").exists() and not (con_registros["mem"] / "tareas").exists()


@pytest.mark.parametrize("vista", ["acuerdos.md", "abiertas.md", "DECISIONS.md", "OPEN.md"])
def test_las_vistas_no_se_escriben(srv, con_registros, vista):
    antes = log_git(con_registros["mem"])
    for herramienta in (srv.update_document, srv.create_document):
        salida = herramienta(project="demo", path=f".project/{vista}", content="a mano")
        assert salida.startswith("ERROR:") and "is a view" in salida and "is regenerated" in salida, salida
    assert log_git(con_registros["mem"]) == antes


def test_fuera_de_project_no_se_traduce(srv, con_registros):
    (con_registros["repo"] / "docs" / "tareas").mkdir()
    (con_registros["repo"] / "docs" / "tareas" / "x.md").write_text("del código\n")
    assert srv.read_document(project="demo", path="docs/tareas/x.md") == "del código"
    salida = srv.create_document(project="demo", path="docs/pendientes/y.md", content="y")
    assert salida.startswith("docs/pendientes/y.md saved") and (con_registros["repo"] / "docs/pendientes/y.md").exists()


def test_carpeta_v1_y_v2_a_la_vez_es_error(srv, con_registros):
    (con_registros["mem"] / "tareas").mkdir()
    salida = srv.read_document(project="demo", path=".project/tareas/T-001.md")
    assert salida.startswith("ERROR:") and "inconsistent" in salida and "both tareas (v1) and tasks (v2)" in salida
    assert str(con_registros["mem"]) in salida
    assert srv.list_documents(project="demo", folder=".project/tareas").startswith("ERROR:")


def test_telemetria_y_analizar_uso_cuentan_los_alias(srv, con_registros, entorno, monkeypatch, capsys):
    srv.read_document(project="demo", path=".project/acuerdos.md")
    srv.list_documents(project="demo", folder=".project/tareas")
    srv.list_documents(project="demo", folder=".project/tasks")
    filas = [f for f in _filas_log(entorno) if f["herramienta"] in ("read_document", "list_documents")]
    assert [f.get("alias_ruta") for f in filas] == [".project/DECISIONS.md", ".project/tasks", None]
    _correr(monkeypatch, "--log", entorno["env"]["MEMORIA_PROYECTOS_LOG"])
    salida = capsys.readouterr().out
    assert "- v1 paths translated (alias, removed in 1.1): \n  demo: 2 uses · " in salida


def test_sin_alias_analizar_uso_dice_ninguna(srv, proyecto, entorno, monkeypatch, capsys):
    srv.list_documents(project="demo", folder=".project")
    _correr(monkeypatch, "--log", entorno["env"]["MEMORIA_PROYECTOS_LOG"])
    assert "- v1 paths translated (alias, removed in 1.1): none" in capsys.readouterr().out
