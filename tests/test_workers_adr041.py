"""T-018 (ADR-041): rework y note en la línea Workers, corrección sin duplicar, propuesta del aviso, cliente MCP en
routing y uso.jsonl, y retrabajo/desglose por cliente en `ratifact report`."""
from __future__ import annotations

import datetime as dt
import json
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_delegacion import WORKERS_OK, _en_curso, _meta, _tarea

BLOQUE = re.compile(r"^### \d{4}-\d\d-\d\d · ", re.M)


@contextmanager
def cliente(nombre=None, version="1.0", info=True):
    """Fija el contextvar real del SDK que lee `cliente_actual` (sesión con clientInfo simulado)."""
    from mcp.server.lowlevel.server import request_ctx
    params = SimpleNamespace(clientInfo=SimpleNamespace(name=nombre, version=version)) if info else None
    token = request_ctx.set(SimpleNamespace(session=SimpleNamespace(client_params=params)))
    try:
        yield
    finally:
        request_ctx.reset(token)


def _filas(entorno) -> list[dict]:
    return [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]


# ───────────────────────── criterios 1-3: parser ─────────────────────────

@pytest.mark.parametrize("linea,roles,reenvios,escalados,nota", [
    ("Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1", 3, {}, [], ""),
    ("Workers: write/sonnet×1, verify/sonnet×1, rework: write×1", 2, {"write": 1}, [], ""),
    ("Workers: write/sonnet×1, verify/sonnet×1, rework: write×2, verify×1", 2, {"write": 2, "verify": 1}, [], ""),
    ("Workers: write/sonnet×1, escalated: write", 1, {}, ["write"], ""),
    ("Workers: write/sonnet×1, rework: write×1, escalated: write", 1, {"write": 1}, ["write"], ""),
    ("Workers: escalated: write, write/sonnet×1", 1, {}, ["write"], ""),            # ADR-036: cualquier orden
    ("Workers: write/sonnet×1, escalated: write, explore/haiku×1", 2, {}, ["write"], ""),
    ("Workers: rework: write×1, write/sonnet×1, escalated: write", 1, {"write": 1}, ["write"], ""),
    ("Workers: write/sonnet×1 — note: resumed once", 1, {}, [], "resumed once"),
    ("Workers: write/sonnet×1, rework: write×1 — note: verify fix (batch 2)", 1, {"write": 1}, [], "verify fix (batch 2)"),
    ("Workers: write/sonnet×1 — cualquier cosa (libre), sin validar", 1, {}, [], "cualquier cosa (libre), sin validar"),
])
def test_parser_acepta_rework_escalated_y_nota(linea, roles, reenvios, escalados, nota):
    from ratifact.delegacion import parsear_workers
    t = parsear_workers(linea)
    assert len(t.roles) == roles and t.reenvios == reenvios and t.escalados == escalados and t.nota == nota


def test_parser_none_sigue_igual():
    from ratifact.delegacion import parsear_workers
    t = parsear_workers("Workers: none — reason: tarea de una línea")
    assert t.motivo == "tarea de una línea" and t.total == 0 and t.reenvios == {} and t.nota == ""


@pytest.mark.parametrize("linea", [
    "Workers: write/sonnet×1 (resumed once)",                                   # paréntesis fuera de la nota
    "Workers: write/sonnet×1, rework: verify×1",                                # rol que no es trabajador
    "Workers: write/sonnet×1, rework: write×0",
    "Workers: write/sonnet×1, write×1",                                         # reenvío fuera de la lista rework
    "Workers: write/sonnet×1, rework: write×1, verify/sonnet×1, write×1",       # continuación tras un trabajador
    "Workers: none", "Workers: none — note: x", "Workers: none — reason:",
    "Workers: write/sonnet×1, extra",                                           # token desconocido
    "Workers: rework: write×1 — note: sin trabajadores",
    "Workers: — note: nada",
])
def test_parser_rechaza(linea):
    from ratifact.delegacion import parsear_workers
    with pytest.raises(ValueError):
        parsear_workers(linea)


# ───────────────────────── criterio 4-5: corrección sin duplicar ─────────────────────────

def _en_revision(srv, proyecto, resultado, id_="T-001"):
    _en_curso(srv, id_)
    srv.update_task(project="demo", id=id_, status="in_review", result=resultado)
    return _tarea(proyecto["mem"], id_)


