"""Documentos: crear vs. modificar, zonas de escritura, rutas protegidas, búsqueda y lectura."""
import pytest

from conftest import log_git


def test_crear_y_modificar_son_herramientas_distintas(srv, proyecto):
    assert "crear_documento" in srv.guardar_documento(proyecto="demo", ruta="docs/nuevo.md", contenido="x")
    assert "(crear)" in srv.crear_documento(proyecto="demo", ruta="docs/nuevo.md", contenido="hola")
    assert "ya existe" in srv.crear_documento(proyecto="demo", ruta="docs/nuevo.md", contenido="otra vez")
    assert "(anexar)" in srv.guardar_documento(proyecto="demo", ruta="docs/nuevo.md", contenido="mundo", modo="anexar")
    assert srv.guardar_documento(proyecto="demo", ruta="docs/nuevo.md", contenido="z", modo="crear").startswith("ERROR:")
    assert (proyecto["repo"] / "docs" / "nuevo.md").read_text() == "hola\n\nmundo\n"
    assert log_git(proyecto["repo"])[0].startswith("memoria: anexar docs/nuevo.md")


def test_documentos_de_memoria_van_al_repo_de_memoria(srv, proyecto):
    srv.crear_documento(proyecto="demo", ruta=".project/notas.md", contenido="nota")
    assert (proyecto["mem"] / "notas.md").exists()
    assert not (proyecto["repo"] / ".project").exists()
    assert log_git(proyecto["mem"])[0] == "memoria: crear .project/notas.md"


@pytest.mark.parametrize("ruta, mensaje", [
    ("../fuera.md", "fuera del proyecto"),
    ("/etc/passwd", "relativa"),
    (".git/config", ".git"),
    ("src/codigo.py", "Escritura solo permitida"),
    (".project/../../escape.md", "fuera de la memoria"),
    (".project/.git/config", "fuera de la memoria"),
])
def test_escrituras_bloqueadas(srv, proyecto, ruta, mensaje):
    salida = srv.crear_documento(proyecto="demo", ruta=ruta, contenido="x")
    assert salida.startswith("ERROR:") and mensaje.lower() in salida.lower()


def test_lecturas_bloqueadas(srv, proyecto):
    for ruta in ("/etc/passwd", "../../x", ".git/HEAD", ".project/.git/HEAD"):
        assert srv.leer_documento(proyecto="demo", ruta=ruta).startswith("ERROR:")


def test_solo_archivos_de_texto(srv, proyecto):
    assert "Solo archivos de texto" in srv.crear_documento(proyecto="demo", ruta="docs/a.zip", contenido="x")


def test_leer_con_rango(srv, proyecto):
    srv.crear_documento(proyecto="demo", ruta="docs/l.md", contenido="\n".join(f"línea {i}" for i in range(1, 11)))
    assert srv.leer_documento(proyecto="demo", ruta="docs/l.md", desde_linea=3, hasta_linea=4) == "línea 3\nlínea 4"
    assert srv.leer_documento(proyecto="demo", ruta="docs/no.md").startswith("ERROR:")


def test_buscar_en_codigo_y_memoria(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Lobo alfa", contexto="Revisar")
    salida = srv.buscar(proyecto="demo", texto="LOBO ALFA")
    assert "docs/vision.md:2:" in salida and ".project/pendientes/" in salida
    assert srv.buscar(proyecto="demo", texto="inexistente-zzz") == "(sin coincidencias)"


def test_listar_documentos(srv, proyecto):
    assert "docs/vision.md" in srv.listar_documentos(proyecto="demo")
    assert ".project/acuerdos.md" in srv.listar_documentos(proyecto="demo", carpeta=".project")


def test_buscar_respeta_gitignore_y_salta_dependencias(srv, proyecto):
    """Backlog punto 3: en proyectos con dependencias (node_modules, target) buscar no debe recorrerlas."""
    repo = proyecto["repo"]
    (repo / ".gitignore").write_text("secreto.md\nbuild/\n")
    (repo / "secreto.md").write_text("lobo alfa ignorado\n")
    (repo / "build").mkdir()
    (repo / "build" / "salida.md").write_text("lobo alfa compilado\n")
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "index.js").write_text("// lobo alfa dependencia\n")
    (repo / "nuevo.md").write_text("lobo alfa sin commitear\n")          # nuevo y no ignorado: sí se busca
    (repo / "src").mkdir()
    (repo / "src" / "Lobo.java").write_text("class LoboAlfa {}  // lobo alfa en Java\n")
    salida = srv.buscar(proyecto="demo", texto="lobo alfa")
    assert "nuevo.md" in salida and "docs/vision.md" in salida and "src/Lobo.java" in salida
    for ignorado in ("secreto.md", "build/", "node_modules"):
        assert ignorado not in salida


def test_buscar_sin_git_salta_carpetas_conocidas(srv, entorno):
    carpeta = entorno["base"] / "sin-git"
    (carpeta / "target" / "classes").mkdir(parents=True)
    (carpeta / "target" / "classes" / "a.properties").write_text("clave=lobo\n")
    (carpeta / "app.properties").write_text("clave=lobo\n")
    srv.registrar_proyecto(nombre="sin-git", ruta=str(carpeta))
    salida = srv.buscar(proyecto="sin-git", texto="lobo")
    assert "app.properties" in salida and "target" not in salida


def test_buscar_omite_archivos_enormes(srv, proyecto):
    (proyecto["repo"] / "docs" / "enorme.md").write_text("lobo alfa\n" * 200_000)
    assert "enorme.md" not in srv.buscar(proyecto="demo", texto="lobo alfa", max_resultados=50)


def test_leer_binario_es_rechazo_no_falla_interna(srv, proyecto):
    """Regresión (Fractall): leer un .docx daba ERROR INTERNO UnicodeDecodeError."""
    (proyecto["repo"] / "docs" / "correo.docx").write_bytes(b"PK\x03\x04\xf9\xff binario")
    salida = srv.leer_documento(proyecto="demo", ruta="docs/correo.docx")
    assert salida.startswith("ERROR:") and "no es un archivo de texto" in salida
