"""T-028: temporary-space hygiene, result warnings, and public guidance."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def demo_task(srv, proyecto):
    srv.create_task(project="demo", title="Temporary path warning", goal="Warn", acceptance_criteria="Covered")
    return proyecto


@pytest.mark.parametrize("path", [
    "/tmp/session/evidence.txt", "/var/tmp/session/evidence.txt", "/private/tmp/session/evidence.txt",
    "workspace/scratchpad/evidence.txt", "scratchpad/evidence.txt",
])
@pytest.mark.parametrize("status", ["in_review", "failed"])
def test_update_task_warns_for_temporary_paths_and_keeps_result(srv, demo_task, status, path):
    from ratifact.registros import _leer_registro

    result = f"Evidence: {path}\nWorkers: none — reason: checks complete"
    output = srv.update_task(project="demo", id="T-001", status=status, result=result)
    assert path in output
    assert "self-contained" in output
    record = next((demo_task["mem"] / "tasks").glob("T-001*"))
    _, body = _leer_registro(record)
    assert result in body


@pytest.mark.parametrize("status", ["todo", "in_progress", "merged", "discarded"])
def test_update_task_does_not_warn_for_temp_path_on_other_states(srv, demo_task, status):
    output = srv.update_task(project="demo", id="T-001", status=status, result="See /tmp/session/file")
    assert "self-contained" not in output


@pytest.mark.parametrize("result", ["", "scratchpad is useful", "tmp is a temporary directory"])
def test_update_task_ignores_empty_result_and_bare_words(srv, demo_task, result):
    output = srv.update_task(project="demo", id="T-001", status="failed", result=result)
    assert "self-contained" not in output


def test_update_task_reports_only_the_first_temporary_path(srv, demo_task):
    output = srv.update_task(
        project="demo", id="T-001", status="failed",
        result="Evidence: /tmp/first/file.txt and /var/tmp/second/file.txt",
    )
    assert "/tmp/first/file.txt" in output and "/var/tmp/second/file.txt" not in output


def test_update_task_workers_only_correction_has_no_temp_warning(srv, demo_task):
    from test_workers_adr041 import WORKERS_OK

    srv.update_task(project="demo", id="T-001", status="in_review", result="First review")
    output = srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    assert "self-contained" not in output


def test_update_task_workers_only_correction_with_temp_path_in_note_has_no_temp_warning(srv, demo_task):
    srv.update_task(project="demo", id="T-001", status="in_review", result="First review")
    output = srv.update_task(project="demo", id="T-001", status="in_review",
                             result="Workers: write/sonnet×1 — note: see /tmp/x")
    assert "Workers line" in output and "self-contained" not in output


def test_update_task_temp_warning_coexists_with_workers_and_stale_server_warnings(
        srv, demo_task, monkeypatch):
    from ratifact import build

    monkeypatch.setattr(build, "obsoleto", lambda: True)
    output = srv.update_task(
        project="demo", id="T-001", status="in_review",
        result="Evidence /tmp/session/file\nWorkers: invalid",
    )
    lines = output.splitlines()
    assert any(l.startswith("⚠ The result references temporary path /tmp/session/file;") for l in lines)
    assert any(l.startswith("⚠") and "Workers" in l and "invalid" in l for l in lines)
    assert any("restart" in l.lower() or "out of date" in l.lower() for l in lines), output


def test_doctor_temporary_section_reports_missing_path_without_error(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal

    missing = tmp_path / "missing"
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(missing))
    lines = doctor_espacio_temporal.seccion()
    assert sum("not found" in line.lower() for line in lines) == 1


def test_doctor_temporary_section_sizes_projects_and_warns_above_threshold(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    (root / "small").mkdir(parents=True)
    (root / "large" / "nested").mkdir(parents=True)
    (root / "small" / "a.txt").write_bytes(b"a" * 4)
    (root / "large" / "nested" / "b.txt").write_bytes(b"b" * 7)
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    monkeypatch.setattr(temp_doctor, "SIZE_WARNING_BYTES", 10)
    lines = temp_doctor.seccion()
    text = "\n".join(lines)
    assert "Total: 11 bytes" in text
    assert text.index("large: 7 bytes") < text.index("small: 4 bytes")
    assert "⚠" in text and str(root) in text and "you decide" in text
    monkeypatch.setattr(temp_doctor, "SIZE_WARNING_BYTES", 12)
    assert "⚠" not in "\n".join(temp_doctor.seccion())
    monkeypatch.setattr(temp_doctor, "SIZE_WARNING_BYTES", 10)
    assert "⚠" in "\n".join(temp_doctor.seccion())


@pytest.mark.parametrize("name", ["db.sql", "db.sql.gz", "backup.dump", ".env", ".env.local", "id.pem", "id.key"])
def test_doctor_lists_sensitive_names_without_opening(tmp_path, monkeypatch, name):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    project = root / "project" / "session"
    project.mkdir(parents=True)
    candidate = project / name
    candidate.write_bytes(b"not inspected")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    lines = temp_doctor.seccion()
    assert str(candidate) in "\n".join(lines)
    assert "⚠" in "\n".join(lines)


def test_doctor_ignores_nonmatching_filename(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    root.mkdir()
    (root / "database.txt").write_text("safe name")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    text = "\n".join(temp_doctor.seccion())
    assert "Sensitive-looking files: none" in text and "database.txt" not in text
    assert "Counts by pattern: .dump=0, .env=0, .key=0, .pem=0, .sql=0, .sql.gz=0" in text


def test_doctor_caps_sensitive_listing_at_twenty_and_reports_total(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    root.mkdir()
    for index in range(23):
        (root / f"{index:02}.sql").write_text("")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    lines = temp_doctor.seccion()
    listed = [line for line in lines if line.startswith("    /") and ".sql" in line]
    text = "\n".join(lines)
    assert len(listed) == 20 and "23 total" in text


def test_doctor_entry_limit_marks_partial_without_pending_action(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    root.mkdir()
    for index in range(5):
        (root / f"{index}.txt").write_text("x")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    monkeypatch.setattr(temp_doctor, "MAX_ENTRIES", 2)
    actions: list[str] = []
    text = "\n".join(temp_doctor.seccion(actions))
    assert "partial" in text.lower() and "entry" in text.lower()
    assert actions == [] and "⚠" not in text


def test_doctor_reports_permission_errors_without_failing(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    blocked = root / "restricted"
    blocked.mkdir(parents=True)
    original_scandir = temp_doctor.os.scandir

    def scandir(path):
        if Path(path) == blocked:
            raise PermissionError("denied")
        return original_scandir(path)

    monkeypatch.setattr(temp_doctor.os, "scandir", scandir)
    actions: list[str] = []
    text = "\n".join(temp_doctor.seccion(actions, raiz=root))
    assert "Permission errors: 1" in text and actions == []


def test_doctor_adds_section_and_pending_action(tmp_path, monkeypatch, srv):
    from ratifact import doctor

    root = tmp_path / "claude"
    project = root / "demo"
    project.mkdir(parents=True)
    (project / "backup.sql").write_text("")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    lines, actions = doctor.informe(procesos=lambda: [], vivos=lambda: [])
    text = "\n".join(lines)
    assert "Claude Code temporary space" in text and "other clients are not inspected" in text
    assert str(root) in text and any(str(root) in action for action in actions)


def test_doctor_keeps_temporary_section_on_configuration_error(tmp_path, monkeypatch, srv):
    from ratifact import doctor

    root = tmp_path / "claude"
    root.mkdir()
    (root / "backup.dump").write_text("")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))

    def fail_plan(**_kwargs):
        raise doctor._cfg.ErrorMemoria("configuration unavailable")

    monkeypatch.setattr(doctor, "planificar", fail_plan)
    lines, actions = doctor.informe(procesos=lambda: [], vivos=lambda: [])
    assert any("Claude Code temporary space" in line for line in lines)
    assert any(str(root) in action for action in actions)


def test_doctor_does_not_follow_symlinks_or_change_tree(tmp_path, monkeypatch):
    from ratifact import doctor_espacio_temporal as temp_doctor

    root = tmp_path / "claude"
    project = root / "project"
    project.mkdir(parents=True)
    secret = tmp_path / "outside.sql"
    secret.write_text("outside")
    link = project / "linked.sql"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    before = sorted((str(path.relative_to(root)), path.is_symlink(), path.stat(follow_symlinks=False).st_size)
                    for path in root.rglob("*"))
    text = "\n".join(temp_doctor.seccion())
    after = sorted((str(path.relative_to(root)), path.is_symlink(), path.stat(follow_symlinks=False).st_size)
                   for path in root.rglob("*"))
    assert str(link) not in text and before == after


def test_skill_docs_and_readme_document_temporary_hygiene():
    root = Path(__file__).resolve().parents[1]
    skill = root / "ratifact/skills/run-task/SKILL.md"
    root_skill = root / "run-task.md"
    text = skill.read_text(encoding="utf-8")
    assert root_skill.resolve() == skill.resolve()
    for term in ("git archive <branch> | tar -x -C <dir>", "production data", "in_review", "self-contained"):
        assert term in text
    readme = (root / "README.md").read_text(encoding="utf-8")
    leeme = (root / "LEEME.md").read_text(encoding="utf-8")
    assert "RATIFACT_CLAUDE_CODE_TEMP" in readme and "RATIFACT_CLAUDE_CODE_TEMP" in leeme
    assert "git archive" in readme and "production data" in readme and "self-contained" in readme
    assert "git archive" in leeme and "datos de producción" in leeme and "autocontenida" in leeme



def test_doctor_whole_command_leaves_temp_tree_identical(tmp_path, monkeypatch, capsys):
    from ratifact import doctor

    root = tmp_path / "claude"
    (root / "demo" / "session").mkdir(parents=True)
    (root / "demo" / "session" / "dump.sql").write_text("select 1")
    (root / "demo" / "notes.txt").write_text("hello")

    def snapshot():
        return sorted((str(p.relative_to(root)), p.lstat().st_size, p.lstat().st_mtime_ns)
                      for p in root.rglob("*"))

    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    before = snapshot()
    doctor.main(procesos=lambda: [], log_viejo=tmp_path / "no-log")
    out = capsys.readouterr().out
    assert "Claude Code temporary space" in out and str(root / "demo" / "session" / "dump.sql") in out
    assert snapshot() == before


@pytest.mark.parametrize("text,expected", [
    ("see /tmp/a/b.txt.", "/tmp/a/b.txt"), ("(/var/tmp/x)", "/var/tmp/x"), ("x scratchpad/y", "scratchpad/y"),
    ("scratchpad is a word", ""), ("", ""), ("a /private/tmp/q and /tmp/z", "/private/tmp/q"),
])
def test_primera_ruta_temporal(text, expected):
    from ratifact.rutas_temporales import primera_ruta_temporal

    assert primera_ruta_temporal(text) == expected
