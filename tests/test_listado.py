"""T-007 / ADR-023: list_documents con profundidad adaptativa. Si el listado completo entra en el presupuesto
(LIMITE_LISTADO_ENTRADAS / LIMITE_LISTADO_CARACTERES) sale igual que siempre; si no, se expande nivel por nivel
mientras entre, las carpetas sin expandir muestran cuántos archivos tienen y las cadenas de carpetas con un solo
hijo se colapsan en una línea."""
import re

from ratifact import config, listado

CADENA = "app/src/main/java/api/astro/whats_orders_manager"


def _contar(lineas: list[str]) -> int:
    """Archivos representados: 1 por línea de archivo, n por línea de carpeta '<ruta>/ (n files)'."""
    total = 0
    for linea in lineas:
        m = re.fullmatch(r".*/ \((\d+) files?\)", linea)
        if m:
            total += int(m.group(1))
        elif re.fullmatch(r".*  \(\d+ B\)", linea):
            total += 1
    return total


def test_presupuesto_en_config():
    assert config.LIMITE_LISTADO_ENTRADAS == 200 and config.LIMITE_LISTADO_CARACTERES == 8000


def test_carpeta_chica_igual_que_antes(srv, proyecto):
    docs = proyecto["repo"] / "docs"
    for nombre in ("b.md", "a/x.md", "a/y/z.md"):
        (docs / nombre).parent.mkdir(parents=True, exist_ok=True)
        (docs / nombre).write_text(f"contenido de {nombre}\n")
    esperado = [f"docs/{r}  ({(docs / r).stat().st_size} B)" for r in ("a/x.md", "a/y/z.md", "b.md", "vision.md")]
    assert srv.list_documents(project="demo").splitlines() == esperado


def test_arbol_grande_se_resume_por_niveles(srv, proyecto):
    raiz = proyecto["repo"] / "app"
    rutas = [f"src/main/java/api/astro/whats_orders_manager/paquete{p:02d}/Clase{c:03d}.java"
             for p in range(12) for c in range(50)]
    rutas += [f"modules/contabilidad/Asiento{c:02d}.java" for c in range(38)]
    rutas += [f"modules/m{m:02d}/sub/Clase{c:02d}.java" for m in range(18) for c in range(20)]
    rutas += ["pom.xml", "LEEME.md"]
    for r in rutas:
        (raiz / r).parent.mkdir(parents=True, exist_ok=True)
        (raiz / r).write_text("x\n")
    assert len(rutas) >= 1000

    salida = srv.list_documents(project="demo", folder="app")
    lineas = salida.splitlines()
    assert len(salida) <= 8000 and len(lineas) <= 200
    assert _contar(lineas) == len(rutas)
    assert "app/modules/contabilidad/ (38 files)" in lineas
    assert "app/pom.xml  (2 B)" in lineas
    # la cadena de 6 carpetas de un solo hijo aparece entera en cada línea, nunca partida por niveles
    assert any(l.startswith(CADENA + "/") for l in lineas)
    intermedias = ("app/src/", "app/src/main/", "app/src/main/java/", "app/src/main/java/api/")
    assert not any(l.split(" ")[0] in intermedias for l in lineas), lineas
    assert "summarized listing" in lineas[-1] and "`folder`" in lineas[-1]
    assert srv.list_documents(project="demo", folder="app") == salida            # determinista


def test_cadena_sin_expandir_en_una_linea():
    entradas = [(f"src/main/java/api/astro/whats_orders_manager/Clase{c:03d}.java", 10) for c in range(412)]
    entradas.append(("pom.xml", 5))
    lineas = listado._listado("app", entradas).splitlines()
    assert lineas[:2] == ["app/pom.xml  (5 B)", f"{CADENA}/ (412 files)"]
    assert "summarized listing" in lineas[-1]


def test_un_nivel_que_no_entra_se_recorta():
    entradas = [(f"Archivo{c:04d}.java", 10) for c in range(1500)]
    salida = listado._listado("plano", entradas)
    lineas = salida.splitlines()
    assert len(salida) <= 8000 and len(lineas) <= 200
    assert lineas[0] == "plano/Archivo0000.java  (10 B)"
    assert _contar(lineas) < 1500 and "more files" in lineas[-2] and "summarized listing" in lineas[-1]


def test_listado_que_entra_es_identico():
    entradas = [("a/x.md", 3), ("b.md", 4)]
    assert listado._listado("docs", entradas) == "docs/a/x.md  (3 B)\ndocs/b.md  (4 B)"
