"""Ciclo de vida de las decisiones: solo el usuario acuerda (ADR-011)."""
from conftest import log_git


def _registrar(srv, titulo="Usar Godot", **extra):
    return srv.registrar_decision(proyecto="demo", titulo=titulo, decision="Godot 4", justificacion="2D nativo", **extra)


def test_toda_decision_nace_como_propuesta(srv, proyecto):
    assert "ADR-001 registrada como proposed" in _registrar(srv)
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "decisions").glob("ADR-001*.md")))
    assert meta["status"] == "proposed"


def test_no_existe_atajo_para_acordar_al_registrar(srv, proyecto):
    import inspect
    assert "acordada" not in inspect.signature(srv.registrar_decision).parameters


def test_confirmar_exige_cita_y_la_guarda(srv, proyecto):
    _registrar(srv)
    assert srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario=" ").startswith("ERROR:")
    assert "ADR-001 → accepted" in srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="sí, confirmo")
    texto = next((proyecto["mem"] / "decisions").glob("ADR-001*.md")).read_text()
    assert "## Acceptance (" in texto and "> sí, confirmo" in texto


def test_solo_se_confirman_o_descartan_propuestas(srv, proyecto):
    _registrar(srv)
    srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="ok")
    assert "solo se confirman propuestas" in srv.confirmar_decision(proyecto="demo", id="ADR-001", cita_usuario="ok")
    assert "solo se descartan propuestas" in srv.descartar_decision(proyecto="demo", id="ADR-001", motivo="ya no")


def test_descartar_exige_motivo_y_conserva_historial(srv, proyecto):
    _registrar(srv)
    assert srv.descartar_decision(proyecto="demo", id="ADR-001", motivo="").startswith("ERROR:")
    assert "ADR-001 → rejected" in srv.descartar_decision(proyecto="demo", id="ADR-001", motivo="No aplica a la v1")
    archivo = next((proyecto["mem"] / "decisions").glob("ADR-001*.md"))
    assert archivo.exists() and "No aplica a la v1" in archivo.read_text()
    assert "## Rejected" in (proyecto["mem"] / "DECISIONS.md").read_text()


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
    acuerdos = (proyecto["mem"] / "DECISIONS.md").read_text()
    assert "ADR-001" in acuerdos.split("## Proposed")[0]       # aparece entre las accepted
    historial = log_git(proyecto["mem"])
    assert historial[0] == "memoria: ADR-001 accepted" and any("proposed" in h for h in historial)


def test_titulos_con_saltos_de_linea_no_rompen_el_registro(srv, proyecto):
    srv.registrar_decision(proyecto="demo", titulo="Título\ncon salto", decision="d", justificacion="j")
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "decisions").glob("ADR-001*.md")))
    assert meta["title"] == "Título con salto"


def test_revisar_propuestas_paginado_y_resumen(srv, proyecto):
    for i in range(1, 14):
        srv.registrar_decision(proyecto="demo", titulo=f"D{i}", decision=f"dec {i}", justificacion="j", resumen=f"r{i}")
    pagina = srv.revisar_propuestas(proyecto="demo", cantidad=5)
    assert "13 propuesta(s) por revisar; se muestran 5" in pagina and 'desde_id="ADR-006"' in pagina
    assert "# ADR-005" in pagina and "# ADR-006" not in pagina
    siguiente = srv.revisar_propuestas(proyecto="demo", desde_id="ADR-006", cantidad=25, resumen=True)
    assert "- **ADR-006** D6 — r6" in siguiente and "- **ADR-013** D13 — r13" in siguiente and "Quedan" not in siguiente


def test_confirmar_en_lote_es_todo_o_nada(srv, proyecto):
    for t in "ABC":
        _registrar(srv, titulo=t)
    srv.confirmar_decision(proyecto="demo", id="ADR-003", cita_usuario="ok")
    salida = srv.confirmar_decisiones_lote(proyecto="demo", ids=["ADR-001", "ADR-003"], cita_usuario="confirmo 1 y 3")
    assert "no se confirmó ninguna" in salida
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "decisions").glob("ADR-001*.md")))
    assert meta["status"] == "proposed"
    assert srv.confirmar_decisiones_lote(proyecto="demo", ids=["ADR-001"], cita_usuario="").startswith("ERROR:")
    salida = srv.confirmar_decisiones_lote(proyecto="demo", ids=["adr-001", "ADR-002", "ADR-001"], cita_usuario="confirmo 1 y 2")
    assert "2 → accepted (ADR-001, ADR-002)" in salida
    texto = next((proyecto["mem"] / "decisions").glob("ADR-002*.md")).read_text()
    assert ", batch)" in texto and "> confirmo 1 y 2" in texto
    assert log_git(proyecto["mem"])[0].startswith("memoria: 2 decisions accepted in batch")
