"""T-009: arranque compacto (ADR-026) y vínculo tarea ↔ pendiente con `resuelve` (ADR-027).
get_context lista los pendientes abiertos desde el catálogo, una línea cada uno; OPEN.md no cambia.
create_task valida y guarda `resuelve`; update_task(..., "integrada" o "merged") recuerda los que siguen abiertos sin
cerrar nada; analizar_uso.py reporta el tamaño del arranque y la higiene de pendientes referenciados."""
import datetime as dt
import json
from pathlib import Path

from conftest import log_git
from test_analizar_uso import _correr, _log_filas

SEPARADOR = "\n\n---\n\n"


def _pendiente(mem: Path, numero: int, tema: str, estado: str = "open", fecha: str = "2026-10-01") -> None:
    """Pendiente escrito a mano (para ids que add_pending no generaría, p. ej. P-1000)."""
    carpeta = mem / "pending"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"P-{numero:03d}-x.md").write_text(
        f"---\nid: P-{numero:03d}\ntopic: {tema}\nstatus: {estado}\ndate: {fecha}\n---\nCuerpo de P-{numero}\n",
        encoding="utf-8")


def _bloque(ctx: str) -> str:
    return next(p for p in ctx.split(SEPARADOR) if p.startswith("# Open items"))


# ───────────────────────── criterio 1: bloque de pendientes abiertos ─────────────────────────

def test_contexto_lista_pendientes_abiertos_una_linea_cada_uno(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="Primera línea del cuerpo\nmás", owner="Emanuel")
    srv.add_pending(project="demo", topic="Cerrado", context="c")
    srv.close_pending(project="demo", id="P-2", resolution="listo")
    largo = "x" * 120
    _pendiente(proyecto["mem"], 1000, "Mil", fecha="2026-10-05")
    _pendiente(proyecto["mem"], 10, largo, fecha="2026-10-03")
    hoy = dt.date.today().isoformat()
    ctx = srv.get_context(project="demo")
    assert _bloque(ctx) == "\n".join([
        "# Open items (3)",
        f"- P-001 · Parry ({hoy})",
        f"- P-010 · {'x' * 99}… (2026-10-03)",
        "- P-1000 · Mil (2026-10-05)",
        'Detail: read_document("demo", "P-NNN")'])
    assert "Primera línea del cuerpo" not in ctx and "Emanuel" not in ctx
    assert "Recently closed" not in ctx and "_View generated" not in ctx and "P-002" not in ctx


def test_tema_de_100_caracteres_no_se_corta(srv, proyecto):
    _pendiente(proyecto["mem"], 1, "y" * 100)
    assert f"- P-001 · {'y' * 100} (2026-10-01)" in srv.get_context(project="demo")


def test_sin_pendientes_abiertos_solo_el_encabezado(srv, proyecto):
    srv.add_pending(project="demo", topic="Uno", context="c")
    srv.close_pending(project="demo", id="P-001", resolution="r")
    assert _bloque(srv.get_context(project="demo")) == "# Open items (0)"


# ───────────────────────── criterio 2: el resto no cambia; OPEN.md intacto ─────────────────────────

def test_orden_de_las_partes_del_contexto(srv, proyecto, entorno):
    import shutil
    srv.update_index(project="demo", content="# Demo\nEstado: fase A")
    srv.add_pending(project="demo", topic="Abierto", context="c")
    srv.propose_decision(project="demo", title="X", decision="d", rationale="j")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c")
    for i in range(srv.UMBRAL_INDICE):
        srv.add_pending(project="demo", topic=f"Otro {i}", context="c")
    shutil.rmtree(entorno["base"] / "demo")
    partes = srv.get_context(project="demo").split(SEPARADOR)
    assert partes[0].startswith("⚠ The registered path of 'demo' no longer exists")
    assert partes[1].startswith("# Demo\nEstado: fase A")
    assert partes[2].startswith("# Open items (6)\n- P-001 · Abierto")
    assert partes[3].startswith("Proposed decisions awaiting the user's acceptance: ADR-001")
    assert partes[4].startswith("# Active code tasks\n- **T-001**")
    assert partes[5].startswith("⚠ INDEX.md is out of date")
    assert partes[6].startswith("Content language: en — ")                # T-010, criterio 11
    assert partes[7] == "Integrations: engram (if available)" and len(partes) == 8


