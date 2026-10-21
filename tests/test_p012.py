"""P-012 (T-012): close_pending sobre un pendiente ya cerrado o con un decision_id inexistente falla sin escribir; los
ids de `decisions` de create_task se normalizan y deben existir. El contrato no cambia."""
from conftest import log_git
from memoria_v1 import foto


def _decisiones(srv, n):
    for i in range(n):
        srv.propose_decision(project="demo", title=f"D{i}", decision="d", rationale="j")


def test_cerrar_un_pendiente_ya_cerrado_falla_sin_escribir(srv, proyecto):
    srv.add_pending(project="demo", topic="Motor", context="c")
    assert "P-001 → closed" in srv.close_pending(project="demo", id="P-001", resolution="Godot")
    antes, commits = foto(proyecto["mem"]), log_git(proyecto["mem"])

    salida = srv.close_pending(project="demo", id="p-1", resolution="Otra cosa")

    fecha = next((proyecto["mem"] / "pending").glob("P-001-*.md")).read_text().split("closed: ")[1].split("\n")[0]
    assert salida == f"ERROR: P-001 is already closed since {fecha}; nothing was changed."
    assert foto(proyecto["mem"]) == antes and log_git(proyecto["mem"]) == commits


def test_decision_id_inexistente_falla_sin_escribir(srv, proyecto):
    srv.add_pending(project="demo", topic="Motor", context="c")
    _decisiones(srv, 1)
    antes, commits = foto(proyecto["mem"]), log_git(proyecto["mem"])

    salida = srv.close_pending(project="demo", id="P-001", resolution="Godot", decision_id="adr-7")

    assert salida == "ERROR: decision_id ADR-007 does not exist; nothing was changed."
    assert foto(proyecto["mem"]) == antes and log_git(proyecto["mem"]) == commits
    assert "P-001 → closed" in srv.close_pending(project="demo", id="P-001", resolution="Godot", decision_id="adr-1")


def test_create_task_normaliza_los_ids_de_decisions(srv, proyecto):
    _decisiones(srv, 2)
    salida = srv.create_task(project="demo", title="X", goal="g", acceptance_criteria="- c",
                             decisions=" adr-2, ADR-1 ,adr-02")
    assert "T-001 created" in salida, salida
    texto = next((proyecto["mem"] / "tasks").glob("T-001-*.md")).read_text()
    assert "## Applicable decisions\n\nADR-002, ADR-001\n" in texto


def test_create_task_con_una_decision_inexistente_falla_y_la_nombra(srv, proyecto):
    _decisiones(srv, 1)
    commits = log_git(proyecto["mem"])

    salida = srv.create_task(project="demo", title="X", goal="g", acceptance_criteria="- c",
                             decisions="ADR-1, adr-9, ADR-12")

    assert salida == "ERROR: Invalid `decisions`: ADR-009, ADR-012 (do not exist); nothing was created."
    assert not list((proyecto["mem"] / "tasks").glob("T-*.md")) and log_git(proyecto["mem"]) == commits
    assert "ADR-009 (does not exist)" in srv.create_task(project="demo", title="X", goal="g",
                                                         acceptance_criteria="- c", decisions="adr-9")
