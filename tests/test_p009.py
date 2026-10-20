"""P-009 (a–d): errores de validación en decide_proposals, búsqueda exacta por id, orden numérico de ids en
review_proposals y reloj de log_session tomado de registros._ahora."""
import asyncio
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ratifact import registros


def _escribir_adr(mem: Path, numero: int, estado: str = "proposed") -> Path:
    id_ = f"ADR-{numero:03d}"
    ruta = mem / "decisions" / f"{id_}-titulo-{numero}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(f"---\nid: {id_}\ntitle: Titulo {numero}\nstatus: {estado}\ndate: 2026-01-01\n"
                    f"summary: Resumen {numero}\n---\n# {id_} — Titulo {numero}\n", encoding="utf-8")
    return ruta


def _filas_log(entorno) -> list[dict]:
    return [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]


# ───────────────────────── (a) decide_proposals: errores de validación ─────────────────────────

def _ctx_con_formularios():
    """Contexto falso con elicitation declarada (lo único que decide_proposals lee antes de tocar la memoria)."""
    async def elicit(*_a, **_k):
        raise AssertionError("no debería abrir formularios")
    capacidades = SimpleNamespace(elicitation=SimpleNamespace())
    return SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(capabilities=capacidades)),
                           elicit=elicit)


def test_decidir_propuestas_proyecto_no_registrado_devuelve_error_de_validacion(srv, proyecto, entorno):
    salida = asyncio.run(srv.decide_proposals(project="fantasma", ctx=_ctx_con_formularios()))

    assert salida.startswith("ERROR: Project 'fantasma' is not registered."), salida
    fila = [f for f in _filas_log(entorno) if f["herramienta"] == "decide_proposals"][-1]
    assert fila["error"] is True and fila["tipo_error"] == "validacion"


def test_decidir_propuestas_falla_inesperada_es_error_interno(srv, proyecto, entorno, monkeypatch, capsys):
    from ratifact.herramientas import decisiones

    def explota(_):
        raise RuntimeError("disco roto")
    monkeypatch.setattr(decisiones, "_mem", explota)

    salida = asyncio.run(srv.decide_proposals(project="demo", ctx=_ctx_con_formularios()))

    assert salida == "ERROR (internal): RuntimeError: disco roto"
    assert "Traceback" in capsys.readouterr().err
    fila = [f for f in _filas_log(entorno) if f["herramienta"] == "decide_proposals"][-1]
    assert fila["error"] is True and fila["tipo_error"] == "interno"


# ───────────────────────── (b) _buscar_registro exacto ─────────────────────────

@pytest.mark.parametrize("pedido, esperado", [
    ("ADR-01", "ADR-001"), ("ADR-1", "ADR-001"), ("adr-11", "ADR-011"), ("ADR-010", "ADR-010"), ("ADR-0012", "ADR-012"),
])
def test_buscar_registro_normaliza_y_es_exacto(srv, proyecto, pedido, esperado):
    for n in (1, 10, 11, 12):
        _escribir_adr(proyecto["mem"], n)
    ruta = registros._buscar_registro(proyecto["mem"] / "decisions", pedido)
    assert ruta.name.startswith(f"{esperado}-")


def test_buscar_registro_inexistente_muestra_id_normalizado(srv, proyecto):
    _escribir_adr(proyecto["mem"], 1)
    with pytest.raises(srv.ErrorMemoria, match=r"^ADR-099 does not exist\.$"):
        registros._buscar_registro(proyecto["mem"] / "decisions", "adr-99")


def test_buscar_registro_no_trunca_ids_de_cuatro_cifras(srv, proyecto):
    _escribir_adr(proyecto["mem"], 100)
    _escribir_adr(proyecto["mem"], 1000)
    assert registros._buscar_registro(proyecto["mem"] / "decisions", "ADR-1000").name.startswith("ADR-1000-")
    assert registros._buscar_registro(proyecto["mem"] / "decisions", "ADR-100").name.startswith("ADR-100-")


