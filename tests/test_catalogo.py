"""T-007 / ADR-022: catálogo de la memoria derivado en cada llamada (sin índice, caché ni watcher). Alimenta la
resolución de ids en leer_documento, el listado de registros en listar_documentos y los resultados por id/título
de buscar. Incluye el arreglo de registrar_tarea con `repositorio` en proyectos de un solo repositorio."""
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
    for n, titulo, estado in ((1, "Primera tarea", "integrada"), (10, "Décima tarea", "en_revision"),
                              (24, "Navegación por id", "pendiente"), (1000, "Tarea mil", "pendiente")):
        id_ = f"T-{n:03d}"
        _registro(mem / "tareas", f"{id_}-{titulo.lower().replace(' ', '-')}.md",
                  {"id": id_, "titulo": titulo, "estado": estado}, f"# {id_} — {titulo}\nlínea 2 de {id_}\nlínea 3 de {id_}")
    for n in (8, 42):
        id_ = f"P-{n:03d}"
        _registro(mem / "pendientes", f"{id_}-tema-{n}.md", {"id": id_, "tema": f"Tema {n}", "estado": "abierta"},
                  f"Cuerpo de {id_}")
    _registro(mem / "decisiones", ADR_020, {"id": "ADR-020", "titulo": "ObjectMapper de Spring Boot", "estado": "acordada"},
              "Cuerpo de ADR-020")
    _registro(mem / "decisiones", "ADR-024-integraciones-opcionales.md",
              {"id": "ADR-024", "titulo": "Integraciones opcionales", "estado": "propuesta"}, "Cuerpo de ADR-024")
    return mem


def _archivos(carpeta):
    return sorted((p.relative_to(carpeta), p.stat().st_mtime_ns) for p in carpeta.rglob("*") if p.is_file())


# ───────────────────────── criterio 1: catálogo ─────────────────────────

def test_catalogo_lee_el_frontmatter_en_cada_llamada_sin_escribir(srv, memoria):
    antes = _archivos(memoria)
    filas = catalogo._catalogo("demo")
    assert _archivos(memoria) == antes                                   # nada escrito en disco
    por_id = {r.id: r for r in filas}
    assert por_id["T-024"] == ("T-024", "tarea", "Navegación por id", "pendiente",
                               ".project/tareas/T-024-navegación-por-id.md", "")   # sin `fecha` en el frontmatter
    assert por_id["P-008"].titulo == "Tema 8" and por_id["P-008"].tipo == "pendiente"
    assert por_id["ADR-020"].ruta == f".project/decisiones/{ADR_020}" and por_id["ADR-020"].estado == "acordada"
    assert [r.id for r in filas if r.tipo == "tarea"] == ["T-001", "T-010", "T-024", "T-1000"]
    _registro(memoria / "tareas", "T-025-nueva.md", {"id": "T-25", "titulo": "Nueva", "estado": "pendiente"}, "x")
    assert "T-025" in {r.id for r in catalogo._catalogo("demo")}            # sin caché: el cambio se ve enseguida


# ───────────────────────── criterio 2: leer_documento resuelve ids ─────────────────────────

@pytest.mark.parametrize("ruta", ["T-24", "T-024", "T-024.md", "tareas/T-024.md", ".project/tareas/T-024.md", "t-24"])
def test_leer_documento_resuelve_formas_de_id(srv, memoria, ruta):
    real = memoria / "tareas" / "T-024-navegación-por-id.md"
    salida = srv.leer_documento(proyecto="demo", ruta=ruta)
    assert salida == "(→ .project/tareas/T-024-navegación-por-id.md)\n" + real.read_text().rstrip("\n"), salida


