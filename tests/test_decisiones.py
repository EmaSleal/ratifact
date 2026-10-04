"""Ciclo de vida de las decisiones: solo el usuario acuerda (ADR-011)."""
from conftest import log_git


def _registrar(srv, titulo="Usar Godot", **extra):
    return srv.registrar_decision(proyecto="demo", titulo=titulo, decision="Godot 4", justificacion="2D nativo", **extra)


def test_toda_decision_nace_como_propuesta(srv, proyecto):
    assert "ADR-001 registrada como propuesta" in _registrar(srv)
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "decisiones").glob("ADR-001*.md")))
    assert meta["estado"] == "propuesta"


def test_no_existe_atajo_para_acordar_al_registrar(srv, proyecto):
    import inspect
    assert "acordada" not in inspect.signature(srv.registrar_decision).parameters


def test_confirmar_exige_cita_y_la_guarda(srv, proyecto):
    _registrar(srv)
    assert srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario=" ").startswith("ERROR:")
    assert "acordada" in srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="sí, confirmo")
    texto = next((proyecto["mem"] / "decisiones").glob("ADR-001*.md")).read_text()
    assert "## Confirmación" in texto and "> sí, confirmo" in texto


def test_solo_se_confirman_o_descartan_propuestas(srv, proyecto):
    _registrar(srv)
    srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="ok")
    assert "solo se confirman propuestas" in srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="ok")
    assert "solo se descartan propuestas" in srv.descartar_decision(proyecto="demo", id="ADR-001", motivo="ya no")


def test_descartar_exige_motivo_y_conserva_historial(srv, proyecto):
    _registrar(srv)
    assert srv.descartar_decision(proyecto="demo", id="ADR-001", motivo="").startswith("ERROR:")
    assert "descartada" in srv.descartar_decision(proyecto="demo", id="ADR-001", motivo="No aplica a la v1")
    archivo = next((proyecto["mem"] / "decisiones").glob("ADR-001*.md"))
    assert archivo.exists() and "No aplica a la v1" in archivo.read_text()
    assert "## Descartadas" in (proyecto["mem"] / "acuerdos.md").read_text()


def test_reemplazar_marca_la_anterior(srv, proyecto):
    _registrar(srv, titulo="A")
    _registrar(srv, titulo="B")
    assert "reemplazada por ADR-002" in srv.reemplazar_decision(proyecto="demo", id_anterior="ADR-001", id_nuevo="ADR-002")
    assert srv.reemplazar_decision(proyecto="demo", id_anterior="ADR-001", id_nuevo="ADR-099").startswith("ERROR:")


def test_revisar_propuestas_muestra_solo_pendientes(srv, proyecto):
    assert srv.revisar_propuestas(proyecto="demo") == "(no hay propuestas pendientes)"
    _registrar(srv, titulo="A")
    _registrar(srv, titulo="B")
    srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="ok")
    salida = srv.revisar_propuestas(proyecto="demo")
    assert "1 propuesta(s)" in salida and "ADR-002" in salida and "ADR-001 —" not in salida


def test_vistas_se_regeneran_y_cada_cambio_se_commitea(srv, proyecto):
    _registrar(srv)
    srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="ok")
    acuerdos = (proyecto["mem"] / "acuerdos.md").read_text()
    assert "ADR-001" in acuerdos.split("## Propuestas")[0]       # aparece entre las acordadas
    historial = log_git(proyecto["mem"])
    assert historial[0] == "memoria: ADR-001 acordada" and any("propuesta" in h for h in historial)


def test_titulos_con_saltos_de_linea_no_rompen_el_registro(srv, proyecto):
    srv.registrar_decision(proyecto="demo", titulo="Título\ncon salto", decision="d", justificacion="j")
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "decisiones").glob("ADR-001*.md")))
    assert meta["titulo"] == "Título con salto"
