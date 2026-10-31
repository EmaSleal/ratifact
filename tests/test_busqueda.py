"""T-007, revisión 1: cuotas de search. El id exacto va primero; los títulos coinciden solo al inicio de palabra (sin
distinguir mayúsculas ni acentos) y con tope de 5; el resto del presupuesto se reparte entre la memoria y el código
(lo que un lado no usa pasa al otro); la última línea dice cuántos se omitieron por sección. Además,
list_documents registra la `carpeta` en la telemetría."""
import json
import re
import sys
from pathlib import Path

import analizar_uso

CATALOGO = re.compile(r"^[A-Z]+-\d+ · ")


def _registro(mem: Path, carpeta: str, id_: str, titulo: str, estado: str = "todo", clave: str = "title"):
    d = mem / carpeta
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{id_}-registro.md"
    p.write_text(f"---\nid: {id_}\n{clave}: {titulo}\nstatus: {estado}\n---\n# {id_} — {titulo}\n", encoding="utf-8")
    return p


def _secciones(salida: str):
    lineas = salida.splitlines()
    return ([l for l in lineas if CATALOGO.match(l)], [l for l in lineas if l.startswith(".project/")],
            [l for l in lineas if not CATALOGO.match(l) and not l.startswith((".project/", "(…"))])


# ───────────────────────── 15(c): el código no se queda sin cuota ─────────────────────────

def test_memoria_con_muchas_menciones_no_tapa_el_codigo(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("Revisar AsientoContableService\n" * 25)
    src = proyecto["repo"] / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "AsientoContableService.java").write_text("public class AsientoContableService {}\n")
    salida = srv.search(project="demo", query="AsientoContableService")
    assert "src/main/java/AsientoContableService.java:1: public class AsientoContableService {}" in salida.splitlines()
    _, memoria, codigo = _secciones(salida)
    assert len(memoria) == 19 and len(codigo) == 1, salida      # lo que el código no usa vuelve a la memoria


