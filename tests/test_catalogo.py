"""T-007 / ADR-022: catálogo de la memoria derivado en cada llamada (sin índice, caché ni watcher). Alimenta la
resolución de ids en read_document, el listado de registros en list_documents y los resultados por id/título
de search. Incluye el arreglo de create_task con `repositorio` en proyectos de un solo repositorio."""
import pytest

from conftest import log_git
from ratifact import catalogo

ADR_020 = "ADR-020-objectmapper-de-spring-boot-y-errores-http-unificados.md"


def _registro(carpeta, nombre: str, meta: dict, cuerpo: str):
    carpeta.mkdir(parents=True, exist_ok=True)
    cabecera = "\n".join(f"{k}: {v}" for k, v in meta.items())
    (carpeta / nombre).write_text(f"---\n{cabecera}\n---\n{cuerpo}\n", encoding="utf-8")
    return carpeta / nombre


@pytest.fixture
def memoria(proyecto):
    """Registros como los de los logs reales: T-001, T-010, T-024, T-1000; P-008, P-042; ADR-020 (slug largo), ADR-024."""
    mem = proyecto["mem"]
    for n, titulo, estado in ((1, "Primera tarea", "merged"), (10, "Décima tarea", "in_review"),
                              (24, "Navegación por id", "todo"), (1000, "Tarea mil", "todo")):
        id_ = f"T-{n:03d}"
        _registro(mem / "tasks", f"{id_}-{titulo.lower().replace(' ', '-')}.md",
                  {"id": id_, "title": titulo, "status": estado}, f"# {id_} — {titulo}\nlínea 2 de {id_}\nlínea 3 de {id_}")
    for n in (8, 42):
        id_ = f"P-{n:03d}"
        _registro(mem / "pending", f"{id_}-tema-{n}.md", {"id": id_, "topic": f"Tema {n}", "status": "open"},
                  f"Cuerpo de {id_}")
    _registro(mem / "decisions", ADR_020, {"id": "ADR-020", "title": "ObjectMapper de Spring Boot", "status": "accepted"},
              "Cuerpo de ADR-020")
    _registro(mem / "decisions", "ADR-024-integraciones-opcionales.md",
              {"id": "ADR-024", "title": "Integraciones opcionales", "status": "proposed"}, "Cuerpo de ADR-024")
    return mem


def _archivos(carpeta):
    return sorted((p.relative_to(carpeta), p.stat().st_mtime_ns) for p in carpeta.rglob("*") if p.is_file())


# ───────────────────────── criterio 1: catálogo ─────────────────────────

def test_catalogo_lee_el_frontmatter_en_cada_llamada_sin_escribir(srv, memoria):
    antes = _archivos(memoria)
    filas = catalogo._catalogo("demo")
    assert _archivos(memoria) == antes                                   # nada escrito en disco
    por_id = {r.id: r for r in filas}
    assert por_id["T-024"] == ("T-024", "task", "Navegación por id", "todo",
                               ".project/tasks/T-024-navegación-por-id.md", "")   # sin `date` en el frontmatter
    assert por_id["P-008"].titulo == "Tema 8" and por_id["P-008"].tipo == "pending"
    assert por_id["ADR-020"].ruta == f".project/decisions/{ADR_020}" and por_id["ADR-020"].estado == "accepted"
    assert [r.id for r in filas if r.tipo == "task"] == ["T-001", "T-010", "T-024", "T-1000"]
    _registro(memoria / "tasks", "T-025-nueva.md", {"id": "T-25", "title": "Nueva", "status": "todo"}, "x")
    assert "T-025" in {r.id for r in catalogo._catalogo("demo")}            # sin caché: el cambio se ve enseguida


# ───────────────────────── criterio 2: read_document resuelve ids ─────────────────────────

@pytest.mark.parametrize("ruta", ["T-24", "T-024", "T-024.md", "tasks/T-024.md", ".project/tasks/T-024.md", "t-24",
                                  "tareas/T-024.md", ".project/tareas/T-024.md"])     # también con la carpeta v1
