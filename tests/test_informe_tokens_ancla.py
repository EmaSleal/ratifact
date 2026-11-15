"""Token attribution by time anchor: candidates by `cwd`, activity near the transitions, ambiguity, median and
long-window warning."""
from __future__ import annotations

import datetime as dt

from test_informe_tokens import (NADA, _a, _activar, _en, _ejecutar, _escribir, _l, _rama, _seccion,  # noqa: F401
                                 claude)

SEG = 1 / 60


def _t(srv, monkeypatch, ini=10, fin=60, **kw):
    _ejecutar(srv, monkeypatch, "T-001", ini, fin, **kw)


def test_sesion_con_rama_head_se_atribuye(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, cwd, "HEAD"), _l(20, cwd, "HEAD", sal=5)])
    _activar(entorno)
    assert "out 5 ·" in _seccion(entorno, capsys)


def test_sesion_de_worktree_con_rama_base_se_atribuye(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, cwd, "prod"), _l(20, cwd, "prod", sal=6), _l(30, cwd, "prod", mid="m2", sal=1)])
    _activar(entorno)
    assert "out 7 ·" in _seccion(entorno, capsys)


def test_multirepo_cwd_en_la_raiz_y_luego_en_repo(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    raiz = proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, raiz, "main"), _l(20, raiz / "servicio", "main", sal=8)])
    _activar(entorno)
    assert "out 8 ·" in _seccion(entorno, capsys)


def test_cwd_fuera_del_proyecto_no_se_atribuye(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    otro = entorno["tmp"] / "otro"
    _escribir(claude / "s.jsonl", [_a(10, otro, _rama(proyecto, "T-001")), _l(20, otro, _rama(proyecto, "T-001"))])
    _activar(entorno)
    assert "T-001 · delegation=required: no data" in _seccion(entorno, capsys)


def test_tolerancia_de_ancla(srv, proyecto, entorno, claude, monkeypatch, capsys):
    from ratifact.informe_tokens_atribucion import TOLERANCIA
    assert TOLERANCIA == dt.timedelta(seconds=120)
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "cerca.jsonl", [_a(10 - 119 * SEG, cwd), _l(20, cwd, "x", mid="a", sal=1)])
    _escribir(claude / "lejos.jsonl", [_a(10 - 121 * SEG, cwd), _a(60 + 121 * SEG, cwd), _l(20, cwd, "x", mid="b", sal=100)])
    _activar(entorno)
    assert "out 1 ·" in _seccion(entorno, capsys)


def test_ancla_solo_al_final(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "s.jsonl", [_l(30, cwd, "x", sal=9), _a(60 + 60 * SEG, cwd)])
    _activar(entorno)
    assert "out 9 ·" in _seccion(entorno, capsys)


def test_varias_ancladas_gana_la_de_la_rama(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd, rama = proyecto["repo"], _rama(proyecto, "T-001")
    _escribir(claude / "a.jsonl", [_a(10, cwd), _l(20, cwd, "main", mid="a", sal=1)])
    _escribir(claude / "b.jsonl", [_a(10, cwd), _l(20, cwd, rama, mid="b", sal=10)])
    _escribir(claude / "c.jsonl", [_a(11, cwd), _l(20, cwd, "main", mid="c", sal=100)])
    _activar(entorno)
    assert "out 10 ·" in _seccion(entorno, capsys)


def test_varias_ancladas_sin_rama_es_ambigua(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "a.jsonl", [_a(10, cwd), _l(20, cwd, "main", mid="a", sal=1)])
    _escribir(claude / "b.jsonl", [_a(10, cwd), _l(20, cwd, "main", mid="b", sal=10)])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    assert "    T-001 · delegation=required: ambiguous (2 sessions active at the transition)\n" in s
    assert "    delegated: —\n    not delegated: —\n" in s


def test_ancla_inicio_en_una_y_fin_en_otra_es_ambigua(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "a.jsonl", [_a(10, cwd), _l(20, cwd, "main", mid="a", sal=1)])
    _escribir(claude / "b.jsonl", [_a(60, cwd), _l(30, cwd, "main", mid="b", sal=10)])
    _activar(entorno)
    assert "ambiguous (2 sessions active at the transition)" in _seccion(entorno, capsys)


def test_una_sola_sesion_ambigua_en_singular(srv, proyecto, entorno, claude, monkeypatch, capsys):
    """An ambiguous task is not counted in the summary denominator."""
    _t(srv, monkeypatch)
    _ejecutar(srv, monkeypatch, "T-002", 200, 210)
    cwd = proyecto["repo"]
    _escribir(claude / "a.jsonl", [_a(10, cwd), _l(20, cwd, "main", mid="a", sal=1)])
    _escribir(claude / "b.jsonl", [_a(10, cwd), _a(200, cwd), _l(205, cwd, "main", mid="b", sal=10)])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    assert "T-001 · delegation=required: ambiguous (2 sessions" in s
    assert "T-002 · delegation=required\n" in s and "delegated: 1 of 1 task with data" in s


def test_subagentes_siguen_a_su_sesion(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd = proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, cwd)])
    _escribir(claude / "s" / "subagents" / "agent-q.jsonl", [_l(30, cwd, "x", mid="w", rid="q", sal=4, lado=True, agente="q")])
    _activar(entorno)
    assert "workers: 1 worker — claude-opus: in 1 · out 4" in _seccion(entorno, capsys)


