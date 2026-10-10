"""Idempotencia de las tools de creación (ADR-019): reintentar una llamada perdida en el cliente (p. ej.
Claude Desktop, timeout de 120s) nunca debe duplicar un ADR, un pendiente o una tarea con el mismo título,
dentro de una ventana de tiempo. Sin idempotency key del cliente (fuera de alcance v1)."""
import datetime as dt
import json
from pathlib import Path

from conftest import log_git


# ───────────────────────── registrar_decision ─────────────────────────

def test_decision_duplicada_no_crea_archivo_ni_commit(srv, proyecto):
    r1 = srv.registrar_decision(proyecto="demo", titulo="Usar Godot", decision="Godot 4", justificacion="2D nativo")
    assert "ADR-001 registrada como propuesta" in r1
    historial_antes = log_git(proyecto["mem"])
    archivos_antes = sorted((proyecto["mem"] / "decisiones").glob("ADR-*.md"))

    r2 = srv.registrar_decision(proyecto="demo", titulo="Usar Godot", decision="Godot 4", justificacion="2D nativo")

    assert "ADR-001" in r2 and srv.MARCA_DUPLICADO in r2
    assert sorted((proyecto["mem"] / "decisiones").glob("ADR-*.md")) == archivos_antes   # ningún archivo nuevo
    assert not (proyecto["mem"] / "decisiones" / "ADR-002").exists()
    assert log_git(proyecto["mem"]) == historial_antes   # ningún commit nuevo (criterio 5)


# ───────────────────────── registrar_pendiente ─────────────────────────

def test_pendiente_duplicado_no_crea_nada_y_devuelve_el_id_existente(srv, proyecto):
    r1 = srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="Sin decidir")
    assert "P-001 registrado" in r1
    historial_antes = log_git(proyecto["mem"])

    r2 = srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="Otro contexto, da igual")

    assert "P-001" in r2 and srv.MARCA_DUPLICADO in r2
    assert len(list((proyecto["mem"] / "pendientes").glob("P-*.md"))) == 1
    assert log_git(proyecto["mem"]) == historial_antes


# ───────────────────────── registrar_tarea ─────────────────────────

def test_tarea_duplicada_no_crea_nada_y_devuelve_el_id_existente(srv, proyecto):
    r1 = srv.registrar_tarea(proyecto="demo", titulo="Ranuras de forma", objetivo="Dos ranuras",
                              criterios_aceptacion="- pruebas verdes")
    assert "T-001 registrada" in r1
    historial_antes = log_git(proyecto["mem"])

    r2 = srv.registrar_tarea(proyecto="demo", titulo="Ranuras de forma", objetivo="otro objetivo",
                              criterios_aceptacion="- otros criterios")

    assert "T-001" in r2 and srv.MARCA_DUPLICADO in r2
    assert len(list((proyecto["mem"] / "tareas").glob("T-*.md"))) == 1
    assert log_git(proyecto["mem"]) == historial_antes


# ───────────────────────── normalización del título (criterio 3) ─────────────────────────

def test_normalizacion_case_insensitive_trim_y_espacios_colapsados(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="  Revisar   Parry ", contexto="c")
    r2 = srv.registrar_pendiente(proyecto="demo", tema="revisar parry", contexto="c2")
    assert "P-001" in r2 and srv.MARCA_DUPLICADO in r2
    assert len(list((proyecto["mem"] / "pendientes").glob("P-*.md"))) == 1


def test_titulos_realmente_distintos_no_son_duplicados(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")
    r2 = srv.registrar_pendiente(proyecto="demo", tema="Parry extendido", contexto="c")
    assert "P-002 registrado" in r2
    assert len(list((proyecto["mem"] / "pendientes").glob("P-*.md"))) == 2


def test_tipos_distintos_nunca_coinciden_entre_si(srv, proyecto):
    """Un ADR y una tarea con el mismo título textual no son duplicados entre sí (carpetas/prefijos distintos)."""
    r_adr = srv.registrar_decision(proyecto="demo", titulo="Mismo título", decision="d", justificacion="j")
    r_pend = srv.registrar_pendiente(proyecto="demo", tema="Mismo título", contexto="c")
    r_tarea = srv.registrar_tarea(proyecto="demo", titulo="Mismo título", objetivo="o", criterios_aceptacion="c")

    assert "ADR-001 registrada" in r_adr
    assert "P-001 registrado" in r_pend
    assert "T-001 registrada" in r_tarea
    for r in (r_adr, r_pend, r_tarea):
        assert srv.MARCA_DUPLICADO not in r


# ───────────────────────── ventana de tiempo (criterio 4) ─────────────────────────

def test_fuera_de_la_ventana_se_crea_normalmente(srv, proyecto, monkeypatch):
    t0 = dt.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(srv, "_ahora", lambda: t0)
    r1 = srv.registrar_decision(proyecto="demo", titulo="Usar Godot", decision="d", justificacion="j")
    assert "ADR-001 registrada" in r1

    despues = t0 + dt.timedelta(minutes=srv.VENTANA_IDEMPOTENCIA_MINUTOS + 1)
    monkeypatch.setattr(srv, "_ahora", lambda: despues)
    r2 = srv.registrar_decision(proyecto="demo", titulo="Usar Godot", decision="d", justificacion="j")

    assert "ADR-002 registrada" in r2
    assert srv.MARCA_DUPLICADO not in r2
    assert len(list((proyecto["mem"] / "decisiones").glob("ADR-*.md"))) == 2


def test_dentro_de_la_ventana_justo_en_el_limite_se_considera_duplicado(srv, proyecto, monkeypatch):
    t0 = dt.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(srv, "_ahora", lambda: t0)
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")

    casi = t0 + dt.timedelta(minutes=srv.VENTANA_IDEMPOTENCIA_MINUTOS - 1)
    monkeypatch.setattr(srv, "_ahora", lambda: casi)
    r2 = srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")
    assert srv.MARCA_DUPLICADO in r2


# ───────────────────────── telemetría (criterio 6) ─────────────────────────

def test_telemetria_marca_duplicado_sin_error(srv, proyecto, entorno):
    srv.registrar_decision(proyecto="demo", titulo="Usar Godot", decision="d", justificacion="j")
    srv.registrar_decision(proyecto="demo", titulo="usar   godot", decision="d", justificacion="j")

    filas = [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]
    propias = [f for f in filas if f["herramienta"] == "registrar_decision"]
    assert len(propias) == 2
    assert propias[0]["duplicado"] is False and propias[0]["error"] is False
    assert propias[1]["duplicado"] is True and propias[1]["error"] is False


def test_analizar_uso_reporta_duplicados(srv, proyecto, entorno, monkeypatch, capsys):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")
    srv.registrar_pendiente(proyecto="demo", tema="parry", contexto="c")
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c")

    import sys
    import analizar_uso
    importlib_reload = __import__("importlib").reload
    importlib_reload(analizar_uso)
    monkeypatch.setattr(analizar_uso, "LOG", Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]))
    monkeypatch.setattr(sys, "argv", ["analizar_uso.py"])

    analizar_uso.main()

    salida = capsys.readouterr().out
    assert "Creaciones idempotentes" in salida
    assert "duplicados detectados" in salida
    assert "1" in salida.split("duplicados detectados")[1].split("\n")[0]