def test_correccion_reemplaza_linea_invalida_sin_bloque_nuevo(srv, proyecto):
    ruta = _en_revision(srv, proyecto, "Hecho.\nWorkers: write/sonnet×1 (resumed once)\nIntegrations used: none")
    assert len(BLOQUE.findall(ruta.read_text())) == 1
    salida = srv.update_task(project="demo", id="T-001", status="in_review",
                             result="  Workers: write/sonnet×1, rework: write×1 — note: resumed once  \n")
    texto = ruta.read_text()
    assert re.fullmatch(r"T-001 → in_review · Workers line replaced in the latest result block · commit \S+", salida)
    assert len(BLOQUE.findall(texto)) == 1
    assert "(resumed once)" not in texto and texto.count("Workers:") == 1
    assert "Workers: write/sonnet×1, rework: write×1 — note: resumed once\nIntegrations used: none" in texto
    assert _meta(proyecto["mem"])["status"] == "in_review"


def test_correccion_agrega_si_el_bloque_no_tenia_linea(srv, proyecto):
    ruta = _en_revision(srv, proyecto, "Hecho sin línea.")
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    texto = ruta.read_text()
    assert "added to the latest result block" in salida and "⚠" not in salida
    assert len(BLOQUE.findall(texto)) == 1 and texto.count(WORKERS_OK) == 1
    assert texto.index("Hecho sin línea.") < texto.index(WORKERS_OK)


def test_resultado_completo_nuevo_sigue_creando_bloque(srv, proyecto):
    ruta = _en_revision(srv, proyecto, "Workers: write/sonnet×1 (x)")
    srv.update_task(project="demo", id="T-001", status="in_review", result=f"Más trabajo.\n{WORKERS_OK}")
    assert len(BLOQUE.findall(ruta.read_text())) == 2


def test_linea_invalida_sola_tambien_crea_bloque(srv, proyecto):
    ruta = _en_revision(srv, proyecto, WORKERS_OK)
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result="Workers: write/sonnet")
    assert len(BLOQUE.findall(ruta.read_text())) == 2 and "replaced" not in salida and "⚠" in salida


def test_linea_sola_fuera_de_in_review_no_reemplaza(srv, proyecto):
    _en_curso(srv)
    srv.update_task(project="demo", id="T-001", status="in_review", result="Hecho")
    srv.request_changes(project="demo", id="T-001", findings="f")
    ruta = _tarea(proyecto["mem"])
    srv.update_task(project="demo", id="T-001", status="in_progress")
    srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    assert len(BLOQUE.findall(ruta.read_text())) == 2     # no estaba en in_review: bloque nuevo, sin reemplazo


def test_correccion_con_review_posterior_cae_al_comportamiento_normal(srv, proyecto):
    _en_curso(srv)
    srv.update_task(project="demo", id="T-001", status="in_review", result="Workers: write/sonnet×1 (x)")
    srv.request_changes(project="demo", id="T-001", findings="f")
    ruta = _tarea(proyecto["mem"])
    from ratifact.registros import _leer_registro, _escribir_registro
    meta, cuerpo = _leer_registro(ruta)
    meta["status"] = "in_review"
    _escribir_registro(ruta, meta, cuerpo)
    srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    assert len(BLOQUE.findall(ruta.read_text())) == 2


def test_correccion_hace_commit(srv, proyecto):
    import subprocess
    _en_revision(srv, proyecto, "Workers: write/sonnet×1 (x)")
    srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    log = subprocess.run(["git", "-C", str(proyecto["mem"]), "log", "-1", "--format=%s"], capture_output=True,
                         text=True).stdout
    assert "T-001 → in_review" in log
    assert subprocess.run(["git", "-C", str(proyecto["mem"]), "status", "--porcelain"], capture_output=True,
                          text=True).stdout.strip() == ""


# ───────────────────────── criterios 6-7: propuesta ─────────────────────────

REAL1 = "Workers: explore/haiku×1, write/sonnet×1 (+1 correction batch on the same writer), verify/sonnet×1"
REAL2 = "Workers: explore/haiku×1, write/sonnet×1 (resumed once for the verify fix), verify/sonnet×1"


@pytest.mark.parametrize("linea,nota", [(REAL1, "+1 correction batch on the same writer"),
                                        (REAL2, "resumed once for the verify fix")])
def test_propuesta_de_las_lineas_reales(linea, nota):
    from ratifact.delegacion import parsear_workers, proponer_workers
    propuesta = proponer_workers(linea)
    t = parsear_workers(propuesta)
    assert t.reenvios == {"write": 1} and t.nota == nota and t.total == 3 and "(" not in propuesta.split(" — ")[0]


def test_propuesta_parentesis_sin_retrabajo_solo_nota():
    from ratifact.delegacion import parsear_workers, proponer_workers
    t = parsear_workers(proponer_workers("Workers: write/sonnet×1 (large refactor), verify/sonnet×1"))
    assert t.reenvios == {} and t.nota == "large refactor"


