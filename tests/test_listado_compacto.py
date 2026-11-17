"""T-031 (ADR-055): list_documents lista los registros en una línea compacta `ID · status · title`, sin ruta y con el
título acotado como el de los pendientes de get_context; los archivos que no son registros y search no cambian."""
import re

CARPETAS = {"decisions": ".project/decisions", "pending": ".project/pending", "tasks": ".project/tasks"}


def _crear(srv, titulo_d="Decisión de prueba", tema="Tema de prueba", titulo_t="Tarea de prueba"):
    assert not srv.propose_decision(project="demo", title=titulo_d, decision="d", rationale="r").startswith("ERROR")
    assert not srv.add_pending(project="demo", topic=tema, context="c").startswith("ERROR")
    assert not srv.create_task(project="demo", title=titulo_t, goal="g", acceptance_criteria="- a").startswith("ERROR")


def _listar(srv, clave):
    return srv.list_documents(project="demo", folder=CARPETAS[clave]).splitlines()


def test_listado_de_registros_es_id_estado_titulo_sin_ruta(srv, proyecto):
    _crear(srv)
    esperado = {"decisions": "ADR-001 · proposed · Decisión de prueba", "pending": "P-001 · open · Tema de prueba",
                "tasks": "T-001 · todo · Tarea de prueba"}
    for clave, linea in esperado.items():
        lineas = _listar(srv, clave)
        assert lineas == [linea]
        assert all("(.project/" not in l and ".md" not in l for l in lineas)


def test_titulo_de_100_caracteres_entero_y_de_101_cortado(srv, proyecto):
    _crear(srv, titulo_t="a" * 100, tema="b" * 101)
    assert _listar(srv, "tasks") == [f"T-001 · todo · {'a' * 100}"]
    linea = _listar(srv, "pending")[0]
    assert linea == f"P-001 · open · {'b' * 99}…"
    assert len(linea.split(" · ", 2)[2]) == 100


def test_el_id_listado_se_lee_con_read_document_y_titulo_completo(srv, proyecto):
    largo = "x" * 150
    _crear(srv, titulo_t=largo)
    id_ = _listar(srv, "tasks")[0].split(" · ")[0]
    leido = srv.read_document(project="demo", path=id_)
    assert not leido.startswith("ERROR") and largo in leido


def test_archivo_que_no_es_registro_conserva_ruta_y_tamano(srv, proyecto):
    _crear(srv)
    (proyecto["mem"] / "tasks" / "notas.txt").write_text("hola")
    assert ".project/tasks/notas.txt  (4 B)" in _listar(srv, "tasks")


def test_search_conserva_ruta_y_titulo_completo(srv, proyecto):
    largo = "zorro " + "y" * 150
    _crear(srv, titulo_t=largo)
    lineas = [l for l in srv.search(project="demo", query="zorro").splitlines() if l.startswith("T-001")]
    assert len(lineas) == 1 and re.fullmatch(rf"T-001 · todo · {largo} \(\.project/tasks/T-001-.*\.md\)", lineas[0])


def test_contexto_pendientes_abiertos_sin_cambios(srv, proyecto):
    _crear(srv, tema="b" * 101)
    srv.add_pending(project="demo", topic="c" * 100, context="c")
    ctx = srv.get_context(project="demo")
    assert f"- P-001 · {'b' * 99}… (" in ctx and f"- P-002 · {'c' * 100} (" in ctx