def test_sesion_con_la_rama_sin_ancla_no_aporta(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _t(srv, monkeypatch)
    cwd, rama = proyecto["repo"], _rama(proyecto, "T-001")
    _escribir(claude / "a.jsonl", [_a(10, cwd), _l(20, cwd, "main", mid="a", sal=1)])
    _escribir(claude / "b.jsonl", [_a(30, cwd, rama), _l(31, cwd, rama, mid="b", sal=1000)])    # no activity at an anchor
    _activar(entorno)
    assert "out 1 ·" in _seccion(entorno, capsys)


def test_misma_sesion_dos_tareas_seguidas_sin_cambiar_de_rama(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _ejecutar(srv, monkeypatch, "T-001", 10, 20)
    _ejecutar(srv, monkeypatch, "T-002", 20.5, 40)
    cwd = proyecto["repo"]
    _escribir(claude / "s.jsonl", [_a(10, cwd), _a(20.5, cwd), _l(15, cwd, "prod", mid="1", sal=1),
                                   _l(30, cwd, "prod", mid="2", sal=100), _l(19.9, cwd, "prod", mid="3", sal=10)])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    t1, t2 = s.split("    T-002")
    assert "out 11 ·" in t1 and "out 100 ·" in t2, s


def _datos(srv, proyecto, claude, monkeypatch, salidas, delegada=True):
    cwd = proyecto["repo"]
    for n, sal in enumerate(salidas):
        id_ = f"T-{n + 1:03d}"
        _ejecutar(srv, monkeypatch, id_, 100 * n + 10, 100 * n + 20, resultado="Workers: write/sonnet×1" if delegada else NADA)
        _escribir(claude / f"s{n}.jsonl", [_a(100 * n + 10, cwd), _l(100 * n + 15, cwd, "x", mid=f"m{n}", sal=sal, cr=sal * 10),
                                           _l(100 * n + 16, cwd, "x", mid=f"w{n}", rid=f"q{n}", sal=sal * 2, lado=True, agente="a")])


def test_mediana_con_cantidad_impar_y_par(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _datos(srv, proyecto, claude, monkeypatch, [1, 2, 9])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    assert ("    delegated: 3 of 3 tasks with data · average per task — main session: out 4 · cache read 40; "
            "workers: out 8 · cache read 0\n      median per task — main session: out 2 · cache read 20; "
            "workers: out 4 · cache read 0\n") in s


def test_mediana_par(srv, proyecto, entorno, claude, monkeypatch, capsys):
    _datos(srv, proyecto, claude, monkeypatch, [2, 4, 10, 20])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    assert "average per task — main session: out 9 · cache read 90; workers: out 18 · cache read 0\n" in s
    assert "      median per task — main session: out 7 · cache read 70; workers: out 14 · cache read 0\n" in s


def test_aviso_de_ventana_larga_en_el_limite(srv, proyecto, entorno, claude, monkeypatch, capsys):
    cwd = proyecto["repo"]
    _ejecutar(srv, monkeypatch, "T-001", 0, 480)                  # exactly 8 h
    _ejecutar(srv, monkeypatch, "T-002", 1000, 1000 + 481)        # 8 h 1 min
    _escribir(claude / "s.jsonl", [_a(0, cwd), _l(5, cwd, "x", mid="a", sal=1), _a(1000, cwd), _l(1005, cwd, "x", mid="b", sal=2)])
    _activar(entorno)
    s = _seccion(entorno, capsys)
    t1, t2 = s.split("    T-002")
    assert "⚠" not in t1
    assert "long window (8 h): may include other work of the same session\n" in t2
    assert "delegated: 2 of 2 tasks with data" in s            # shown and counted