@pytest.mark.parametrize("ruta,real,cuerpo", [
    ("pendientes/P-8.md", "pendientes/P-008-tema-8.md", "Cuerpo de P-008"),
    ("pendientes/P-042.md", "pendientes/P-042-tema-42.md", "Cuerpo de P-042"),
    (".project/tareas/T-001.md", "tareas/T-001-primera-tarea.md", "# T-001 — Primera tarea"),
    ("tareas/T-010.md", "tareas/T-010-décima-tarea.md", "# T-010 — Décima tarea"),
    (".project/decisiones/ADR-020-objectmapper-de-spring-boot-y-errores-ht.md", f"decisiones/{ADR_020}", "Cuerpo de ADR-020"),
])
def test_leer_documento_resuelve_rutas_reales_de_los_logs(srv, memoria, ruta, real, cuerpo):
    salida = srv.leer_documento(proyecto="demo", ruta=ruta)
    assert salida == f"(→ .project/{real})\n" + (memoria / real).read_text().rstrip("\n"), salida
    assert cuerpo in salida


def test_rango_se_aplica_al_archivo_resuelto(srv, memoria):
    # líneas 1-5: frontmatter; 6: título; 7: "línea 2 de T-024"
    assert srv.leer_documento(proyecto="demo", ruta="T-24", desde_linea=7, hasta_linea=7) == \
        "(→ .project/tareas/T-024-navegación-por-id.md)\nlínea 2 de T-024"


# ───────────────────────── criterio 3: rutas exactas sin cambios ─────────────────────────

def test_ruta_exacta_se_lee_igual_que_antes(srv, memoria, proyecto):
    real = memoria / "tareas" / "T-024-navegación-por-id.md"
    assert srv.leer_documento(proyecto="demo", ruta=".project/tareas/T-024-navegación-por-id.md") == \
        real.read_text().rstrip("\n")
    assert srv.leer_documento(proyecto="demo", ruta="docs/vision.md") == "# Visión\nUn lobo alfa lidera la manada."
    (proyecto["repo"] / "T-001.md").write_text("archivo del código\n")      # existe tal cual: no se resuelve
    assert srv.leer_documento(proyecto="demo", ruta="T-001.md") == "archivo del código"


# ───────────────────────── criterio 4: id inexistente ─────────────────────────

def test_id_inexistente_nombra_el_ultimo_de_su_tipo(srv, memoria):
    assert srv.leer_documento(proyecto="demo", ruta="ADR-099") == "ERROR: No existe ADR-099; el último es ADR-024."
    assert srv.leer_documento(proyecto="demo", ruta="tareas/T-2000.md") == "ERROR: No existe T-2000; el último es T-1000."


def test_id_inexistente_con_carpeta_vacia(srv, proyecto):
    salida = srv.leer_documento(proyecto="demo", ruta="T-005")
    assert salida == "ERROR: No existe T-005; todavía no hay registros en .project/tareas.", salida


def test_sin_forma_de_id_sigue_el_mensaje_de_siempre(srv, memoria):
    assert srv.leer_documento(proyecto="demo", ruta="docs/no.md") == "ERROR: No existe docs/no.md."
    assert srv.leer_documento(proyecto="demo", ruta="X-001") == "ERROR: No existe X-001."


# ───────────────────────── criterio 5: carpeta ─────────────────────────

def test_leer_una_carpeta_apunta_a_listar_documentos(srv, memoria):
    salida = srv.leer_documento(proyecto="demo", ruta=".project/tareas")
    assert salida.startswith("ERROR:") and "es una carpeta" in salida and "listar_documentos" in salida, salida


# ───────────────────────── criterio 6: solo lectura y dentro de la memoria ─────────────────────────

def test_escrituras_no_resuelven_ids(srv, memoria):
    real = memoria / "tareas" / "T-024-navegación-por-id.md"
    original = real.read_text()
    assert srv.guardar_documento(proyecto="demo", ruta="T-024", contenido="x") == \
        "ERROR: Escritura solo permitida en: .project, docs"
    assert srv.guardar_documento(proyecto="demo", ruta=".project/tareas/T-024.md", contenido="x") == \
        "ERROR: .project/tareas/T-024.md no existe; para crearlo usa crear_documento."
    assert real.read_text() == original


