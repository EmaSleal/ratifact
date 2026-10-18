"""T-007, revisión 1: cuotas de buscar. El id exacto va primero; los títulos coinciden solo al inicio de palabra (sin
distinguir mayúsculas ni acentos) y con tope de 5; el resto del presupuesto se reparte entre la memoria y el código
(lo que un lado no usa pasa al otro); la última línea dice cuántos se omitieron por sección. Además,
listar_documentos registra la `carpeta` en la telemetría."""
import json
import re
import sys
from pathlib import Path

import analizar_uso

CATALOGO = re.compile(r"^[A-Z]+-\d+ · ")


def _registro(mem: Path, carpeta: str, id_: str, titulo: str, estado: str = "pendiente", clave: str = "titulo"):
    d = mem / carpeta
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{id_}-registro.md"
    p.write_text(f"---\nid: {id_}\n{clave}: {titulo}\nestado: {estado}\n---\n# {id_} — {titulo}\n", encoding="utf-8")
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
    salida = srv.buscar(proyecto="demo", texto="AsientoContableService")
    assert "src/main/java/AsientoContableService.java:1: public class AsientoContableService {}" in salida.splitlines()
    _, memoria, codigo = _secciones(salida)
    assert len(memoria) == 19 and len(codigo) == 1, salida      # lo que el código no usa vuelve a la memoria


