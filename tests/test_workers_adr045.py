"""T-023 (ADR-045, ADR-046): omisión declarada de explore (`skipped: explore`), verificación de respaldo y aviso blando
de in_review."""
from __future__ import annotations

import pytest

from test_delegacion import _en_curso, _meta  # noqa: F401

BASE = "write/sonnet×1, verify/sonnet×1"


def test_skipped_explore_valido():
    from ratifact.workers import parsear_workers
    t = parsear_workers(f"Workers: {BASE}, skipped: explore — note: already explored while planning")
    assert t.omitidos == ["explore"] and t.nota == "already explored while planning"
    assert t.roles == [("write", "sonnet", 1), ("verify", "sonnet", 1)]


def test_skipped_explore_con_rework_y_separador_ascii():
    from ratifact.workers import parsear_workers
    t = parsear_workers(f"Workers: {BASE}, rework: write×1, skipped: explore — note: x")
    assert t.omitidos == ["explore"] and t.reenvios == {"write": 1}
    assert parsear_workers(f"Workers: {BASE}, skipped: explore -- note: x").omitidos == ["explore"]


def test_sin_skipped_el_campo_esta_vacio():
    from ratifact.workers import Trabajadores, parsear_workers
    assert Trabajadores().omitidos == []
    assert parsear_workers(f"Workers: explore/haiku×1, {BASE}").omitidos == []


@pytest.mark.parametrize("linea,causa", [
    (f"Workers: {BASE}, skipped: explore", "note"),
    (f"Workers: {BASE}, skipped: explore — note:", "note"),
    (f"Workers: explore/haiku×1, {BASE}, skipped: explore — note: x", "explore worker"),
    (f"Workers: {BASE}, skipped: write — note: x", "only explore"),
    (f"Workers: write/sonnet×1, skipped: verify — note: x", "only explore"),
])
def test_skipped_invalido(linea, causa):
    from ratifact.workers import parsear_workers
    with pytest.raises(ValueError, match=causa):
        parsear_workers(linea)


def test_bloque_required_menciona_skipped_y_verify_de_respaldo(srv, proyecto):
    salida = _en_curso(srv)
    bloque = salida[salida.index("Delegation (required"):]
    assert "`skipped: explore`" in bloque and "— note:" in bloque
    assert "already explored" in bloque
    assert "not available" in bloque and "other than the writer's" in bloque
    assert "never skipped" in bloque
    assert "Workers: <role>/<model>×<n>, …" in bloque


def test_bloques_suggested_y_off_sin_cambios(srv, proyecto):
    srv.update_project(name="demo", delegation="suggested")
    assert "skipped" not in _en_curso(srv)
    srv.update_project(name="demo", delegation="off")
    assert "skipped" not in _en_curso(srv, "T-002")


def _a_revision(srv, resultado):
    _en_curso(srv)
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=resultado)
    assert "T-001 → in_review" in salida
    return salida


def test_aviso_sin_explore_ni_skipped(srv, proyecto):
    salida = _a_revision(srv, f"hecho\nWorkers: {BASE}")
    assert "skipped: explore — note: <why>" in salida
    assert _meta(proyecto["mem"])["status"] == "in_review"


@pytest.mark.parametrize("linea", [f"Workers: explore/haiku×1, {BASE}",
                                   f"Workers: {BASE}, skipped: explore — note: planned it"])
def test_sin_aviso_con_explore_o_skipped(srv, proyecto, linea):
    salida = _a_revision(srv, f"hecho\n{linea}")
    assert "skipped" not in salida and "⚠" not in salida
    assert _meta(proyecto["mem"])["status"] == "in_review"


def test_sin_aviso_si_politica_no_required(srv, proyecto):
    srv.update_project(name="demo", delegation="suggested")
    srv.create_task(project="demo", title="x", goal="o", acceptance_criteria="c")
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=f"Workers: {BASE}")
    assert "skipped" not in salida
