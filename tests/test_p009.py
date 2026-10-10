"""P-009 (a–d): errores de validación en decidir_propuestas, búsqueda exacta por id, orden numérico de ids en
revisar_propuestas y reloj de registrar_sesion tomado de registros._ahora."""
import asyncio
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ratifact import registros


def _escribir_adr(mem: Path, numero: int, estado: str = "propuesta") -> Path:
    id_ = f"ADR-{numero:03d}"
    ruta = mem / "decisiones" / f"{id_}-titulo-{numero}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(f"---\nid: {id_}\ntitulo: Titulo {numero}\nestado: {estado}\nfecha: 2026-01-01\n"
                    f"resumen: Resumen {numero}\n---\n# {id_} — Titulo {numero}\n", encoding="utf-8")
    return ruta


def _filas_log(entorno) -> list[dict]:
    return [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]


# ───────────────────────── (a) decidir_propuestas: errores de validación ─────────────────────────

def _ctx_con_formularios():
    """Contexto falso con elicitation declarada (lo único que decidir_propuestas lee antes de tocar la memoria)."""
    async def elicit(*_a, **_k):
        raise AssertionError("no debería abrir formularios")
    capacidades = SimpleNamespace(elicitation=SimpleNamespace())
    return SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(capabilities=capacidades)),
                           elicit=elicit)


def test_decidir_propuestas_proyecto_no_registrado_devuelve_error_de_validacion(srv, proyecto, entorno):
    salida = asyncio.run(srv.decidir_propuestas(proyecto="fantasma", ctx=_ctx_con_formularios()))

    assert salida.startswith("ERROR: Proyecto 'fantasma' no registrado."), salida
    fila = [f for f in _filas_log(entorno) if f["herramienta"] == "decidir_propuestas"][-1]
    assert fila["error"] is True and fila["tipo_error"] == "validacion"


def test_decidir_propuestas_falla_inesperada_es_error_interno(srv, proyecto, entorno, monkeypatch, capsys):
    from ratifact.herramientas import decisiones

    def explota(_):
        raise RuntimeError("disco roto")
    monkeypatch.setattr(decisiones, "_mem", explota)

    salida = asyncio.run(srv.decidir_propuestas(proyecto="demo", ctx=_ctx_con_formularios()))

    assert salida == "ERROR INTERNO: RuntimeError: disco roto"
    assert "Traceback" in capsys.readouterr().err
    fila = [f for f in _filas_log(entorno) if f["herramienta"] == "decidir_propuestas"][-1]
    assert fila["error"] is True and fila["tipo_error"] == "interno"


# ───────────────────────── (b) _buscar_registro exacto ─────────────────────────

@pytest.mark.parametrize("pedido, esperado", [
    ("ADR-01", "ADR-001"), ("ADR-1", "ADR-001"), ("adr-11", "ADR-011"), ("ADR-010", "ADR-010"), ("ADR-0012", "ADR-012"),
])
def test_buscar_registro_normaliza_y_es_exacto(srv, proyecto, pedido, esperado):
    for n in (1, 10, 11, 12):
        _escribir_adr(proyecto["mem"], n)
    ruta = registros._buscar_registro(proyecto["mem"] / "decisiones", pedido)
    assert ruta.name.startswith(f"{esperado}-")


def test_buscar_registro_inexistente_muestra_id_normalizado(srv, proyecto):
    _escribir_adr(proyecto["mem"], 1)
    with pytest.raises(srv.ErrorMemoria, match=r"^No existe ADR-099\.$"):
        registros._buscar_registro(proyecto["mem"] / "decisiones", "adr-99")


def test_buscar_registro_no_trunca_ids_de_cuatro_cifras(srv, proyecto):
    _escribir_adr(proyecto["mem"], 100)
    _escribir_adr(proyecto["mem"], 1000)
    assert registros._buscar_registro(proyecto["mem"] / "decisiones", "ADR-1000").name.startswith("ADR-1000-")
    assert registros._buscar_registro(proyecto["mem"] / "decisiones", "ADR-100").name.startswith("ADR-100-")


def test_buscar_registro_acepta_archivo_sin_slug(srv, proyecto):
    carpeta = proyecto["mem"] / "decisiones"
    _escribir_adr(proyecto["mem"], 10)
    (carpeta / "ADR-001.md").write_text("---\nid: ADR-001\nestado: propuesta\n---\n", encoding="utf-8")
    assert registros._buscar_registro(carpeta, "ADR-01").name == "ADR-001.md"


