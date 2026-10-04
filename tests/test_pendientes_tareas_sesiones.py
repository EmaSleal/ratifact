"""Pendientes, tareas para el agente de código, sesiones, índice y contexto inicial."""


def test_pendiente_abrir_y_cerrar(srv, proyecto):
    assert "P-001 registrado" in srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="Sin decidir", dueno="Emanuel")
    abiertas = (proyecto["mem"] / "abiertas.md").read_text()
    assert "P-001" in abiertas and "dueño: Emanuel" in abiertas
    assert "cerrado" in srv.cerrar_pendiente(proyecto="demo", id="P-001", resolucion="Fuera del prototipo", id_decision="ADR-003")
    abiertas = (proyecto["mem"] / "abiertas.md").read_text()
    assert "- (ninguna)" in abiertas.split("## Cerradas")[0] and "P-001 Parry (cerrado" in abiertas


def test_cerradas_recientes_se_limitan_y_no_inflan_el_contexto(srv, proyecto):
    for i in range(7):
        srv.registrar_pendiente(proyecto="demo", tema=f"T{i}", contexto="c")
        srv.cerrar_pendiente(proyecto="demo", id=f"P-00{i + 1}", resolucion="x" * 500)
    cerradas = (proyecto["mem"] / "abiertas.md").read_text().split("## Cerradas recientemente")[1]
    assert cerradas.count("\n- P-") == 5 and "xxxx" not in cerradas


def test_ciclo_de_una_tarea(srv, proyecto):
    salida = srv.registrar_tarea(proyecto="demo", titulo="Ranuras de forma", objetivo="Dos ranuras",
                                 criterios_aceptacion="- pruebas verdes", decisiones="ADR-001", fuera_de_alcance="Golem")
    assert "T-001 registrada" in salida and "/tarea T-001" in salida
    assert srv.actualizar_tarea(proyecto="demo", id="T-001", estado="inventado").startswith("ERROR:")
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="en_curso")
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="en_revision", resultado="740/740 verdes", commit="abc123")
    texto = next((proyecto["mem"] / "tareas").glob("T-001*.md")).read_text()
    assert "estado: en_revision" in texto and "740/740 verdes" in texto and "commit: abc123" in texto
    assert "[en_revision] Ranuras de forma" in srv.listar_tareas(proyecto="demo")
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="integrada")
    assert srv.listar_tareas(proyecto="demo") == "(sin tareas)"
    assert "integrada" in srv.listar_tareas(proyecto="demo", incluir_cerradas=True)


def test_sesion_e_indice(srv, proyecto):
    assert "Sesión registrada" in srv.registrar_sesion(proyecto="demo", resumen="Se decidió X")
    assert "Se decidió X" in next((proyecto["mem"] / "sesiones").glob("*.md")).read_text()
    assert srv.actualizar_indice(proyecto="demo", contenido="x" * 7000).startswith("ERROR:")
    assert "actualizado" in srv.actualizar_indice(proyecto="demo", contenido="# Demo\nEstado: fase A")


def test_contexto_incluye_indice_abiertas_propuestas_y_tareas(srv, proyecto):
    srv.actualizar_indice(proyecto="demo", contenido="# Demo\nEstado: fase A")
    srv.registrar_decision(proyecto="demo", titulo="X", decision="d", justificacion="j")
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c")
    ctx = srv.obtener_contexto(proyecto="demo")
    assert "Estado: fase A" in ctx and "Decisiones abiertas" in ctx
    assert "pendientes de confirmar por el usuario: ADR-001" in ctx and "T-001" in ctx


def test_aviso_de_indice_desactualizado(srv, proyecto):
    srv.actualizar_indice(proyecto="demo", contenido="# Demo")
    assert "desactualizado" not in srv.obtener_contexto(proyecto="demo")
    for i in range(srv.UMBRAL_INDICE):
        srv.registrar_pendiente(proyecto="demo", tema=f"T{i}", contexto="c")
    assert "INDEX.md está desactualizado" in srv.obtener_contexto(proyecto="demo")
    srv.actualizar_indice(proyecto="demo", contenido="# Demo al día")
    assert "desactualizado" not in srv.obtener_contexto(proyecto="demo")