def test_resolucion_no_sale_de_la_memoria(srv, memoria, proyecto):
    commits = log_git(memoria)
    assert srv.leer_documento(proyecto="demo", ruta="docs/T-001.md") == "ERROR: No existe docs/T-001.md."
    assert srv.leer_documento(proyecto="demo", ruta="../T-001").startswith("ERROR: Ruta fuera del proyecto")
    assert srv.leer_documento(proyecto="demo", ruta=".project/../../T-001").startswith("ERROR: Ruta fuera")
    assert log_git(memoria) == commits


# ───────────────────────── criterio 7: listar_documentos de registros ─────────────────────────

def test_listar_carpeta_de_registros_por_id(srv, memoria):
    assert srv.listar_documentos(proyecto="demo", carpeta=".project/tareas").splitlines() == [
        "T-001 · integrada · Primera tarea  (.project/tareas/T-001-primera-tarea.md)",
        "T-010 · en_revision · Décima tarea  (.project/tareas/T-010-décima-tarea.md)",
        "T-024 · pendiente · Navegación por id  (.project/tareas/T-024-navegación-por-id.md)",
        "T-1000 · pendiente · Tarea mil  (.project/tareas/T-1000-tarea-mil.md)",
    ]
    assert srv.listar_documentos(proyecto="demo", carpeta=".project/pendientes/").splitlines()[0] == \
        "P-008 · abierta · Tema 8  (.project/pendientes/P-008-tema-8.md)"
    assert "ADR-020 · acordada · ObjectMapper de Spring Boot" in srv.listar_documentos(proyecto="demo",
                                                                                        carpeta=".project/decisiones")


def test_listar_otros_archivos_de_memoria_sin_cambios(srv, memoria):
    tam = (memoria / "acuerdos.md").stat().st_size
    assert f".project/acuerdos.md  ({tam} B)" in srv.listar_documentos(proyecto="demo", carpeta=".project").splitlines()


# ───────────────────────── criterio 8: buscar ─────────────────────────

def test_buscar_un_id_devuelve_el_registro_primero(srv, memoria, proyecto):
    (proyecto["repo"] / "docs" / "notas.md").write_text("Ver T-1 y T-10 en el código\n")
    salida = srv.buscar(proyecto="demo", texto="T-1").splitlines()
    assert salida[0] == "T-001 · integrada · Primera tarea (.project/tareas/T-001-primera-tarea.md)", salida
    assert "docs/notas.md:1: Ver T-1 y T-10 en el código" in salida


def test_buscar_por_titulo_devuelve_el_registro_primero(srv, memoria):
    salida = srv.buscar(proyecto="demo", texto="objectmapper").splitlines()
    assert salida[0] == f"ADR-020 · acordada · ObjectMapper de Spring Boot (.project/decisiones/{ADR_020})", salida


def test_coincidencias_de_memoria_antes_que_las_del_codigo(srv, memoria, proyecto):
    (proyecto["repo"] / "docs" / "ruido.md").write_text("\n".join("zorro gris" for _ in range(50)) + "\n")
    (memoria / "notas.md").write_text("Un zorro gris en la memoria\n")
    salida = srv.buscar(proyecto="demo", texto="zorro gris", max_resultados=5).splitlines()
    assert salida[0] == ".project/notas.md:1: Un zorro gris en la memoria", salida
    assert len(salida) == 6 and salida[-1].startswith("(… más resultados")


# ───────────────────────── criterio 10: registrar_tarea en un solo repositorio ─────────────────────────

def test_un_solo_repo_ignora_repositorio(srv, proyecto):
    salida = srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c", repositorio="x")
    assert salida.startswith("T-001 registrada") and "(proyecto de un solo repositorio: se ignoró `repositorio`)" in salida
    tarea = next((proyecto["mem"] / "tareas").glob("T-001*.md")).read_text()
    assert "repositorio:" not in tarea.split("---")[1]