def test_buscar_registro_acepta_archivo_sin_slug(srv, proyecto):
    carpeta = proyecto["mem"] / "decisions"
    _escribir_adr(proyecto["mem"], 10)
    (carpeta / "ADR-001.md").write_text("---\nid: ADR-001\nstatus: proposed\n---\n", encoding="utf-8")
    assert registros._buscar_registro(carpeta, "ADR-01").name == "ADR-001.md"


def test_confirmar_decision_adr_01_no_toca_adr_010(srv, proyecto):
    _escribir_adr(proyecto["mem"], 1)
    for n in (10, 11, 12):
        _escribir_adr(proyecto["mem"], n)

    assert srv.accept_decision(project="demo", id="ADR-01", user_quote="sí, dale").startswith("ADR-001 → accepted")
    assert "status: proposed" in next((proyecto["mem"] / "decisions").glob("ADR-010-*.md")).read_text()
    assert srv.reject_decision(project="demo", id="adr-11", reason="no va").startswith("ADR-011 → rejected")
    assert srv.accept_decision(project="demo", id="ADR-099", user_quote="sí") == "ERROR: ADR-099 does not exist."


def test_cerrar_pendiente_p_1_es_exacto(srv, proyecto):
    for i in range(1, 11):
        srv.add_pending(project="demo", topic=f"Tema {i}", context="c")
    assert srv.close_pending(project="demo", id="p-1", resolution="listo").startswith("P-001 → closed")
    assert "status: open" in next((proyecto["mem"] / "pending").glob("P-010-*.md")).read_text()
    assert srv.close_pending(project="demo", id="P-11", resolution="x") == "ERROR: P-011 does not exist."


def test_actualizar_tarea_t_1_es_exacta(srv, proyecto):
    for i in range(1, 11):
        srv.create_task(project="demo", title=f"Tarea {i}", goal="o", acceptance_criteria="- c")
    salida = srv.update_task(project="demo", id="t-1", status="en_curso")
    assert "T-001" in salida and not salida.startswith("ERROR"), salida
    assert "status: todo" in next((proyecto["mem"] / "tasks").glob("T-010-*.md")).read_text()
    assert srv.update_task(project="demo", id="T-11", status="en_curso") == "ERROR: T-011 does not exist."


# ───────────────────────── (c) review_proposals: orden numérico ─────────────────────────

def test_revisar_propuestas_ordena_por_numero(srv, proyecto):
    for n in (1000, 999, 2):
        _escribir_adr(proyecto["mem"], n)
    salida = srv.review_proposals(project="demo", summary=True)
    assert salida.index("**ADR-002**") < salida.index("**ADR-999**") < salida.index("**ADR-1000**")


def test_revisar_propuestas_desde_id_compara_numeros(srv, proyecto):
    for n in (998, 999, 1000):
        _escribir_adr(proyecto["mem"], n)
    salida = srv.review_proposals(project="demo", from_id="ADR-999", summary=True)
    assert salida.startswith("2 proposal(s) to review; showing 2.")
    assert "**ADR-999**" in salida and "**ADR-1000**" in salida and "ADR-998" not in salida


def test_revisar_propuestas_paginacion_cruza_el_salto_de_cifras(srv, proyecto):
    for n in (999, 1000):
        _escribir_adr(proyecto["mem"], n)
    salida = srv.review_proposals(project="demo", limit=1, summary=True)
    assert "**ADR-999**" in salida
    assert salida.endswith('(1 proposal(s) left: continue with from_id="ADR-1000".)')


# ───────────────────────── (d) log_session: reloj de registros._ahora ─────────────────────────

def test_registrar_sesion_toma_la_hora_de_ahora(srv, proyecto, monkeypatch):
    hoy = dt.date.today()
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(hoy.year, hoy.month, hoy.day, 7, 5, 42))

    salida = srv.log_session(project="demo", summary="Sesión de prueba")

    assert not salida.startswith("ERROR"), salida
    texto = (proyecto["mem"] / "sessions" / f"{hoy.isoformat()}.md").read_text(encoding="utf-8")
    assert "\n## 07:05\nSesión de prueba\n" in texto