def test_open_md_igual_antes_y_despues(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="Cuerpo", owner="Emanuel")
    srv.add_pending(project="demo", topic="Esquiva", context="Otro")
    srv.add_pending(project="demo", topic="Viejo", context="c")
    srv.close_pending(project="demo", id="P-003", resolution="r")
    vista = proyecto["mem"] / "OPEN.md"
    antes = vista.read_bytes()
    assert b"## Recently closed" in antes and b"Cuerpo" in antes and b"owner: Emanuel" in antes
    srv.get_context(project="demo")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c",
                        resolves="P-1, P-2 (parcial)")
    srv.update_task(project="demo", id="T-001", status="integrada")
    assert vista.read_bytes() == antes


# ───────────────────────── criterio 3: tamaño de get_context en analizar_uso ─────────────────────────

def test_analizar_uso_tamano_de_contexto_por_proyecto(entorno, monkeypatch, capsys):
    filas = [{"herramienta": "get_context", "resp_chars": c} for c in (1000, 9000, 9000)]
    filas += [{"herramienta": "get_context", "resp_chars": c, "proyecto": "otro"} for c in (400, 8000)]
    filas += [{"herramienta": "search", "resp_chars": 50000}]
    _correr(monkeypatch, "--log", str(_log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)))
    salida = capsys.readouterr().out
    bloque = salida.split("- Tamaño de get_context por proyecto")[1].split("\n- ")[0].splitlines()
    assert "referencia 2,000 tokens = 8,000 caracteres" in bloque[0]
    assert bloque[1] == "  demo: p50 9000 caracteres (~2250 tokens) · máx 9000 (~2250 tokens) · 3 llamadas  ⚠ > 2,000 tokens"
    assert bloque[2] == "  otro: p50 8000 caracteres (~2000 tokens) · máx 8000 (~2000 tokens) · 2 llamadas"


# ───────────────────────── criterio 4: create_task con resuelve ─────────────────────────

def _tarea(mem: Path, id_: str = "T-001") -> str:
    return next((mem / "tasks").glob(f"{id_}-*.md")).read_text(encoding="utf-8")


def test_resuelve_normaliza_guarda_y_muestra_seccion(srv, proyecto):
    for tema in ("Parry", "Esquiva"):
        srv.add_pending(project="demo", topic=tema, context="c")
    salida = srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c",
                                 resolves=" p-1 ,P-002( Parcial ) , P-01")
    assert salida.startswith("T-001 created"), salida
    texto = _tarea(proyecto["mem"])
    assert "\nresolves: P-001, P-002 (partial)\n" in texto
    assert "## Acceptance criteria\n\nc\n\n## Resolves\n\n- P-001 · Parry\n- P-002 (partial) · Esquiva\n\n" in texto


def test_resuelve_invalido_nombra_los_malos_y_no_escribe(srv, proyecto):
    srv.add_pending(project="demo", topic="Abierto", context="c")
    srv.add_pending(project="demo", topic="Cerrado", context="c")
    srv.close_pending(project="demo", id="P-002", resolution="r")
    commits = log_git(proyecto["mem"])
    salida = srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c",
                                 resolves="P-1, P-2 (parcial), p-99, ADR-1")
    assert salida.startswith("ERROR:") and "P-001" not in salida, salida
    assert "P-002 (not open)" in salida and "P-099 (does not exist)" in salida and "ADR-001 (does not exist)" in salida
    assert not list((proyecto["mem"] / "tasks").glob("T-*.md")) and log_git(proyecto["mem"]) == commits


def test_sin_resuelve_no_hay_campo_ni_seccion(srv, proyecto):
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", resolves="  ")
    texto = _tarea(proyecto["mem"])
    assert "resolves" not in texto and "## Resolves" not in texto


def test_resuelve_no_rompe_la_idempotencia(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="c")
    primera = srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", resolves="P-1")
    segunda = srv.create_task(project="demo", title="t ", goal="o", acceptance_criteria="c", resolves="P-1")
    assert primera.startswith("T-001 created") and "T-001 was already registered" in segunda
    assert len(list((proyecto["mem"] / "tasks").glob("T-*.md"))) == 1


# ───────────────────────── criterio 5: recordatorio al integrar ─────────────────────────