def test_leer_documento_resuelve_formas_de_id(srv, memoria, ruta):
    real = memoria / "tasks" / "T-024-navegación-por-id.md"
    salida = srv.read_document(project="demo", path=ruta)
    assert salida == "(→ .project/tasks/T-024-navegación-por-id.md)\n" + real.read_text().rstrip("\n"), salida


@pytest.mark.parametrize("ruta,real,cuerpo", [
    ("pendientes/P-8.md", "pending/P-008-tema-8.md", "Cuerpo de P-008"),       # rutas v1 de los logs
    ("pendientes/P-042.md", "pending/P-042-tema-42.md", "Cuerpo de P-042"),
    (".project/tareas/T-001.md", "tasks/T-001-primera-tarea.md", "# T-001 — Primera tarea"),
    ("tareas/T-010.md", "tasks/T-010-décima-tarea.md", "# T-010 — Décima tarea"),
    (".project/decisiones/ADR-020-objectmapper-de-spring-boot-y-errores-ht.md", f"decisions/{ADR_020}", "Cuerpo de ADR-020"),
    ("pending/P-8.md", "pending/P-008-tema-8.md", "Cuerpo de P-008"),             # y sus equivalentes v2
    (".project/decisions/ADR-020-slug-equivocado.md", f"decisions/{ADR_020}", "Cuerpo de ADR-020"),
])
def test_leer_documento_resuelve_rutas_reales_de_los_logs(srv, memoria, ruta, real, cuerpo):
    salida = srv.read_document(project="demo", path=ruta)
    assert salida == f"(→ .project/{real})\n" + (memoria / real).read_text().rstrip("\n"), salida
    assert cuerpo in salida


def test_rango_se_aplica_al_archivo_resuelto(srv, memoria):
    # líneas 1-5: frontmatter; 6: título; 7: "línea 2 de T-024"
    assert srv.read_document(project="demo", path="T-24", from_line=7, to_line=7) == \
        "(→ .project/tasks/T-024-navegación-por-id.md)\nlínea 2 de T-024"


# ───────────────────────── criterio 3: rutas exactas sin cambios ─────────────────────────

def test_ruta_exacta_se_lee_igual_que_antes(srv, memoria, proyecto):
    real = memoria / "tasks" / "T-024-navegación-por-id.md"
    assert srv.read_document(project="demo", path=".project/tasks/T-024-navegación-por-id.md") == \
        real.read_text().rstrip("\n")
    assert srv.read_document(project="demo", path="docs/vision.md") == "# Visión\nUn lobo alfa lidera la manada."
    (proyecto["repo"] / "T-001.md").write_text("archivo del código\n")      # existe tal cual: no se resuelve
    assert srv.read_document(project="demo", path="T-001.md") == "archivo del código"


# ───────────────────────── criterio 4: id inexistente ─────────────────────────

def test_id_inexistente_nombra_el_ultimo_de_su_tipo(srv, memoria):
    assert srv.read_document(project="demo", path="ADR-099") == "ERROR: ADR-099 does not exist; the latest is ADR-024."
    assert srv.read_document(project="demo", path="tareas/T-2000.md") == "ERROR: T-2000 does not exist; the latest is T-1000."


def test_id_inexistente_con_carpeta_vacia(srv, proyecto):
    salida = srv.read_document(project="demo", path="T-005")
    assert salida == "ERROR: T-005 does not exist; there are no records in .project/tasks yet.", salida


def test_sin_forma_de_id_sigue_el_mensaje_de_siempre(srv, memoria):
    assert srv.read_document(project="demo", path="docs/no.md") == "ERROR: docs/no.md does not exist."
    assert srv.read_document(project="demo", path="X-001") == "ERROR: X-001 does not exist."


# ───────────────────────── criterio 5: carpeta ─────────────────────────

def test_leer_una_carpeta_apunta_a_listar_documentos(srv, memoria):
    salida = srv.read_document(project="demo", path=".project/tasks")
    assert salida.startswith("ERROR:") and "is a folder" in salida and "list_documents" in salida, salida


# ───────────────────────── criterio 6: solo lectura y dentro de la memoria ─────────────────────────