def test_propuesta_varios_roles_y_escalated():
    from ratifact.delegacion import parsear_workers, proponer_workers
    t = parsear_workers(proponer_workers(
        "Workers: write/sonnet×1 (retry), verify/sonnet×1 (re-run twice), escalated: write"))
    assert t.reenvios == {"write": 1, "verify": 1} and t.escalados == ["write"] and t.nota == "retry; re-run twice"


@pytest.mark.parametrize("linea", ["Workers: write/sonnet", "Workers: write/sonnet×1 (oops", "Workers: foo (bar)",
                                   "Workers: none (x)", "sin linea"])
def test_propuesta_no_derivable(linea):
    from ratifact.delegacion import proponer_workers
    assert proponer_workers(linea) is None


def test_aviso_incluye_propuesta_o_ejemplo(srv, proyecto):
    _en_curso(srv)
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=REAL2)
    propuesta = re.search(r"^(Workers: .*)$", salida, re.M).group(1)
    assert "rework: write×1 — note: resumed once for the verify fix" in propuesta
    assert 'update_task(project, id, "in_review"' in salida and "only that line" in salida
    _en_curso(srv, "T-002")
    salida = srv.update_task(project="demo", id="T-002", status="in_review", result="Workers: write/sonnet")
    assert "for example `Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1, rework: write×1 — note:" in salida


# ───────────────────────── criterios 8-9: cliente ─────────────────────────

def test_cliente_actual_normal_saneado_y_unknown():
    from ratifact.delegacion import cliente_actual
    assert cliente_actual() == "unknown"                                   # fuera de una petición
    with cliente("claude-code", "2.1.0"):
        assert cliente_actual() == "claude-code/2.1.0"
    with cliente("Mi Cliente · raro=1,\nx\ty", "v 1"):
        c = cliente_actual()
        assert c == "Mi-Cliente-raro-1-x-y/v-1" and not re.search(r"[\s·=,]", c)
    with cliente("x" * 100, "1"):
        assert len(cliente_actual()) == 64
    with cliente(info=False):
        assert cliente_actual() == "unknown"
    with cliente(None, None):
        assert cliente_actual() == "unknown"
    with cliente("solo-nombre", None):
        assert cliente_actual() == "solo-nombre/unknown"


def test_routing_y_uso_llevan_client(srv, proyecto, entorno):
    with cliente("codex", "0.9"):
        _en_curso(srv)
    m = _meta(proyecto["mem"])["routing"]
    assert m.endswith(" · client=codex/0.9")
    from ratifact.delegacion import at_de_routing, build_de_routing, cliente_de_routing, politica_de_routing
    assert cliente_de_routing(m) == "codex/0.9" and politica_de_routing(m) == "required"
    assert build_de_routing(m) and at_de_routing(m) is not None
    assert {f["client"] for f in _filas(entorno) if f["herramienta"] in ("create_task", "update_task")} == {"codex/0.9"}


def test_routing_sin_clientinfo_es_unknown(srv, proyecto, entorno):
    with cliente(info=False):
        _en_curso(srv)
    assert _meta(proyecto["mem"])["routing"].endswith(" · client=unknown")
    assert _filas(entorno)[-1]["client"] == "unknown"


def test_lectores_aceptan_todos_los_formatos():
    from ratifact.delegacion import at_de_routing, build_de_routing, cliente_de_routing, politica_de_routing
    base = "explore=haiku,write=sonnet,verify=sonnet · delegation=suggested"
    con_todo = base + " · build=1.0.0+abc1234 · at=2026-10-25T18:40-06:00 · client=a/b"
    solo_client = base + " · client=a/b"
    for r in (base, base + " · build=1.0.0+abc1234", con_todo, solo_client):
        assert politica_de_routing(r) == "suggested"
    assert cliente_de_routing(base) == "unknown" and cliente_de_routing(con_todo) == "a/b"
    assert build_de_routing(base) is None and build_de_routing(solo_client) is None
    assert at_de_routing(con_todo) is not None and at_de_routing(solo_client) is None
    assert at_de_routing("x · client=bat=2026-10-25T18:40") is None      # `at=` dentro de otro valor no cuenta


