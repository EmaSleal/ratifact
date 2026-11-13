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


# --- Review 1: corrected-line proposal and re-evaluation on a Workers-line-only correction ---

def _propuesta(aviso):
    return [l for l in aviso.splitlines() if l.startswith("Workers:")][-1]


def test_aviso_propone_linea_completa_con_nota_existente():
    from ratifact.workers import aviso_in_review, parsear_workers
    aviso = aviso_in_review("required", f"Workers: {BASE} — note: foo")
    t = parsear_workers(_propuesta(aviso).replace("<why>", "already explored"))
    assert t.omitidos == ["explore"] and t.nota.startswith("foo") and "already explored" in t.nota


def test_aviso_propone_linea_completa_sin_nota():
    from ratifact.workers import aviso_in_review, parsear_workers
    linea = _propuesta(aviso_in_review("required", f"Workers: {BASE}"))
    assert linea == f"Workers: {BASE}, skipped: explore — note: <why>"
    assert parsear_workers(linea.replace("<why>", "x")).omitidos == ["explore"]


def _revision(srv, proyecto, texto):
    from test_workers_adr041 import _en_revision
    return _en_revision(srv, proyecto, texto)


def _bloques(ruta):
    import re
    return len(re.findall(r"^### \d{4}-\d{2}-\d{2} · \S+", ruta.read_text(), re.M))


def test_correccion_valida_sin_explore_vuelve_a_avisar(srv, proyecto):
    ruta = _revision(srv, proyecto, "Hecho.\nWorkers: write/sonnet×1 (x)\nIntegrations used: none")
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=f"Workers: {BASE}")
    assert "⚠" in salida and "no explore worker" in salida and "skipped: explore — note: <why>" in salida
    assert "replaced" in salida and _bloques(ruta) == 1 and f"Workers: {BASE}\n" in ruta.read_text()


def test_correccion_con_skipped_explore_no_avisa(srv, proyecto):
    ruta = _revision(srv, proyecto, "Hecho.\nWorkers: write/sonnet×1 (x)\nIntegrations used: none")
    salida = srv.update_task(project="demo", id="T-001", status="in_review",
                             result=f"Workers: {BASE}, skipped: explore — note: x")
    assert "⚠" not in salida and "replaced" in salida and _bloques(ruta) == 1


def test_correccion_invalida_avisa_linea_invalida(srv, proyecto):
    # an invalid line alone is kept as a new block (existing behaviour); the invalid-line warning is returned
    _revision(srv, proyecto, "Hecho.\nWorkers: write/sonnet×1 (x)")
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result="Workers: write/sonnet")
    assert "⚠" in salida and "is invalid" in salida