def test_integrada_recuerda_los_pendientes_abiertos_sin_tocarlos(srv, proyecto):
    for tema in ("Parry", "Esquiva", "Salto"):
        srv.add_pending(project="demo", topic=tema, context="c")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c",
                        resolves="P-1, P-2 (parcial), P-3")
    srv.close_pending(project="demo", id="P-3", resolution="r")
    pendientes = {p.name: p.read_bytes() for p in (proyecto["mem"] / "pending").glob("*.md")}
    salida = srv.update_task(project="demo", id="T-1", status="integrada")
    cabecera, recordatorio = salida.split("\n\n")
    assert cabecera.startswith("T-001 → merged · commit ")
    p2 = next((proyecto["mem"] / "pending").glob("P-002-*.md")).name
    assert recordatorio.splitlines() == [   # P-016: el parcial dice cómo registrar lo que falta
        'P-001 is still open: close it with close_pending("demo", "P-001", ...) if it was resolved',
        f'P-002 (partial) is still open: record what remains — append a note to its file with update_document('
        f'"demo", ".project/pending/{p2}", "<what remains>", mode="append"), or close it with '
        'close_pending("demo", "P-002", ...) and add the remainder with add_pending("demo", ...)']
    assert {p.name: p.read_bytes() for p in (proyecto["mem"] / "pending").glob("*.md")} == pendientes


def test_integrada_sin_resuelve_o_todos_cerrados_no_cambia(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="c")
    srv.create_task(project="demo", title="Sin", goal="o", acceptance_criteria="c")
    srv.create_task(project="demo", title="Con", goal="o", acceptance_criteria="c", resolves="P-1")
    srv.close_pending(project="demo", id="P-1", resolution="r")
    for id_ in ("T-001", "T-002"):
        salida = srv.update_task(project="demo", id=id_, status="integrada")
        assert salida.startswith(f"{id_} → merged · commit ") and "\n" not in salida, salida


def test_otros_estados_no_recuerdan(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="c")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", resolves="P-1")
    for estado in ("en_revision", "fallida", "descartada"):
        assert "sigue abierto" not in srv.update_task(project="demo", id="T-1", status=estado)


# ───────────────────────── criterio 6: higiene en analizar_uso ─────────────────────────

def test_analizar_uso_pendientes_referenciados_por_tareas_integradas(srv, proyecto, entorno, monkeypatch, capsys):
    for tema in ("Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis"):
        srv.add_pending(project="demo", topic=tema, context="c")
    srv.close_pending(project="demo", id="P-6", resolution="r")
    srv.create_task(project="demo", title="A", goal="Cubre P-002 y p-6", acceptance_criteria="c",
                        resolves="P-1 (parcial)", out_of_scope="P-004", notes="P-005")
    srv.update_task(project="demo", id="T-1", status="en_revision", result="Queda P-003")
    srv.request_changes(project="demo", id="T-1", findings="Falta P-004")
    srv.update_task(project="demo", id="T-1", status="en_revision", result="Sigue P-005")
    srv.update_task(project="demo", id="T-1", status="integrada")
    srv.create_task(project="demo", title="B", goal="P-002 sin integrar", acceptance_criteria="c")
    hoy = dt.date.today().isoformat()
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "search", "resp_chars": 10}])
    _correr(monkeypatch, "--log", str(log))
    seccion = capsys.readouterr().out.split("Pendientes abiertos referenciados por tareas integradas\n")[1]
    assert seccion.split("\n\n")[0].splitlines() == [
        "  demo",
        "    declarados en resuelve:",
        f"      P-001: T-001 (integrada {hoy})",
        "    mencionados en la spec:",
        f"      P-002: T-001 (integrada {hoy})",
        f"      P-004: T-001 (integrada {hoy})",
        "    mencionados en el Resultado:",
        f"      P-003: T-001 (integrada {hoy})",
        f"      P-005: T-001 (integrada {hoy})"]


def test_analizar_uso_higiene_sin_referencias(srv, proyecto, entorno, monkeypatch, capsys):
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "search", "resp_chars": 10}])
    _correr(monkeypatch, "--log", str(log))
    seccion = capsys.readouterr().out.split("Pendientes abiertos referenciados por tareas integradas\n")[1]
    assert seccion.split("\n\n")[0].splitlines() == [
        "  demo", "    declarados en resuelve: (ninguno)", "    mencionados en la spec: (ninguno)",
        "    mencionados en el Resultado: (ninguno)"]


# ───────────────────────── criterio 7: contrato ─────────────────────────

def test_contrato_registrar_tarea_tiene_resuelve():
    contrato = json.loads((Path(__file__).parent / "contrato_herramientas.json").read_text(encoding="utf-8"))
    herramientas = {h["nombre"]: h for h in contrato["herramientas"]}
    assert len(herramientas) == 28
    tarea = herramientas["create_task"]
    assert tarea["esquema_entrada"]["properties"]["resolves"] == {"default": "", "title": "Resolves", "type": "string"}
    assert "`resolves`" in tarea["descripcion"] and "never closes pending items" in tarea["descripcion"]
    assert "open items" in herramientas["get_context"]["descripcion"]
    assert "'merged'" in herramientas["update_task"]["descripcion"]
