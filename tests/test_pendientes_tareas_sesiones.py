"""Pendientes, tareas para el agente de código, sesiones, índice y contexto inicial."""
from conftest import log_git


def test_pendiente_abrir_y_cerrar(srv, proyecto):
    assert "P-001 recorded" in srv.add_pending(project="demo", topic="Parry", context="Sin decidir", owner="Emanuel")
    abiertas = (proyecto["mem"] / "OPEN.md").read_text()
    assert "P-001" in abiertas and "owner: Emanuel" in abiertas
    assert "P-001 → closed" in srv.close_pending(project="demo", id="P-001", resolution="Fuera del prototipo", decision_id="ADR-003")
    abiertas = (proyecto["mem"] / "OPEN.md").read_text()
    assert "- (none)" in abiertas.split("## Recently closed")[0] and "P-001 Parry (closed" in abiertas


def test_cerradas_recientes_se_limitan_y_no_inflan_el_contexto(srv, proyecto):
    for i in range(7):
        srv.add_pending(project="demo", topic=f"T{i}", context="c")
        srv.close_pending(project="demo", id=f"P-00{i + 1}", resolution="x" * 500)
    cerradas = (proyecto["mem"] / "OPEN.md").read_text().split("## Recently closed")[1]
    assert cerradas.count("\n- P-") == 5 and "xxxx" not in cerradas


def test_ciclo_de_una_tarea(srv, proyecto):
    salida = srv.create_task(project="demo", title="Ranuras de forma", goal="Dos ranuras",
                                 acceptance_criteria="- pruebas verdes", decisions="ADR-001", out_of_scope="Golem")
    assert "T-001 created" in salida and "/run-task T-001" in salida
    assert srv.update_task(project="demo", id="T-001", status="inventado").startswith("ERROR:")
    srv.update_task(project="demo", id="T-001", status="en_curso")
    srv.update_task(project="demo", id="T-001", status="en_revision", result="740/740 verdes", commit="abc123")
    texto = next((proyecto["mem"] / "tasks").glob("T-001*.md")).read_text()
    assert "status: in_review" in texto and "740/740 verdes" in texto and "commit: abc123" in texto
    assert "[in_review] Ranuras de forma" in srv.list_tasks(project="demo")
    srv.update_task(project="demo", id="T-001", status="integrada")
    assert srv.list_tasks(project="demo") == "(no tasks)"
    assert "[merged]" in srv.list_tasks(project="demo", include_closed=True)


def test_sesion_e_indice(srv, proyecto):
    assert "Session logged" in srv.log_session(project="demo", summary="Se decidió X")
    assert "Se decidió X" in next((proyecto["mem"] / "sessions").glob("*.md")).read_text()
    assert srv.update_index(project="demo", content="x" * 7000).startswith("ERROR:")
    assert "updated" in srv.update_index(project="demo", content="# Demo\nEstado: fase A")


def test_contexto_incluye_indice_abiertas_propuestas_y_tareas(srv, proyecto):
    srv.update_index(project="demo", content="# Demo\nEstado: fase A")
    srv.propose_decision(project="demo", title="X", decision="d", rationale="j")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    ctx = srv.get_context(project="demo")
    assert "Estado: fase A" in ctx and "# Open items (0)" in ctx
    assert "awaiting the user's acceptance: ADR-001" in ctx and "T-001" in ctx


def test_aviso_de_indice_desactualizado(srv, proyecto):
    srv.update_index(project="demo", content="# Demo")
    assert "desactualizado" not in srv.get_context(project="demo")
    for i in range(srv.UMBRAL_INDICE):
        srv.add_pending(project="demo", topic=f"T{i}", context="c")
    assert "INDEX.md is out of date" in srv.get_context(project="demo")
    srv.update_index(project="demo", content="# Demo al día")
    assert "desactualizado" not in srv.get_context(project="demo")


def _tarea_en_revision(srv):
    srv.create_task(project="demo", title="Tope NC", goal="o", acceptance_criteria="1. c")
    srv.update_task(project="demo", id="T-001", status="en_curso")
    srv.update_task(project="demo", id="T-001", status="en_revision", result="652 verdes", commit="c4eae6a")


def test_devolver_tarea_deja_revision_estructurada(srv, proyecto):
    """Hallazgo Fractall T-001: devolver con 'pendiente' confundía al agente (rama con commit + tarea 'pendiente')."""
    _tarea_en_revision(srv)
    assert srv.request_changes(project="demo", id="T-001", findings=" ").startswith("ERROR:")
    salida = srv.request_changes(project="demo", id="T-001", findings="Criterio 3 falla: fuga de tenant",
                                additional_criteria="6. 409 con mensaje fijo")
    assert "T-001 → changes_requested (review 1)" in salida and "/run-task T-001" in salida
    ruta = next((proyecto["mem"] / "tasks").glob("T-001*.md"))
    meta, cuerpo = srv._leer_registro(ruta)
    assert meta["status"] == "changes_requested" and meta["reviews"] == "1"
    assert "### Review 1 · " in cuerpo and "· changes_requested\n" in cuerpo and "SAME branch `t-001-tope-nc`" in cuerpo and "commit c4eae6a" in cuerpo
    assert "**Findings**\nCriterio 3 falla" in cuerpo
    assert "**Additional criteria**\n6. 409 con mensaje fijo" in cuerpo
    assert cuerpo.index("652 verdes") < cuerpo.index("### Review 1")      # historial en orden
    assert "[changes_requested] Tope NC" in srv.list_tasks(project="demo")
    assert log_git(proyecto["mem"])[0] == "memoria: T-001 → changes_requested (review 1)"
    # segunda vuelta: el agente corrige y vuelve a revisión; una nueva devolución numera la revisión 2
    srv.update_task(project="demo", id="T-001", status="en_curso")
    assert srv.request_changes(project="demo", id="T-001", findings="x").startswith("ERROR:")   # aún en curso
    srv.update_task(project="demo", id="T-001", status="en_revision", result="corregido")
    assert "review 2" in srv.request_changes(project="demo", id="T-001", findings="falta javadoc")


def test_no_se_devuelve_por_atajos(srv, proyecto):
    _tarea_en_revision(srv)
    assert "request_changes" in srv.update_task(project="demo", id="T-001", status="pendiente")
    assert "request_changes" in srv.update_task(project="demo", id="T-001", status="devuelta")
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "tasks").glob("T-001*.md")))
    assert meta["status"] == "in_review"
