"""T-026: expose decision age and current lifecycle status without changing task records."""
import datetime as dt
import re

from conftest import log_git
from ratifact import registros


def _adr(mem, id_, status="proposed", date="2026-11-01", extra=""):
    folder = mem / "decisions"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{id_}-decision.md"
    fields = f"id: {id_}\ntitle: Decision {id_}\nstatus: {status}"
    if date is not None:
        fields += f"\ndate: {date}"
    path.write_text(f"---\n{fields}\n{extra}---\n# {id_}\n", encoding="utf-8")
    return path


def test_get_context_shows_age_orders_by_date_and_suggests_oldest_batch(srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    _adr(proyecto["mem"], "ADR-004", date="2026-10-05")  # 41 days
    _adr(proyecto["mem"], "ADR-003", date="2026-11-02")  # 13 days
    _adr(proyecto["mem"], "ADR-002", date="2026-11-01")  # 14 days
    _adr(proyecto["mem"], "ADR-010", date="2026-11-01")  # same date, numeric tie-break
    _adr(proyecto["mem"], "ADR-001", date="2026-11-15")  # today

    salida = srv.get_context(project="demo")
    linea = next(l for l in salida.splitlines() if l.startswith("Proposed decisions awaiting"))

    assert linea == ("Proposed decisions awaiting the user's acceptance: ADR-004 (41 d), ADR-002 (14 d), "
                     "ADR-010 (14 d), ADR-003 (13 d), ADR-001 (today)")
    assert "Offer the user to decide the 3 oldest proposals: ADR-004, ADR-002, ADR-010" in salida


def test_get_context_no_age_suffix_for_invalid_date_and_no_old_proposal_notice(srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    _adr(proyecto["mem"], "ADR-001", date=None)
    _adr(proyecto["mem"], "ADR-002", date="2026-11-02")
    _adr(proyecto["mem"], "ADR-003", date="not-a-date")

    salida = srv.get_context(project="demo")
    linea = next(l for l in salida.splitlines() if l.startswith("Proposed decisions awaiting"))

    assert linea.endswith(": ADR-002 (13 d), ADR-001, ADR-003")
    assert "offer the user to decide" not in salida


def test_get_context_five_old_proposals_recommends_only_three_and_no_proposals_omits_line(
        srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    for n, day in enumerate(("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"), 1):
        _adr(proyecto["mem"], f"ADR-{n:03}", date=day)

    salida = srv.get_context(project="demo")

    assert "Offer the user to decide the 3 oldest proposals: ADR-001, ADR-002, ADR-003" in salida
    assert "ADR-004, ADR-005" not in next(l for l in salida.splitlines() if "Offer the user" in l)
    for path in (proyecto["mem"] / "decisions").glob("*.md"):
        path.unlink()
    assert not any(l.startswith("Proposed decisions awaiting") for l in srv.get_context(project="demo").splitlines())


def test_get_context_names_all_old_proposals_when_fewer_than_batch_limit(srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    _adr(proyecto["mem"], "ADR-001", date="2026-11-01")

    salida = srv.get_context(project="demo")

    assert "Offer the user to decide the oldest proposal: ADR-001" in salida


def test_get_context_uses_plural_for_two_old_proposals(srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    _adr(proyecto["mem"], "ADR-001", date="2026-10-31")
    _adr(proyecto["mem"], "ADR-002", date="2026-11-01")

    salida = srv.get_context(project="demo")

    assert "Offer the user to decide the 2 oldest proposals: ADR-001, ADR-002" in salida


def test_get_context_uses_plural_for_three_old_proposals(srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    for n in range(1, 4):
        _adr(proyecto["mem"], f"ADR-{n:03}", date=f"2026-10-{n:02}")

    salida = srv.get_context(project="demo")

    assert "Offer the user to decide the 3 oldest proposals: ADR-001, ADR-002, ADR-003" in salida


def test_get_context_future_proposal_has_no_age_or_old_proposal_notice(srv, proyecto, monkeypatch):
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(2026, 11, 15, 12))
    _adr(proyecto["mem"], "ADR-001", date="2026-11-18")

    salida = srv.get_context(project="demo")

    assert "Proposed decisions awaiting the user's acceptance: ADR-001" in salida
    assert "ADR-001 (-3 d)" not in salida
    assert "Offer the user to decide" not in salida


def test_create_task_warns_for_each_nonaccepted_decision_but_keeps_stored_format(srv, proyecto):
    _adr(proyecto["mem"], "ADR-001", status="accepted")
    _adr(proyecto["mem"], "ADR-002", status="proposed")
    _adr(proyecto["mem"], "ADR-003", status="rejected")
    _adr(proyecto["mem"], "ADR-004", status="superseded", extra="superseded_by: ADR-005\n")
    _adr(proyecto["mem"], "ADR-005", status="accepted")
    _adr(proyecto["mem"], "ADR-006", status="superseded")

    salida = srv.create_task(project="demo", title="Task", goal="g", acceptance_criteria="- c",
                             decisions="ADR-001, ADR-002, ADR-003, ADR-004, ADR-006")

    assert "ADR-002 is proposed" in salida and "reference, not as a rule" in salida
    assert "Accept it before starting" in salida and "clarify in the task notes" in salida
    assert "ADR-003 is rejected" in salida and "not applicable" in salida
    assert "ADR-004 is superseded by ADR-005" in salida
    assert "ADR-006 is superseded;" in salida
    task = next((proyecto["mem"] / "tasks").glob("T-*.md"))
    assert "## Applicable decisions\n\nADR-001, ADR-002, ADR-003, ADR-004, ADR-006\n" in task.read_text()


def test_create_task_all_accepted_has_no_warning_and_read_task_status_is_live(srv, proyecto):
    adr = _adr(proyecto["mem"], "ADR-001", status="proposed")
    created = srv.create_task(project="demo", title="Task", goal="g", acceptance_criteria="- c", decisions="ADR-1")
    assert "T-001 created" in created
    task = next((proyecto["mem"] / "tasks").glob("T-*.md"))
    original = task.read_bytes()
    assert "ADR-001 (proposed)" in srv.read_task(project="demo", id="T-001")

    srv.accept_decisions(project="demo", ids=["ADR-001"], user_quote="approved")
    committed = log_git(proyecto["mem"])
    brief = srv.read_task(project="demo", id="T-001")

    assert "ADR-001 (accepted)" in brief
    assert task.read_bytes() == original
    assert log_git(proyecto["mem"]) == committed

    without_decisions = srv.create_task(project="demo", title="No decisions", goal="g",
                                        acceptance_criteria="- c")
    with_accepted_decision = srv.create_task(project="demo", title="Accepted", goal="g",
                                             acceptance_criteria="- c", decisions="ADR-001")

    def normalize_task_response(response):
        response = re.sub(r"T-\d+", "T-ID", response)
        response = re.sub(r"t-\d+-[a-z0-9-]+", "task-branch", response)
        return re.sub(r"commit [0-9a-f]+", "commit HASH", response)

    assert normalize_task_response(with_accepted_decision) == normalize_task_response(without_decisions)


def test_read_task_marks_missing_decision_and_handles_absent_section(srv, proyecto):
    _adr(proyecto["mem"], "ADR-001")
    srv.create_task(project="demo", title="With decision", goal="g", acceptance_criteria="- c", decisions="ADR-1")
    (proyecto["mem"] / "decisions" / "ADR-001-decision.md").unlink()
    assert "ADR-001 (missing)" in srv.read_task(project="demo", id="T-001")

    srv.create_task(project="demo", title="No decisions", goal="g", acceptance_criteria="- c")
    assert "Applicable decisions" not in srv.read_task(project="demo", id="T-002")


def test_read_task_preserves_applicable_decisions_block_spacing(srv, proyecto):
    _adr(proyecto["mem"], "ADR-001", status="accepted")
    srv.create_task(project="demo", title="With decision", goal="g", acceptance_criteria="- c",
                    decisions="ADR-001")

    brief = srv.read_task(project="demo", id="T-001")

    assert "## Applicable decisions\n\nADR-001 (accepted)\n\n## How to verify" in brief


def test_read_task_preserves_applicable_decisions_with_free_text(srv, proyecto):
    _adr(proyecto["mem"], "ADR-001", status="accepted")
    srv.create_task(project="demo", title="With decision", goal="g", acceptance_criteria="- c",
                    decisions="ADR-001")
    task = next((proyecto["mem"] / "tasks").glob("T-*.md"))
    task.write_text(task.read_text().replace("ADR-001\n", "ADR-001, note for reviewer\n"), encoding="utf-8")

    brief = srv.read_task(project="demo", id="T-001")

    assert "## Applicable decisions\n\nADR-001, note for reviewer\n\n## How to verify" in brief
    assert "note for reviewer (missing)" not in brief


def test_read_task_marks_only_valid_missing_decision_ids(srv, proyecto):
    _adr(proyecto["mem"], "ADR-001", status="accepted")
    srv.create_task(project="demo", title="With decisions", goal="g", acceptance_criteria="- c",
                    decisions="ADR-001")
    task = next((proyecto["mem"] / "tasks").glob("T-*.md"))
    task.write_text(task.read_text().replace("ADR-001\n", "ADR-001, ADR-999\n"), encoding="utf-8")

    brief = srv.read_task(project="demo", id="T-001")

    assert "## Applicable decisions\n\nADR-001 (accepted), ADR-999 (missing)\n\n## How to verify" in brief
