"""Pendientes, tareas para el agente de código, sesiones, índice y contexto inicial."""
from conftest import log_git


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


def _tarea_en_revision(srv):
    srv.registrar_tarea(proyecto="demo", titulo="Tope NC", objetivo="o", criterios_aceptacion="1. c")
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="en_curso")
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="en_revision", resultado="652 verdes", commit="c4eae6a")


def test_devolver_tarea_deja_revision_estructurada(srv, proyecto):
    """Hallazgo Fractall T-001: devolver con 'pendiente' confundía al agente (rama con commit + tarea 'pendiente')."""
    _tarea_en_revision(srv)
    assert srv.devolver_tarea(proyecto="demo", id="T-001", observaciones=" ").startswith("ERROR:")
    salida = srv.devolver_tarea(proyecto="demo", id="T-001", observaciones="Criterio 3 falla: fuga de tenant",
                                criterios_adicionales="6. 409 con mensaje fijo")
    assert "T-001 devuelta (revisión 1)" in salida and "/tarea T-001" in salida
    ruta = next((proyecto["mem"] / "tareas").glob("T-001*.md"))
    meta, cuerpo = srv._leer_registro(ruta)
    assert meta["estado"] == "devuelta" and meta["revisiones"] == "1"
    assert "### Revisión 1" in cuerpo and "MISMA rama `t-001-tope-nc`" in cuerpo and "commit c4eae6a" in cuerpo
    assert "**Criterios adicionales**\n6. 409 con mensaje fijo" in cuerpo
    assert cuerpo.index("652 verdes") < cuerpo.index("### Revisión 1")      # historial en orden
    assert "[devuelta] Tope NC" in srv.listar_tareas(proyecto="demo")
    assert log_git(proyecto["mem"])[0] == "memoria: T-001 devuelta (revisión 1)"
    # segunda vuelta: el agente corrige y vuelve a revisión; una nueva devolución numera la revisión 2
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="en_curso")
    assert srv.devolver_tarea(proyecto="demo", id="T-001", observaciones="x").startswith("ERROR:")   # aún en curso
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="en_revision", resultado="corregido")
    assert "revisión 2" in srv.devolver_tarea(proyecto="demo", id="T-001", observaciones="falta javadoc")


def test_no_se_devuelve_por_atajos(srv, proyecto):
    _tarea_en_revision(srv)
    assert "devolver_tarea" in srv.actualizar_tarea(proyecto="demo", id="T-001", estado="pendiente")
    assert "devolver_tarea" in srv.actualizar_tarea(proyecto="demo", id="T-001", estado="devuelta")
    meta, _ = srv._leer_registro(next((proyecto["mem"] / "tareas").glob("T-001*.md")))
    assert meta["estado"] == "en_revision"
