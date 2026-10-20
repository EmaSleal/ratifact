"""Documentos: crear vs. modificar, zonas de escritura, rutas protegidas, búsqueda y lectura."""
import pytest

from conftest import log_git


def test_crear_y_modificar_son_herramientas_distintas(srv, proyecto):
    assert "create_document" in srv.update_document(project="demo", path="docs/nuevo.md", content="x")
    assert "(create)" in srv.create_document(project="demo", path="docs/nuevo.md", content="hola")
    assert "already exists" in srv.create_document(project="demo", path="docs/nuevo.md", content="otra vez")
    assert "(append)" in srv.update_document(project="demo", path="docs/nuevo.md", content="mundo", mode="anexar")
    assert srv.update_document(project="demo", path="docs/nuevo.md", content="z", mode="crear").startswith("ERROR:")
    assert (proyecto["repo"] / "docs" / "nuevo.md").read_text() == "hola\n\nmundo\n"
    assert log_git(proyecto["repo"])[0].startswith("memoria: anexar docs/nuevo.md")


def test_documentos_de_memoria_van_al_repo_de_memoria(srv, proyecto):
    srv.create_document(project="demo", path=".project/notas.md", content="nota")
    assert (proyecto["mem"] / "notas.md").exists()
    assert not (proyecto["repo"] / ".project").exists()
    assert log_git(proyecto["mem"])[0] == "memoria: crear .project/notas.md"


@pytest.mark.parametrize("ruta, mensaje", [
    ("../fuera.md", "outside the project"),
    ("/etc/passwd", "relative"),
    (".git/config", ".git"),
    ("src/codigo.py", "Writing is only allowed"),
    (".project/../../escape.md", "outside the project memory"),
    (".project/.git/config", "outside the project memory"),
])
def test_escrituras_bloqueadas(srv, proyecto, ruta, mensaje):
    salida = srv.create_document(project="demo", path=ruta, content="x")
    assert salida.startswith("ERROR:") and mensaje.lower() in salida.lower()


def test_lecturas_bloqueadas(srv, proyecto):
    for ruta in ("/etc/passwd", "../../x", ".git/HEAD", ".project/.git/HEAD"):
        assert srv.read_document(project="demo", path=ruta).startswith("ERROR:")


def test_solo_archivos_de_texto(srv, proyecto):
    assert "Text files only" in srv.create_document(project="demo", path="docs/a.zip", content="x")


def test_leer_con_rango(srv, proyecto):
    srv.create_document(project="demo", path="docs/l.md", content="\n".join(f"línea {i}" for i in range(1, 11)))
    assert srv.read_document(project="demo", path="docs/l.md", from_line=3, to_line=4) == "línea 3\nlínea 4"
    assert srv.read_document(project="demo", path="docs/no.md").startswith("ERROR:")


def test_buscar_en_codigo_y_memoria(srv, proyecto):
    srv.add_pending(project="demo", topic="Lobo alfa", context="Revisar")
    salida = srv.search(project="demo", query="LOBO ALFA")
    assert "docs/vision.md:2:" in salida and ".project/pending/" in salida
    assert srv.search(project="demo", query="inexistente-zzz") == "(no matches)"


def test_listar_documentos(srv, proyecto):
    assert "docs/vision.md" in srv.list_documents(project="demo")
    assert ".project/DECISIONS.md" in srv.list_documents(project="demo", folder=".project")


def test_buscar_respeta_gitignore_y_salta_dependencias(srv, proyecto):
    """Backlog punto 3: en proyectos con dependencias (node_modules, target) search no debe recorrerlas."""
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
    salida = srv.search(project="demo", query="lobo alfa")
    assert "nuevo.md" in salida and "docs/vision.md" in salida and "src/Lobo.java" in salida
    for ignorado in ("secreto.md", "build/", "node_modules"):
        assert ignorado not in salida


def test_buscar_sin_git_salta_carpetas_conocidas(srv, entorno):
    carpeta = entorno["base"] / "sin-git"
    (carpeta / "target" / "classes").mkdir(parents=True)
    (carpeta / "target" / "classes" / "a.properties").write_text("clave=lobo\n")
    (carpeta / "app.properties").write_text("clave=lobo\n")
    srv.register_project(name="sin-git", path=str(carpeta))
    salida = srv.search(project="sin-git", query="lobo")
    assert "app.properties" in salida and "target" not in salida


def test_buscar_omite_archivos_enormes(srv, proyecto):
    (proyecto["repo"] / "docs" / "enorme.md").write_text("lobo alfa\n" * 200_000)
    assert "enorme.md" not in srv.search(project="demo", query="lobo alfa", max_results=50)


def test_leer_binario_es_rechazo_no_falla_interna(srv, proyecto):
    """Regresión (Fractall): leer un .docx daba ERROR (internal) UnicodeDecodeError."""
    (proyecto["repo"] / "docs" / "correo.docx").write_bytes(b"PK\x03\x04\xf9\xff binario")
    salida = srv.read_document(project="demo", path="docs/correo.docx")
    assert salida.startswith("ERROR:") and "is not a text file" in salida
