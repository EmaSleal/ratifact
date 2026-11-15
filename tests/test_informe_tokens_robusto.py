"""The token section never makes `report` fail."""
from __future__ import annotations

from test_informe_tokens import CABECERA, _a, _activar, _ejecutar, _escribir, _informe, _l, _rama, claude  # noqa: F401


def test_linea_con_anidamiento_extremo_se_ignora(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 0, 60)
    rama, cwd = _rama(proyecto, "T-001"), proyecto["repo"]
    _escribir(claude / "s.jsonl", ["[" * 200000, _a(0, cwd, rama), _l(5, cwd, rama, sal=4)])
    _activar(entorno)
    assert "out 4 ·" in _informe(entorno, capsys)


def test_error_inesperado_no_rompe_report(srv, proyecto, entorno, claude, monkeypatch, capsys):
    from ratifact import informe_tokens
    _activar(entorno)

    def falla(*a, **k):
        raise KeyError("x")
    monkeypatch.setattr(informe_tokens, "seccion", falla)
    salida = _informe(entorno, capsys)
    assert CABECERA in salida and "  token usage unavailable: KeyError" in salida