def test_aviso_in_review_con_routing_viejo_y_nuevo(srv, proyecto):
    from ratifact.registros import _escribir_registro, _leer_registro
    for id_, routing in (("T-001", "explore=haiku,write=sonnet,verify=sonnet · delegation=required"),
                         ("T-002", "explore=haiku,write=sonnet,verify=sonnet · delegation=required · client=a/b")):
        _en_curso(srv, id_)
        ruta = _tarea(proyecto["mem"], id_)
        meta, cuerpo = _leer_registro(ruta)
        meta["routing"] = routing
        _escribir_registro(ruta, meta, cuerpo)
        assert "⚠" in srv.update_task(project="demo", id=id_, status="in_review", result="hecho")


def test_fila_de_uso_sin_client_se_lee(entorno, monkeypatch, capsys):
    """Un registro viejo (sin `client`) y uno nuevo conviven en el log que lee el CLI."""
    from test_analizar_uso import _correr, _log_filas
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "search", "resp_chars": 10},
                                                              {"herramienta": "search", "resp_chars": 10,
                                                               "client": "a/b"}])
    _correr(monkeypatch, "--log", str(log))
    assert "search" in capsys.readouterr().out


# ───────────────────────── criterio 10: report ─────────────────────────

def test_report_retrabajo_y_desglose_por_cliente(srv, proyecto, entorno):
    from ratifact.informe_memoria import indicador_delegacion
    from ratifact.registros import _escribir_registro, _leer_registro
    with cliente("claude-code", "2"):
        _en_curso(srv, "T-001")
        srv.update_task(project="demo", id="T-001", status="in_review",
                        result="Workers: write/sonnet×1, verify/sonnet×1, rework: write×2, verify×1 — note: x")
        _en_curso(srv, "T-002")
        srv.update_task(project="demo", id="T-002", status="in_review", result=WORKERS_OK)
        _en_curso(srv, "T-003")      # línea inválida primero, válida después (la última válida cuenta)
        srv.update_task(project="demo", id="T-003", status="in_review",
                        result="Workers: write/sonnet×1, rework: write×1\nWorkers: write/sonnet×1 (x)")
    with cliente("codex", "0.9"):
        _en_curso(srv, "T-004")
        srv.update_task(project="demo", id="T-004", status="in_review",
                        result="Workers: write/sonnet×1 (rework once)")      # inválida
    _en_curso(srv, "T-005")                                                                    # formato viejo
    srv.update_task(project="demo", id="T-005", status="in_review", result="Workers: write/sonnet×1, rework: write×1")
    ruta = _tarea(proyecto["mem"], "T-005")
    meta, cuerpo = _leer_registro(ruta)
    meta["routing"] = "explore=haiku,write=sonnet,verify=sonnet · delegation=required"
    _escribir_registro(ruta, meta, cuerpo)
    lineas = indicador_delegacion(dt.datetime.now() - dt.timedelta(days=7), "demo")
    assert lineas[0].startswith("  demo: 5 tasks with routing · required 5 · with workers")
    assert "    rework: with rework 3 of 4 delegated · rate 75 % · resends write×4, verify×1 · escalations 0" \
        in lineas
    assert "    per client claude-code/2: 3 tasks · compliance 100 % · rework 67 %" in lineas
    assert "    per client codex/0.9: 1 task · compliance 0 % · rework —" in lineas
    assert "    per client unknown: 1 task · compliance 100 % · rework 100 %" in lineas


def test_report_cuenta_la_ultima_linea_valida_aunque_haya_una_invalida_despues(srv, proyecto):
    from ratifact.informe_memoria import indicador_delegacion
    _en_curso(srv)
    srv.update_task(project="demo", id="T-001", status="in_review",
                    result="Workers: write/sonnet×1, rework: write×1, escalated: write\nWorkers: write/sonnet×1 (x)")
    lineas = indicador_delegacion(dt.datetime.now() - dt.timedelta(days=7), "demo")
    assert "required 1 · with workers 1 · compliance 100 % · escalations 1" in lineas[0]
    assert lineas[1].startswith("    delegated: 1 task")
    assert "    rework: with rework 1 of 1 delegated · rate 100 % · resends write×1 · escalations 1" in lineas


def test_correccion_con_review_tras_otro_encabezado_cae_al_comportamiento_normal(srv, proyecto):
    _en_curso(srv)
    srv.update_task(project="demo", id="T-001", status="in_review", result="Workers: write/sonnet×1 (x)")
    ruta = _tarea(proyecto["mem"])
    from ratifact.registros import _escribir_registro, _leer_registro
    meta, cuerpo = _leer_registro(ruta)
    _escribir_registro(ruta, meta, cuerpo.rstrip() + "\n\n## Notas\nalgo\n\n### Review 1 · 2026-10-31\nf\n")
    srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    assert len(BLOQUE.findall(ruta.read_text())) == 2