def test_pocas_coincidencias_en_memoria_ceden_su_cuota_al_codigo(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris en la memoria\n")
    (proyecto["repo"] / "docs" / "ruido.md").write_text("zorro gris\n" * 30)
    _, memoria, codigo = _secciones(srv.search(project="demo", query="zorro gris", max_results=10))
    assert len(memoria) == 1 and len(codigo) == 9


def test_pocas_coincidencias_en_codigo_ceden_su_cuota_a_la_memoria(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n" * 30)
    (proyecto["repo"] / "docs" / "ruido.md").write_text("zorro gris en el código\n")
    _, memoria, codigo = _secciones(srv.search(project="demo", query="zorro gris", max_results=10))
    assert len(memoria) == 9 and codigo == ["docs/ruido.md:1: zorro gris en el código"]


# ───────────────────────── 15(b): títulos al inicio de palabra, tope 5 ─────────────────────────

def test_titulos_solo_coinciden_al_inicio_de_palabra(srv, proyecto):
    _registro(proyecto["mem"], "decisions", "ADR-001", "Tipo de cambio híbrido", "accepted")
    _registro(proyecto["mem"], "pending", "P-001", "IVA incluido", "open", clave="topic")
    catalogo, _, _ = _secciones(srv.search(project="demo", query="id"))
    assert catalogo == []


def test_titulos_sin_distinguir_mayusculas_ni_acentos(srv, proyecto):
    _registro(proyecto["mem"], "tasks", "T-001", "Asientos contables de cierre")
    _registro(proyecto["mem"], "tasks", "T-002", "Navegación por id")
    linea = "T-001 · todo · Asientos contables de cierre (.project/tasks/T-001-registro.md)"
    assert srv.search(project="demo", query="asiento").splitlines()[0] == linea
    assert srv.search(project="demo", query="ASIENTOS CONTABLES").splitlines()[0] == linea
    assert srv.search(project="demo", query="navegacion").splitlines()[0].startswith("T-002 · ")
    assert srv.search(project="demo", query="NAVEGACIÓN").splitlines()[0].startswith("T-002 · ")


def test_titulos_con_tope_de_cinco(srv, proyecto):
    for n in range(1, 8):
        _registro(proyecto["mem"], "tasks", f"T-{n:03d}", f"Asiento número {n}")
    salida = srv.search(project="demo", query="asiento")
    catalogo, _, _ = _secciones(salida)
    assert [l.split(" · ")[0] for l in catalogo] == ["T-001", "T-002", "T-003", "T-004", "T-005"]
    assert salida.splitlines()[-1] == "(… more results — omitted: catalog 2, memory 0, code 0; refine the query)"


# ───────────────────────── 15(a): el id exacto va primero ─────────────────────────

def test_id_exacto_antes_que_los_titulos(srv, proyecto):
    _registro(proyecto["mem"], "tasks", "T-001", "Seguimiento de ADR-24")
    _registro(proyecto["mem"], "decisions", "ADR-024", "Integraciones opcionales", "proposed")
    catalogo, _, _ = _secciones(srv.search(project="demo", query="adr-24"))
    assert [l.split(" · ")[0] for l in catalogo] == ["ADR-024", "T-001"]
    assert srv.search(project="demo", query="adr-24").splitlines()[0].startswith("ADR-024 · proposed · ")


# ───────────────────────── 15(d): omitidos por sección ─────────────────────────

def test_ultima_linea_cuenta_omitidos_por_seccion(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n" * 30)
    (proyecto["repo"] / "docs" / "ruido.md").write_text("zorro gris\n" * 40)
    salida = srv.search(project="demo", query="zorro gris", max_results=10).splitlines()
    assert len(salida) == 11
    assert salida[-1] == "(… more results — omitted: catalog 0, memory 25, code 35; refine the query)"


def test_sin_omitidos_no_hay_linea_final(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n")
    salida = srv.search(project="demo", query="zorro gris").splitlines()
    assert salida == [".project/notas.md:1: zorro gris"]


# ───────────────────────── 15(e): sin repetir la línea del título ─────────────────────────

def test_no_repite_el_titulo_del_frontmatter_de_un_registro_mostrado(srv, proyecto):
    _registro(proyecto["mem"], "tasks", "T-001", "Asientos contables")
    _registro(proyecto["mem"], "pending", "P-001", "Asientos pendientes", "open", clave="topic")
    salida = srv.search(project="demo", query="asientos").splitlines()
    assert not [l for l in salida if l.endswith((": title: Asientos contables", ": topic: Asientos pendientes"))], salida
    assert ".project/tasks/T-001-registro.md:6: # T-001 — Asientos contables" in salida      # el cuerpo sí sale


# ───────────────────────── 16: telemetría de list_documents ─────────────────────────

def test_listar_documentos_registra_la_carpeta(srv, proyecto, entorno):
    srv.list_documents(project="demo", folder=".project")
    filas = [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]
    assert [f for f in filas if f["herramienta"] == "list_documents"][-1]["carpeta"] == ".project"


def test_analizar_uso_muestra_la_carpeta_en_respuestas_grandes(srv, proyecto, entorno, monkeypatch, capsys):
    for n in range(150):
        (proyecto["repo"] / "docs" / f"archivo-{n:03d}.md").write_text("x\n")
    srv.list_documents(project="demo", folder="docs")
    monkeypatch.setattr(sys, "argv", ["analizar_uso.py"])
    analizar_uso.main()
    seccion = capsys.readouterr().out.split("Largest responses")[1].splitlines()
    assert "list_documents" in seccion[1] and seccion[1].endswith(" · docs"), seccion[1]


# ───────────────────────── revisión 2, 18–20: nombre del archivo primero y una línea por archivo ─────────────────────────

def _omitidos(salida: str) -> str:
    return salida.splitlines()[-1]


def test_caso_real_el_java_aparece_aunque_docs_tenga_muchas_menciones(srv, proyecto):
    """20(a): en el ERP, 10 líneas de docs/contabilidad/*.md (que van antes que src/ por ruta) tapaban el .java."""
    docs = proyecto["repo"] / "docs" / "contabilidad"
    docs.mkdir(parents=True)
    for n in range(8):
        (docs / f"modulo-{n}.md").write_text("Ver AsientoContableService para el cierre\n" * 4)
    java = proyecto["repo"] / "src" / "main" / "java" / "erp" / "contabilidad"
    java.mkdir(parents=True)
    (java / "AsientoContableService.java").write_text("package erp;\npublic class AsientoContableService {\n}\n")
    salida = srv.search(project="demo", query="AsientoContableService")
    _, _, codigo = _secciones(salida)
    ruta = "src/main/java/erp/contabilidad/AsientoContableService.java"
    assert codigo[0] == f"{ruta}:2: public class AsientoContableService {{", salida
    assert sum(1 for l in codigo if l.startswith("docs/contabilidad/")) >= 8


def test_primera_pasada_una_linea_por_archivo(srv, proyecto):
    """20(b) y 19: con N archivos y presupuesto ≥ N, las primeras N líneas de la sección son N archivos distintos;
    la segunda pasada agrega más líneas de archivos ya listados, agrupadas por archivo."""
    for n in range(6):
        (proyecto["repo"] / "docs" / f"nota-{n}.md").write_text("zorro gris\n" * 5)
        (proyecto["mem"] / f"nota-{n}.md").write_text("zorro gris\n" * 5)
    salida = srv.search(project="demo", query="zorro gris", max_results=20)
    _, memoria, codigo = _secciones(salida)
    assert len(memoria) == 10 and len(codigo) == 10, salida
    for seccion, prefijo in ((memoria, ".project/"), (codigo, "docs/")):
        archivos = [l.split(":")[0] for l in seccion]
        assert archivos[:6] == [f"{prefijo}nota-{n}.md" for n in range(6)], salida
        assert archivos[6:] == [f"{prefijo}nota-0.md"] * 4, salida
        assert [l.split(":")[1] for l in seccion[:7]] == ["1"] * 6 + ["2"]
    assert _omitidos(salida) == "(… more results — omitted: catalog 0, memory 20, code 20; refine the query)"


def test_omitidos_cuenta_tambien_archivos_por_seccion(srv, proyecto):
    """19: un archivo omitido es uno con coincidencias del que no se muestra ninguna línea."""
    for n in range(12):
        (proyecto["repo"] / "docs" / f"nota-{n:02d}.md").write_text("zorro gris\n" * 3)
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n" * 7)
    salida = srv.search(project="demo", query="zorro gris", max_results=10)
    _, memoria, codigo = _secciones(salida)
    assert len(memoria) == 5 and len({l.split(":")[0] for l in codigo}) == 5 == len(codigo), salida
    assert _omitidos(salida) == ("(… more results — omitted: catalog 0, memory 2 lines/0 files, "
                                 "code 31 lines/7 files; refine the query)")


def test_coincidencia_solo_por_nombre_se_lista_una_vez(srv, proyecto):
    """20(c): el nombre coincide (inicio de palabra o de tramo camelCase) pero ninguna línea; sale una vez y primero."""
    (proyecto["repo"] / "docs" / "cierre.md").write_text("el asiento contable del cierre\n")
    src = proyecto["repo"] / "src"
    src.mkdir()
    (src / "AsientoContableService.java").write_text("public class Servicio {}\n")
    (src / "Recontable.java").write_text("class X {}\n")
    salida = srv.search(project="demo", query="contable")
    _, _, codigo = _secciones(salida)
    assert codigo == ["src/AsientoContableService.java: (file name matches)",
                      "docs/cierre.md:1: el asiento contable del cierre"], salida
    assert "Recontable" not in salida


def test_nombre_en_memoria_solo_para_archivos_que_no_son_registros(srv, proyecto):
    (proyecto["mem"] / "a-notas.md").write_text("un asiento suelto\n")
    (proyecto["mem"] / "plan-asientos.md").write_text("nada que ver\n")
    _registro(proyecto["mem"], "tasks", "T-001", "Otra cosa")
    (proyecto["mem"] / "tasks" / "T-001-registro.md").rename(proyecto["mem"] / "tasks" / "T-001-asiento.md")
    salida = srv.search(project="demo", query="asiento")
    _, memoria, _ = _secciones(salida)
    assert memoria == [".project/plan-asientos.md: (file name matches)",
                       ".project/a-notas.md:1: un asiento suelto"], salida


def test_regla_de_inicio_de_palabra_en_nombres():
    from ratifact.busqueda import _nombre_coincide
    for nombre, texto in [("AsientoContableService", "AsientoContableService"), ("AsientoContableService", "asiento"),
                          ("AsientoContableService", "contable"), ("AsientoContableService", "SERVICE"),
                          ("AsientoContableService", "contable service"), ("asiento_contable", "Contable"),
                          ("NavegacionPorId", "navegación"), ("factura-v2.test", "v2"), ("V2Factura", "factura")]:
        assert _nombre_coincide(nombre, texto), (nombre, texto)
    for nombre, texto in [("AsientoContableService", "ontable"), ("Recontable", "contable"), ("Hibrido", "id"),
                          ("AsientoContableService", "  "), ("ACME", "cme")]:
        assert not _nombre_coincide(nombre, texto), (nombre, texto)