def test_escrituras_no_resuelven_ids(srv, memoria):
    real = memoria / "tasks" / "T-024-navegación-por-id.md"
    original = real.read_text()
    assert srv.update_document(project="demo", path="T-024", content="x") == \
        "ERROR: Writing is only allowed in: .project, docs"
    assert srv.update_document(project="demo", path=".project/tasks/T-024.md", content="x") == \
        "ERROR: .project/tasks/T-024.md does not exist; to create it use create_document."
    assert real.read_text() == original


def test_resolucion_no_sale_de_la_memoria(srv, memoria, proyecto):
    commits = log_git(memoria)
    assert srv.read_document(project="demo", path="docs/T-001.md") == "ERROR: docs/T-001.md does not exist."
    assert srv.read_document(project="demo", path="../T-001").startswith("ERROR: Path outside the project")
    assert srv.read_document(project="demo", path=".project/../../T-001").startswith("ERROR: Path outside")
    assert log_git(memoria) == commits


# ───────────────────────── criterio 7: list_documents de registros ─────────────────────────

def test_listar_carpeta_de_registros_por_id(srv, memoria):
    assert srv.list_documents(project="demo", folder=".project/tasks").splitlines() == [
        "T-001 · merged · Primera tarea  (.project/tasks/T-001-primera-tarea.md)",
        "T-010 · in_review · Décima tarea  (.project/tasks/T-010-décima-tarea.md)",
        "T-024 · todo · Navegación por id  (.project/tasks/T-024-navegación-por-id.md)",
        "T-1000 · todo · Tarea mil  (.project/tasks/T-1000-tarea-mil.md)",
    ]
    assert srv.list_documents(project="demo", folder=".project/pending/").splitlines()[0] == \
        "P-008 · open · Tema 8  (.project/pending/P-008-tema-8.md)"
    assert "ADR-020 · accepted · ObjectMapper de Spring Boot" in srv.list_documents(project="demo",
                                                                                        folder=".project/decisions")


def test_listar_otros_archivos_de_memoria_sin_cambios(srv, memoria):
    tam = (memoria / "DECISIONS.md").stat().st_size
    assert f".project/DECISIONS.md  ({tam} B)" in srv.list_documents(project="demo", folder=".project").splitlines()


# ───────────────────────── criterio 8: search ─────────────────────────

def test_buscar_un_id_devuelve_el_registro_primero(srv, memoria, proyecto):
    (proyecto["repo"] / "docs" / "notas.md").write_text("Ver T-1 y T-10 en el código\n")
    salida = srv.search(project="demo", query="T-1").splitlines()
    assert salida[0] == "T-001 · merged · Primera tarea (.project/tasks/T-001-primera-tarea.md)", salida
    assert "docs/notas.md:1: Ver T-1 y T-10 en el código" in salida


def test_buscar_por_titulo_devuelve_el_registro_primero(srv, memoria):
    salida = srv.search(project="demo", query="objectmapper").splitlines()
    assert salida[0] == f"ADR-020 · accepted · ObjectMapper de Spring Boot (.project/decisions/{ADR_020})", salida


def test_coincidencias_de_memoria_antes_que_las_del_codigo(srv, memoria, proyecto):
    (proyecto["repo"] / "docs" / "ruido.md").write_text("\n".join("zorro gris" for _ in range(50)) + "\n")
    (memoria / "notas.md").write_text("Un zorro gris en la memoria\n")
    salida = srv.search(project="demo", query="zorro gris", max_results=5).splitlines()
    assert salida[0] == ".project/notas.md:1: Un zorro gris en la memoria", salida
    assert len(salida) == 6 and salida[-1].startswith("(… more results")


# ───────────────────────── criterio 10: create_task en un solo repositorio ─────────────────────────

def test_un_solo_repo_ignora_repositorio(srv, proyecto):
    salida = srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", repo="x")
    assert salida.startswith("T-001 created") and "(single-repo project: `repo` was ignored)" in salida
    tarea = next((proyecto["mem"] / "tasks").glob("T-001*.md")).read_text()
    assert "repo:" not in tarea.split("---")[1]
