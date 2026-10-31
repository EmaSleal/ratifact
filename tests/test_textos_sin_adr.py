"""T-021 criteria 16 and 19: text shown to the user (CLI output, MCP tool responses) cites no ADR-NNN identifier.
Ids of records the test itself creates (ADR-001...) are data, not citations, and are the only ones allowed."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

from conftest import crear_repo, recargar_servidor
from test_analizar_uso import _log_filas
from test_install import casa, instalar, maquina, paquete  # noqa: F401  (fixtures)
from test_upgrade import correr, hogar, vieja  # noqa: F401,F811  (fixtures)

ADR = re.compile(r"ADR[- ]?\d{3}|\b[TtPp]-\d+\b")   # ADR-NNN and the development-history ids T-NNN / P-NNN


def sin_citas(texto: str, permitidos: tuple[str, ...] = ()) -> list[str]:
    """Matches of ADR-NNN, T-NNN or P-NNN that are not the id of a record created by the test."""
    return [m for m in ADR.findall(texto) if m.upper() not in {x.upper() for x in permitidos}]


# ───────────────────────── CLI ─────────────────────────

def test_ayuda_de_la_cli_sin_adr(capsys):
    from ratifact import cli
    textos = []
    for argumentos in ([], ["install"], ["upgrade"], ["doctor"], ["report"], ["serve"]):
        with pytest.raises(SystemExit):
            cli.main([*argumentos, "--help"])
        textos.append(capsys.readouterr().out)
    assert "--apply" in textos[2] and "English keys" in textos[0]
    assert "--days DAYS" in textos[4] and "--project PROJECT" in textos[4]
    assert sin_espanol("\n".join(textos).replace("--dias", "").replace("--proyecto", "")) == []
    assert sin_citas("\n".join(textos)) == []


def test_install_plan_y_apply_sin_adr(maquina, paquete, capsys):
    _, plan = instalar(capsys, paquete)
    assert "never asked" in plan and "Integrations per project" in plan
    assert sin_citas(plan) == [] and sin_espanol(plan) == []
    _, aplicado = instalar(capsys, paquete, aplicar=True)
    assert sin_citas(aplicado) == [] and sin_espanol(aplicado) == []


def test_upgrade_plan_y_apply_sin_adr(vieja, capsys):
    _, plan = correr(vieja, capsys)
    assert "Dry run: nothing was changed" in plan and sin_citas(plan) == [] and sin_espanol(plan) == []
    _, aplicado = correr(vieja, capsys, aplicar=True)
    assert sin_citas(aplicado) == [] and sin_espanol(aplicado) == []


def test_doctor_sin_adr_en_ninguna_plataforma(vieja, capsys, monkeypatch, tmp_path):
    from ratifact import doctor
    textos = []
    for plataforma, osrelease in (("linux", "6.1.0-generic"), ("win32", "6.1.0-generic"),
                                  ("linux", "5.15.153.1-microsoft-standard-WSL2")):
        monkeypatch.setattr(doctor.sys, "platform", plataforma)
        monkeypatch.setattr(doctor, "_osrelease", lambda o=osrelease: o)
        doctor.main(procesos=lambda: [], paquete=tmp_path, log_viejo=vieja["log"])
        textos.append(capsys.readouterr().out)
    assert "Native Windows is not a supported platform: install ratifact inside WSL2" in textos[1]
    assert "Running inside WSL: supported" in textos[2]
    assert sin_citas("\n".join(textos)) == [] and sin_espanol("\n".join(textos)) == []


def test_doctor_memoria_dentro_del_repo_explica_el_motivo(vieja, capsys):
    repo = vieja["base"] / "uno" / "codigo"
    config = Path(vieja["config"])
    datos = json.loads(config.read_text())
    datos["uno"]["memoria"] = str(repo / ".project")
    config.write_text(json.dumps(datos))
    from ratifact import doctor
    doctor.main(procesos=lambda: [], paquete=None, log_viejo=vieja["log"])
    salida = capsys.readouterr().out
    assert "the memory is inside the code repository (it would be committed and published with the code)" in salida
    assert sin_citas(salida) == []


def test_report_sin_adr(entorno, monkeypatch, capsys):
    from ratifact import cli
    filas = [{"herramienta": h, "resp_chars": 10} for h in ("propose_decision", "add_pending", "create_task", "search")]
    filas += [{"herramienta": "propose_decision", "resp_chars": 10, "duplicado": True}]
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)
    cli.main(["report", "--log", str(log), "--days", "14"])
    salida = capsys.readouterr().out
    assert "Idempotent creations:" in salida and "Real-use criterion for 1.0" in salida
    assert "Delegation: tasks with `routing:`" in salida
    assert sin_citas(salida) == []


# ───────────────────────── criterion 22: everything the CLI prints is English ─────────────────────────

PALABRAS_EN_ESPANOL = ("Creaciones", "Criterio", "Delegación", "tareas", "pendientes", "decisiones", "uso real",
                       "llamadas", "errores", "interno", "validacion")


def sin_espanol(texto: str) -> list[str]:
    return [p for p in PALABRAS_EN_ESPANOL if re.search(rf"\b{re.escape(p)}\b", texto, re.I)]


def test_report_completo_en_ingles(srv, proyecto, entorno, monkeypatch, capsys):
    """Report with idempotent creations, delegation, rework and per-client breakdown; plus empty and missing log."""
    from ratifact import cli
    from test_delegacion import WORKERS_OK, _en_curso
    from test_workers_adr041 import cliente
    with cliente("claude-code", "2"):
        _en_curso(srv, "T-001")
        srv.update_task(project="demo", id="T-001", status="in_review",
                        result="Workers: write/sonnet×1, verify/sonnet×1, rework: write×2 — note: x")
    filas = [{"herramienta": h, "resp_chars": 10, "error": False}
             for h in ("get_context", "read_document", "search", "propose_decision", "add_pending", "create_task")]
    filas += [{"herramienta": "propose_decision", "resp_chars": 10, "duplicado": True},
              {"herramienta": "search", "resp_chars": 10, "error": True, "tipo_error": "interno", "detalle": "x"},
              {"herramienta": "search", "resp_chars": 10, "error": True, "tipo_error": "validacion", "detalle": "y"}]
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)
    cli.main(["report", "--log", str(log), "--days", "14"])
    salida = capsys.readouterr().out
    for encabezado in ("Idempotent creations:", "Real-use criterion for 1.0", "Delegation: tasks with `routing:`",
                       "tasks with routing", "rework: with rework", "per client claude-code/2:",
                       "Open pending items referenced by merged tasks", "Latest errors", "Largest responses", "[internal]", "[validation]"):
        assert encabezado in salida, encabezado
    assert sin_espanol(salida) == [], salida
    # empty period (no rows inside the window) and missing log
    vacio = _log_filas(entorno["tmp"] / "log" / "vacio.jsonl", [{"herramienta": "search", "resp_chars": 1}])
    cli.main(["report", "--log", str(vacio), "--days", "0"])
    assert "No calls in the period." in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["report", "--log", str(entorno["tmp"] / "no-existe.jsonl")])
    assert sin_espanol(capsys.readouterr().err) == []


# ───────────────────────── respuestas de las herramientas MCP ─────────────────────────

def test_respuestas_de_las_herramientas_sin_adr(srv, proyecto, entorno):
    repo = proyecto["repo"]
    (repo / ".codegraph").mkdir()          # integraciones detectadas: guía de ejecución/verificación/cierre
    (repo / ".atl").mkdir()
    respuestas: list[str] = []
    creados: list[str] = []

    def llamar(herramienta, **kw):
        salida = getattr(srv, herramienta)(**kw)
        respuestas.append(str(salida))
        if herramienta.startswith(("propose", "create", "add")):
            creados.extend(re.findall(r"\b(?:ADR|T|P)-\d{3,}\b", str(salida)))
        return salida

    llamar("get_context", project="demo")
    llamar("list_projects")
    llamar("project_instructions", project="demo")
    # errores de validación con los textos reescritos
    dentro = crear_repo(entorno["base"] / "interno")
    assert "ERROR" in llamar("register_project", name="interno", path=str(dentro), memory=str(dentro / ".project"))
    assert "ERROR" in llamar("register_project", name="interno", path=str(dentro), memory=str(dentro / ".project"),
                             tests="x")
    assert "ERROR" in llamar("update_project", name="demo", path=str(entorno["base"]))
    assert "ERROR" in llamar("review_proposals", project="demo", from_id="no-es-un-id")
    llamar("update_project", name="demo", models="explore=haiku,write=sonnet", delegation="required")
    # decisiones
    llamar("propose_decision", project="demo", title="Usar X", decision="d", rationale="r")
    llamar("propose_decision", project="demo", title="Usar X", decision="d", rationale="r")      # idempotente
    llamar("review_proposals", project="demo", from_id="ADR-001")
    llamar("review_proposals", project="demo", summary=True)
    llamar("accept_decision", project="demo", id="ADR-001", user_quote="sí, acepto")
    # pendientes y sesiones
    llamar("add_pending", project="demo", topic="tema", context="c")
    llamar("add_pending", project="demo", topic="tema", context="c")                              # idempotente
    llamar("log_session", project="demo", summary="s")
    # tareas: integración, enrutamiento, delegación y validación de Workers
    llamar("create_task", project="demo", title="Hacer Y", goal="g", acceptance_criteria="c", decisions="ADR-001",
           resolves="P-001", delegation="required")
    llamar("create_task", project="demo", title="Hacer Y", goal="g", acceptance_criteria="c")     # idempotente
    llamar("read_task", project="demo", id="T-001")
    llamar("amend_task", project="demo", id="T-001", additional_criteria="más", delegation="off")
    llamar("update_task", project="demo", id="T-001", status="in_progress")
    llamar("update_task", project="demo", id="T-001", status="in_review", result="Hecho.")        # sin Workers
    llamar("update_task", project="demo", id="T-001", status="in_review", result="Workers: write/sonnet×1 (x)")
    llamar("update_task", project="demo", id="T-001", status="in_review", result="Workers: write/sonnet×1")
    llamar("request_changes", project="demo", id="T-001", findings="f")
    llamar("update_task", project="demo", id="T-001", status="in_progress")
    llamar("update_task", project="demo", id="T-001", status="merged")
    llamar("list_tasks", project="demo", include_closed=True)
    # documentos
    llamar("read_document", project="demo", path="T-001")
    llamar("read_document", project="demo", path="ADR-001-no-existe.md")
    llamar("search", project="demo", query="Usar")
    llamar("list_documents", project="demo")
    permitidos = tuple(sorted(set(creados) | {"ADR-001"}))
    for texto in respuestas:
        assert sin_citas(texto, permitidos) == [], texto
