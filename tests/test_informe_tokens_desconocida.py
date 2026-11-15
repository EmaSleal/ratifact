"""Token usage averages: a task without a valid `Workers:` line is listed but excluded from both averages."""
from __future__ import annotations

from test_informe_tokens import (NADA, _a, _activar, _en, _ejecutar, _escribir, _l, _rama, _seccion, claude)  # noqa: F401


def test_tarea_sin_workers_valido_no_entra_en_promedios(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 10, 20)
    _ejecutar(srv, monkeypatch, "T-002", 30, 40, resultado=NADA)
    srv.create_task(project="demo", title="En curso", goal="o", acceptance_criteria="c")
    monkeypatch.setenv("GIT_COMMITTER_DATE", _en(50).isoformat())
    assert srv.update_task(project="demo", id="T-003", status="in_progress").startswith("T-003 → in_progress")
    cwd = proyecto["repo"]
    for n, (id_, minu, sal) in enumerate((("T-001", 15, 10), ("T-002", 35, 20), ("T-003", 55, 9999))):
        _escribir(claude / f"s{n}.jsonl", [_a(minu - 5, cwd), _l(minu, cwd, _rama(proyecto, id_), mid=f"a{n}", sal=sal)])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    # the open window runs up to now, so it also carries the long-window warning
    assert "    T-003 · delegation=required ⚠ long window (" in s
    assert "h): may include other work of the same session\n      main session: claude-opus: in 1 · out 9,999" in s
    assert "    delegated: 1 of 1 task with data · average per task — main session: out 10 " in s
    assert "    not delegated: 1 of 1 task with data · average per task — main session: out 20 " in s