def test_confirmar_decision_adr_01_no_toca_adr_010(srv, proyecto):
    _escribir_adr(proyecto["mem"], 1)
    for n in (10, 11, 12):
        _escribir_adr(proyecto["mem"], n)

    assert srv.confirmar_decision(proyecto="demo", id="ADR-01", cita_usuario="sí, dale").startswith("ADR-001 acordada")
    assert "estado: propuesta" in next((proyecto["mem"] / "decisiones").glob("ADR-010-*.md")).read_text()
    assert srv.descartar_decision(proyecto="demo", id="adr-11", motivo="no va").startswith("ADR-011 descartada")
    assert srv.confirmar_decision(proyecto="demo", id="ADR-099", cita_usuario="sí") == "ERROR: No existe ADR-099."


def test_cerrar_pendiente_p_1_es_exacto(srv, proyecto):
    for i in range(1, 11):
        srv.registrar_pendiente(proyecto="demo", tema=f"Tema {i}", contexto="c")
    assert srv.cerrar_pendiente(proyecto="demo", id="p-1", resolucion="listo").startswith("P-001 cerrado")
    assert "estado: abierta" in next((proyecto["mem"] / "pendientes").glob("P-010-*.md")).read_text()
    assert srv.cerrar_pendiente(proyecto="demo", id="P-11", resolucion="x") == "ERROR: No existe P-011."


def test_actualizar_tarea_t_1_es_exacta(srv, proyecto):
    for i in range(1, 11):
        srv.registrar_tarea(proyecto="demo", titulo=f"Tarea {i}", objetivo="o", criterios_aceptacion="- c")
    salida = srv.actualizar_tarea(proyecto="demo", id="t-1", estado="en_curso")
    assert "T-001" in salida and not salida.startswith("ERROR"), salida
    assert "estado: pendiente" in next((proyecto["mem"] / "tareas").glob("T-010-*.md")).read_text()
    assert srv.actualizar_tarea(proyecto="demo", id="T-11", estado="en_curso") == "ERROR: No existe T-011."


# ───────────────────────── (c) revisar_propuestas: orden numérico ─────────────────────────

def test_revisar_propuestas_ordena_por_numero(srv, proyecto):
    for n in (1000, 999, 2):
        _escribir_adr(proyecto["mem"], n)
    salida = srv.revisar_propuestas(proyecto="demo", resumen=True)
    assert salida.index("**ADR-002**") < salida.index("**ADR-999**") < salida.index("**ADR-1000**")


def test_revisar_propuestas_desde_id_compara_numeros(srv, proyecto):
    for n in (998, 999, 1000):
        _escribir_adr(proyecto["mem"], n)
    salida = srv.revisar_propuestas(proyecto="demo", desde_id="ADR-999", resumen=True)
    assert salida.startswith("2 propuesta(s) por revisar; se muestran 2.")
    assert "**ADR-999**" in salida and "**ADR-1000**" in salida and "ADR-998" not in salida


def test_revisar_propuestas_paginacion_cruza_el_salto_de_cifras(srv, proyecto):
    for n in (999, 1000):
        _escribir_adr(proyecto["mem"], n)
    salida = srv.revisar_propuestas(proyecto="demo", cantidad=1, resumen=True)
    assert "**ADR-999**" in salida
    assert salida.endswith('(Quedan 1 propuesta(s): continúa con desde_id="ADR-1000".)')


# ───────────────────────── (d) registrar_sesion: reloj de registros._ahora ─────────────────────────

def test_registrar_sesion_toma_la_hora_de_ahora(srv, proyecto, monkeypatch):
    hoy = dt.date.today()
    monkeypatch.setattr(registros, "_ahora", lambda: dt.datetime(hoy.year, hoy.month, hoy.day, 7, 5, 42))

    salida = srv.registrar_sesion(proyecto="demo", resumen="Sesión de prueba")

    assert not salida.startswith("ERROR"), salida
    texto = (proyecto["mem"] / "sesiones" / f"{hoy.isoformat()}.md").read_text(encoding="utf-8")
    assert "\n## 07:05\nSesión de prueba\n" in texto