def test_pocas_coincidencias_en_memoria_ceden_su_cuota_al_codigo(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris en la memoria\n")
    (proyecto["repo"] / "docs" / "ruido.md").write_text("zorro gris\n" * 30)
    _, memoria, codigo = _secciones(srv.buscar(proyecto="demo", texto="zorro gris", max_resultados=10))
    assert len(memoria) == 1 and len(codigo) == 9


def test_pocas_coincidencias_en_codigo_ceden_su_cuota_a_la_memoria(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n" * 30)
    (proyecto["repo"] / "docs" / "ruido.md").write_text("zorro gris en el código\n")
    _, memoria, codigo = _secciones(srv.buscar(proyecto="demo", texto="zorro gris", max_resultados=10))
    assert len(memoria) == 9 and codigo == ["docs/ruido.md:1: zorro gris en el código"]


# ───────────────────────── 15(b): títulos al inicio de palabra, tope 5 ─────────────────────────

def test_titulos_solo_coinciden_al_inicio_de_palabra(srv, proyecto):
    _registro(proyecto["mem"], "decisiones", "ADR-001", "Tipo de cambio híbrido", "acordada")
    _registro(proyecto["mem"], "pendientes", "P-001", "IVA incluido", "abierta", clave="tema")
    catalogo, _, _ = _secciones(srv.buscar(proyecto="demo", texto="id"))
    assert catalogo == []


def test_titulos_sin_distinguir_mayusculas_ni_acentos(srv, proyecto):
    _registro(proyecto["mem"], "tareas", "T-001", "Asientos contables de cierre")
    _registro(proyecto["mem"], "tareas", "T-002", "Navegación por id")
    linea = "T-001 · pendiente · Asientos contables de cierre (.project/tareas/T-001-registro.md)"
    assert srv.buscar(proyecto="demo", texto="asiento").splitlines()[0] == linea
    assert srv.buscar(proyecto="demo", texto="ASIENTOS CONTABLES").splitlines()[0] == linea
    assert srv.buscar(proyecto="demo", texto="navegacion").splitlines()[0].startswith("T-002 · ")
    assert srv.buscar(proyecto="demo", texto="NAVEGACIÓN").splitlines()[0].startswith("T-002 · ")


def test_titulos_con_tope_de_cinco(srv, proyecto):
    for n in range(1, 8):
        _registro(proyecto["mem"], "tareas", f"T-{n:03d}", f"Asiento número {n}")
    salida = srv.buscar(proyecto="demo", texto="asiento")
    catalogo, _, _ = _secciones(salida)
    assert [l.split(" · ")[0] for l in catalogo] == ["T-001", "T-002", "T-003", "T-004", "T-005"]
    assert salida.splitlines()[-1] == "(… más resultados — omitidos: catálogo 2, memoria 0, código 0; refina la búsqueda)"


# ───────────────────────── 15(a): el id exacto va primero ─────────────────────────

def test_id_exacto_antes_que_los_titulos(srv, proyecto):
    _registro(proyecto["mem"], "tareas", "T-001", "Seguimiento de ADR-24")
    _registro(proyecto["mem"], "decisiones", "ADR-024", "Integraciones opcionales", "propuesta")
    catalogo, _, _ = _secciones(srv.buscar(proyecto="demo", texto="adr-24"))
    assert [l.split(" · ")[0] for l in catalogo] == ["ADR-024", "T-001"]
    assert srv.buscar(proyecto="demo", texto="adr-24").splitlines()[0].startswith("ADR-024 · propuesta · ")


# ───────────────────────── 15(d): omitidos por sección ─────────────────────────

def test_ultima_linea_cuenta_omitidos_por_seccion(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n" * 30)
    (proyecto["repo"] / "docs" / "ruido.md").write_text("zorro gris\n" * 40)
    salida = srv.buscar(proyecto="demo", texto="zorro gris", max_resultados=10).splitlines()
    assert len(salida) == 11
    assert salida[-1] == "(… más resultados — omitidos: catálogo 0, memoria 25, código 35; refina la búsqueda)"


def test_sin_omitidos_no_hay_linea_final(srv, proyecto):
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n")
    salida = srv.buscar(proyecto="demo", texto="zorro gris").splitlines()
    assert salida == [".project/notas.md:1: zorro gris"]


# ───────────────────────── 15(e): sin repetir la línea del título ─────────────────────────

def test_no_repite_el_titulo_del_frontmatter_de_un_registro_mostrado(srv, proyecto):
    _registro(proyecto["mem"], "tareas", "T-001", "Asientos contables")
    _registro(proyecto["mem"], "pendientes", "P-001", "Asientos pendientes", "abierta", clave="tema")
    salida = srv.buscar(proyecto="demo", texto="asientos").splitlines()
    assert not [l for l in salida if l.endswith((": titulo: Asientos contables", ": tema: Asientos pendientes"))], salida
    assert ".project/tareas/T-001-registro.md:6: # T-001 — Asientos contables" in salida      # el cuerpo sí sale


# ───────────────────────── 16: telemetría de listar_documentos ─────────────────────────

def test_listar_documentos_registra_la_carpeta(srv, proyecto, entorno):
    srv.listar_documentos(proyecto="demo", carpeta=".project")
    filas = [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]
    assert [f for f in filas if f["herramienta"] == "listar_documentos"][-1]["carpeta"] == ".project"


def test_analizar_uso_muestra_la_carpeta_en_respuestas_grandes(srv, proyecto, entorno, monkeypatch, capsys):
    for n in range(150):
        (proyecto["repo"] / "docs" / f"archivo-{n:03d}.md").write_text("x\n")
    srv.listar_documentos(proyecto="demo", carpeta="docs")
    monkeypatch.setattr(sys, "argv", ["analizar_uso.py"])
    analizar_uso.main()
    seccion = capsys.readouterr().out.split("Respuestas más grandes")[1].splitlines()
    assert "listar_documentos" in seccion[1] and seccion[1].endswith(" · docs"), seccion[1]


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
    salida = srv.buscar(proyecto="demo", texto="AsientoContableService")
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
    salida = srv.buscar(proyecto="demo", texto="zorro gris", max_resultados=20)
    _, memoria, codigo = _secciones(salida)
    assert len(memoria) == 10 and len(codigo) == 10, salida
    for seccion, prefijo in ((memoria, ".project/"), (codigo, "docs/")):
        archivos = [l.split(":")[0] for l in seccion]
        assert archivos[:6] == [f"{prefijo}nota-{n}.md" for n in range(6)], salida
        assert archivos[6:] == [f"{prefijo}nota-0.md"] * 4, salida
        assert [l.split(":")[1] for l in seccion[:7]] == ["1"] * 6 + ["2"]
    assert _omitidos(salida) == "(… más resultados — omitidos: catálogo 0, memoria 20, código 20; refina la búsqueda)"


def test_omitidos_cuenta_tambien_archivos_por_seccion(srv, proyecto):
    """19: un archivo omitido es uno con coincidencias del que no se muestra ninguna línea."""
    for n in range(12):
        (proyecto["repo"] / "docs" / f"nota-{n:02d}.md").write_text("zorro gris\n" * 3)
    (proyecto["mem"] / "notas.md").write_text("zorro gris\n" * 7)
    salida = srv.buscar(proyecto="demo", texto="zorro gris", max_resultados=10)
    _, memoria, codigo = _secciones(salida)
    assert len(memoria) == 5 and len({l.split(":")[0] for l in codigo}) == 5 == len(codigo), salida
    assert _omitidos(salida) == ("(… más resultados — omitidos: catálogo 0, memoria 2 líneas/0 archivos, "
                                 "código 31 líneas/7 archivos; refina la búsqueda)")


def test_coincidencia_solo_por_nombre_se_lista_una_vez(srv, proyecto):
    """20(c): el nombre coincide (inicio de palabra o de tramo camelCase) pero ninguna línea; sale una vez y primero."""
    (proyecto["repo"] / "docs" / "cierre.md").write_text("el asiento contable del cierre\n")
    src = proyecto["repo"] / "src"
    src.mkdir()
    (src / "AsientoContableService.java").write_text("public class Servicio {}\n")
    (src / "Recontable.java").write_text("class X {}\n")
    salida = srv.buscar(proyecto="demo", texto="contable")
    _, _, codigo = _secciones(salida)
    assert codigo == ["src/AsientoContableService.java: (coincide el nombre del archivo)",
                      "docs/cierre.md:1: el asiento contable del cierre"], salida
    assert "Recontable" not in salida


def test_nombre_en_memoria_solo_para_archivos_que_no_son_registros(srv, proyecto):
    (proyecto["mem"] / "a-notas.md").write_text("un asiento suelto\n")
    (proyecto["mem"] / "plan-asientos.md").write_text("nada que ver\n")
    _registro(proyecto["mem"], "tareas", "T-001", "Otra cosa")
    (proyecto["mem"] / "tareas" / "T-001-registro.md").rename(proyecto["mem"] / "tareas" / "T-001-asiento.md")
    salida = srv.buscar(proyecto="demo", texto="asiento")
    _, memoria, _ = _secciones(salida)
    assert memoria == [".project/plan-asientos.md: (coincide el nombre del archivo)",
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
