"""`ratifact report`: delegation breakdown per build, explore omissions, rework not measured for non-delegated tasks,
and singular/plural of the counted nouns."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from test_delegacion import _en_curso, _tarea
from test_analizar_uso import _log_filas

BASE = "explore=haiku,write=sonnet,verify=sonnet · delegation=required"
HOY = dt.date.today().isoformat()
DESDE = lambda: dt.datetime.now() - dt.timedelta(days=7)     # noqa: E731


def _tarea_con(srv, mem: Path, id_: str, routing: str, resultado: str) -> None:
    from ratifact.registros import _escribir_registro, _leer_registro
    _en_curso(srv, id_)
    srv.update_task(project="demo", id=id_, status="in_review", result=resultado)
    archivo = _tarea(mem, id_)
    meta, cuerpo = _leer_registro(archivo)
    meta["routing"] = routing
    _escribir_registro(archivo, meta, cuerpo)


def _tres_builds(srv, mem):
    # build ...zzz is older (06:00) than ...aaa (09:00), although it sorts after it alphabetically
    _tarea_con(srv, mem, "T-001", f"{BASE} · build=1.0.0+aaaaaaa · at={HOY}T09:00-06:00 · client=claude-code/2",
               "Workers: write/sonnet×1, verify/sonnet×1, rework: write×1, skipped: explore — note: explored")
    _tarea_con(srv, mem, "T-002", f"{BASE} · build=1.0.0+aaaaaaa · at={HOY}T09:30-06:00 · client=claude-code/2",
               "Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1")
    _tarea_con(srv, mem, "T-003", f"{BASE} · build=1.0.0+zzzzzzz · at={HOY}T06:00-06:00",
               "Workers: write/sonnet×1, verify/sonnet×1, rework: write×1")
    _tarea_con(srv, mem, "T-004", f"{BASE} · at={HOY}T05:00-06:00 · client=codex/1", "Workers: none — reason: tiny")
    from ratifact.informe_delegacion import indicador_delegacion
    return indicador_delegacion(DESDE(), "demo")


def test_desglose_por_build_ordenado_por_at(srv, proyecto):
    lineas = _tres_builds(srv, proyecto["mem"])
    por_build = [l for l in lineas if l.startswith("    per build ")]
    assert por_build == [
        "    per build 1.0.0+zzzzzzz: 1 task · 1 delegated · rework —",
        "    per build 1.0.0+aaaaaaa: 2 tasks · 2 delegated · rework 50 %",
        "    per build no build: 1 task · 0 delegated · rework —",
    ], por_build


def test_omisiones_de_explore_y_grupo_no_delegado(srv, proyecto):
    lineas = _tres_builds(srv, proyecto["mem"])
    assert "    explore skipped 1 of 3 delegated" in lineas
    no_deleg = next(l for l in lineas if l.startswith("    not delegated:"))
    assert lineas[lineas.index(no_deleg) + 1] == "    not delegated: rework not measured (no verifier)"
    assert sum("rework not measured" in l for l in lineas) == 1


def test_salida_existente_sin_cambios(srv, proyecto):
    lineas = _tres_builds(srv, proyecto["mem"])
    assert lineas[0].startswith("  demo: 4 tasks with routing · required 4 · with workers 3 · compliance 75 %")
    assert any(l.startswith("    rework: with rework 2 of 3 delegated · rate 67 %") for l in lineas)
    assert any(l.startswith("    per client claude-code/2: 2 tasks") for l in lineas)


def test_plurales_en_el_indicador_con_una_tarea(srv, proyecto):
    _tarea_con(srv, proyecto["mem"], "T-001", f"{BASE} · build=1.0.0+aaaaaaa · at={HOY}T09:00-06:00 · client=x/1",
               "Workers: write/sonnet×1, verify/sonnet×1")
    from ratifact.informe_delegacion import indicador_delegacion
    texto = "\n".join(indicador_delegacion(DESDE(), "demo"))
    assert "1 task with routing" in texto and "1 task ·" in texto
    for malo in ("1 tasks", "1 calls", "1 days", "1 items"):
        assert malo not in texto


def test_helper_contar():
    from ratifact.plurales import contar
    assert contar(1, "call") == "1 call" and contar(0, "call") == "0 calls" and contar(2, "task") == "2 tasks"
    assert contar(1, "elapsed day") == "1 elapsed day" and contar(3, "use") == "3 uses"
    assert contar(2, "entry", "entries") == "2 entries"


def _salida_report(entorno, capsys, filas, dias=14):
    from ratifact import cli
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)
    cli.main(["report", "--log", str(log), "--days", str(dias)])
    return capsys.readouterr().out


def test_report_singular_con_una_llamada_un_dia(srv, proyecto, entorno, capsys):
    ahora = dt.datetime.now().isoformat(timespec="seconds")
    filas = [{"herramienta": "create_task", "resp_chars": 10, "error": False, "ts": ahora}]
    _tarea_con(srv, proyecto["mem"], "T-001", f"{BASE} · build=1.0.0+aaaaaaa · at={HOY}T09:00-06:00 · client=x/1",
               "Workers: write/sonnet×1, verify/sonnet×1")
    salida = _salida_report(entorno, capsys, filas)
    assert "last 14 days · 1 call\n" in salida and "Idempotent creations: 1 call " in salida
    assert "1 day with use" in salida
    for malo in ("1 calls", "1 tasks", "1 days", "1 items", "1 uses"):
        assert malo not in salida, malo


def test_report_plural_con_dos(srv, proyecto, entorno, capsys):
    t0 = dt.datetime.now() - dt.timedelta(days=1)
    filas = [{"herramienta": "create_task", "resp_chars": 10, "error": False, "ts": t.isoformat(timespec="seconds")}
             for t in (t0, dt.datetime.now())]
    _tarea_con(srv, proyecto["mem"], "T-001", f"{BASE} · build=1.0.0+aaaaaaa · at={HOY}T09:00-06:00 · client=x/1",
               "Workers: write/sonnet×1, verify/sonnet×1")
    _tarea_con(srv, proyecto["mem"], "T-002", f"{BASE} · build=1.0.0+aaaaaaa · at={HOY}T09:30-06:00 · client=x/1",
               "Workers: write/sonnet×1, verify/sonnet×1")
    salida = _salida_report(entorno, capsys, filas)
    assert "last 14 days · 2 calls\n" in salida and "Idempotent creations: 2 calls " in salida
    assert "2 days with use" in salida and "2 tasks with routing" in salida
