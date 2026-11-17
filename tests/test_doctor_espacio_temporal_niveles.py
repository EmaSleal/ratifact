"""Doctor temporary-space section: two sensitivity levels, partial walks, default-location note."""
from __future__ import annotations

import pytest

from ratifact import doctor_espacio_temporal as temp_doctor

DUMPS = "Data dumps and env files"
KEYS = "Certificates and keys"


def _snapshot(root):
    return sorted((str(p.relative_to(root)), p.lstat().st_size, p.lstat().st_mtime_ns) for p in root.rglob("*"))


def _run(root, monkeypatch, **limits):
    monkeypatch.setenv("RATIFACT_CLAUDE_CODE_TEMP", str(root))
    for name, value in limits.items():
        monkeypatch.setattr(temp_doctor, name, value)
    before = _snapshot(root) if root.exists() else None
    actions: list[str] = []
    text = "\n".join(temp_doctor.seccion(actions))
    if before is not None:
        assert _snapshot(root) == before
    return text, actions


def test_only_informational_files_have_no_warning_or_action(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    (root / "venv").mkdir(parents=True)
    (root / "venv" / "cacert.pem").write_text("")
    (root / "venv" / "id.key").write_text("")
    text, actions = _run(root, monkeypatch)
    assert "⚠" not in text and actions == []
    assert str(root / "venv" / "cacert.pem") in text and str(root / "venv" / "id.key") in text
    assert f"{KEYS}: 2 total" in text and f"{DUMPS}: none" in text
    assert "not opened" in text and "only a hint" in text


def test_dump_and_certificate_land_in_their_levels(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    root.mkdir()
    (root / "a.sql").write_text("")
    (root / "b.pem").write_text("")
    text, actions = _run(root, monkeypatch)
    lines = text.splitlines()
    dumps = lines.index(f"  {DUMPS}: 1 total")
    keys = lines.index(f"  {KEYS}: 1 total")
    assert lines[dumps + 1].strip() == str(root / "a.sql")
    assert lines[keys + 1].strip() == str(root / "b.pem")
    assert any(l.startswith("  ⚠") and "not opened" in l for l in lines)
    assert len(actions) == 1 and "Counts by pattern" in text


def test_twenty_paths_shown_per_level(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    root.mkdir()
    for i in range(23):
        (root / f"{i:02}.sql").write_text("")
        (root / f"{i:02}.pem").write_text("")
    text, _ = _run(root, monkeypatch)
    lines = text.splitlines()
    assert sum(l.startswith("    /") and l.endswith(".sql") for l in lines) == 20
    assert sum(l.startswith("    /") and l.endswith(".pem") for l in lines) == 20
    assert lines.count("    … first 20 shown; 23 total") == 2


def test_info_only_hint_line_has_no_warning_marker(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    root.mkdir()
    (root / "x.key").write_text("")
    text, _ = _run(root, monkeypatch)
    hint = [l for l in text.splitlines() if "not opened" in l]
    assert hint and not any("⚠" in l for l in hint)


def test_partial_walk_shows_minimums_warning_and_single_action(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    (root / "proj").mkdir(parents=True)
    for i in range(5):
        (root / "proj" / f"{i}.txt").write_text("xxxx")
    text, actions = _run(root, monkeypatch, MAX_ENTRIES=3)
    assert "Total: at least " in text and "proj: at least " in text
    assert any(l.startswith("  ⚠") and "partial" in l.lower() and "threshold" in l for l in text.splitlines())
    assert len(actions) == 1 and str(root) in actions[0]
    assert text.count("Review Claude Code temporary folder") == 1


def test_partial_walk_plus_dump_adds_action_once(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    (root / "proj").mkdir(parents=True)
    (root / "a.sql").write_text("")
    for i in range(5):
        (root / "proj" / f"{i}.txt").write_text("x")
    text, actions = _run(root, monkeypatch, MAX_ENTRIES=4)
    assert "at least" in text and f"{DUMPS}: 1 total" in text
    assert len(actions) == 1 and text.count("Review Claude Code temporary folder") == 1


def test_complete_walk_has_no_minimums(tmp_path, monkeypatch):
    root = tmp_path / "claude"
    (root / "proj").mkdir(parents=True)
    (root / "proj" / "a.txt").write_text("xxxx")
    text, actions = _run(root, monkeypatch)
    assert "at least" not in text and "Total: 4 bytes" in text and "proj: 4 bytes" in text
    assert "partial" not in text.lower() and actions == []
    assert "checked on Linux" in text and "RATIFACT_CLAUDE_CODE_TEMP" in text


def test_missing_folder_mentions_environment_variable(tmp_path, monkeypatch):
    text, actions = _run(tmp_path / "missing", monkeypatch)
    assert "RATIFACT_CLAUDE_CODE_TEMP" in text and "not found" in text.lower() and actions == []
