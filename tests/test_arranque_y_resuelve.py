"""T-009: arranque compacto (ADR-026) y vínculo tarea ↔ pendiente con `resuelve` (ADR-027).
obtener_contexto lista los pendientes abiertos desde el catálogo, una línea cada uno; abiertas.md no cambia.
registrar_tarea valida y guarda `resuelve`; actualizar_tarea(..., "integrada") recuerda los que siguen abiertos sin
cerrar nada; analizar_uso.py reporta el tamaño del arranque y la higiene de pendientes referenciados."""
import datetime as dt
import json
from pathlib import Path

from conftest import log_git
from test_analizar_uso import _correr, _log_filas

SEPARADOR = "\n\n---\n\n"


def _pendiente(mem: Path, numero: int, tema: str, estado: str = "abierta", fecha: str = "2026-10-01") -> None:
    """Pendiente escrito a mano (para ids que registrar_pendiente no generaría, p. ej. P-1000)."""
    carpeta = mem / "pendientes"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"P-{numero:03d}-x.md").write_text(
        f"---\nid: P-{numero:03d}\ntema: {tema}\nestado: {estado}\nfecha: {fecha}\n---\nCuerpo de P-{numero}\n",
        encoding="utf-8")


def _bloque(ctx: str) -> str:
    return next(p for p in ctx.split(SEPARADOR) if p.startswith("# Pendientes abiertos"))


# ───────────────────────── criterio 1: bloque de pendientes abiertos ─────────────────────────

def test_contexto_lista_pendientes_abiertos_una_linea_cada_uno(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="Primera línea del cuerpo\nmás", dueno="Emanuel")
    srv.registrar_pendiente(proyecto="demo", tema="Cerrado", contexto="c")
    srv.cerrar_pendiente(proyecto="demo", id="P-2", resolucion="listo")
    largo = "x" * 120
    _pendiente(proyecto["mem"], 1000, "Mil", fecha="2026-10-05")
    _pendiente(proyecto["mem"], 10, largo, fecha="2026-10-03")
    hoy = dt.date.today().isoformat()
    ctx = srv.obtener_contexto(proyecto="demo")
    assert _bloque(ctx) == "\n".join([
        "# Pendientes abiertos (3)",
        f"- P-001 · Parry ({hoy})",
        f"- P-010 · {'x' * 99}… (2026-10-03)",
        "- P-1000 · Mil (2026-10-05)",
        'Detalle: leer_documento("demo", "P-NNN")'])
    assert "Primera línea del cuerpo" not in ctx and "Emanuel" not in ctx
    assert "Cerradas recientemente" not in ctx and "Decisiones abiertas" not in ctx and "P-002" not in ctx


def test_tema_de_100_caracteres_no_se_corta(srv, proyecto):
    _pendiente(proyecto["mem"], 1, "y" * 100)
    assert f"- P-001 · {'y' * 100} (2026-10-01)" in srv.obtener_contexto(proyecto="demo")


def test_sin_pendientes_abiertos_solo_el_encabezado(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Uno", contexto="c")
    srv.cerrar_pendiente(proyecto="demo", id="P-001", resolucion="r")
    assert _bloque(srv.obtener_contexto(proyecto="demo")) == "# Pendientes abiertos (0)"


# ───────────────────────── criterio 2: el resto no cambia; abiertas.md intacto ─────────────────────────

def test_orden_de_las_partes_del_contexto(srv, proyecto, entorno):
    import shutil
    srv.actualizar_indice(proyecto="demo", contenido="# Demo\nEstado: fase A")
    srv.registrar_pendiente(proyecto="demo", tema="Abierto", contexto="c")
    srv.registrar_decision(proyecto="demo", titulo="X", decision="d", justificacion="j")
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c")
    for i in range(srv.UMBRAL_INDICE):
        srv.registrar_pendiente(proyecto="demo", tema=f"Otro {i}", contexto="c")
    shutil.rmtree(entorno["base"] / "demo")
    partes = srv.obtener_contexto(proyecto="demo").split(SEPARADOR)
    assert partes[0].startswith("⚠ La ruta registrada de 'demo' ya no existe")
    assert partes[1].startswith("# Demo\nEstado: fase A")
    assert partes[2].startswith("# Pendientes abiertos (6)\n- P-001 · Abierto")
    assert partes[3].startswith("Decisiones propuestas pendientes de confirmar por el usuario: ADR-001")
    assert partes[4].startswith("# Tareas de código activas\n- **T-001**")
    assert partes[5].startswith("⚠ INDEX.md está desactualizado")
    assert partes[6] == "Integraciones: engram (si está disponible)" and len(partes) == 7


def test_abiertas_md_igual_antes_y_despues(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="Cuerpo", dueno="Emanuel")
    srv.registrar_pendiente(proyecto="demo", tema="Esquiva", contexto="Otro")
    srv.registrar_pendiente(proyecto="demo", tema="Viejo", contexto="c")
    srv.cerrar_pendiente(proyecto="demo", id="P-003", resolucion="r")
    vista = proyecto["mem"] / "abiertas.md"
    antes = vista.read_bytes()
    assert b"## Cerradas recientemente" in antes and b"Cuerpo" in antes and "dueño: Emanuel".encode() in antes
    srv.obtener_contexto(proyecto="demo")
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c",
                        resuelve="P-1, P-2 (parcial)")
    srv.actualizar_tarea(proyecto="demo", id="T-001", estado="integrada")
    assert vista.read_bytes() == antes


# ───────────────────────── criterio 3: tamaño de obtener_contexto en analizar_uso ─────────────────────────

def test_analizar_uso_tamano_de_contexto_por_proyecto(entorno, monkeypatch, capsys):
    filas = [{"herramienta": "obtener_contexto", "resp_chars": c} for c in (1000, 9000, 9000)]
    filas += [{"herramienta": "obtener_contexto", "resp_chars": c, "proyecto": "otro"} for c in (400, 8000)]
    filas += [{"herramienta": "buscar", "resp_chars": 50000}]
    _correr(monkeypatch, "--log", str(_log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)))
    salida = capsys.readouterr().out
    bloque = salida.split("- Tamaño de obtener_contexto por proyecto")[1].split("\n- ")[0].splitlines()
    assert "referencia 2,000 tokens = 8,000 caracteres" in bloque[0]
    assert bloque[1] == "  demo: p50 9000 caracteres (~2250 tokens) · máx 9000 (~2250 tokens) · 3 llamadas  ⚠ > 2,000 tokens"
    assert bloque[2] == "  otro: p50 8000 caracteres (~2000 tokens) · máx 8000 (~2000 tokens) · 2 llamadas"


# ───────────────────────── criterio 4: registrar_tarea con resuelve ─────────────────────────

def _tarea(mem: Path, id_: str = "T-001") -> str:
    return next((mem / "tareas").glob(f"{id_}-*.md")).read_text(encoding="utf-8")


def test_resuelve_normaliza_guarda_y_muestra_seccion(srv, proyecto):
    for tema in ("Parry", "Esquiva"):
        srv.registrar_pendiente(proyecto="demo", tema=tema, contexto="c")
    salida = srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c",
                                 resuelve=" p-1 ,P-002( Parcial ) , P-01")
    assert salida.startswith("T-001 registrada"), salida
    texto = _tarea(proyecto["mem"])
    assert "\nresuelve: P-001, P-002 (parcial)\n" in texto
    assert "## Criterios de aceptación\n\nc\n\n## Resuelve\n\n- P-001 · Parry\n- P-002 (parcial) · Esquiva\n\n" in texto


def test_resuelve_invalido_nombra_los_malos_y_no_escribe(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Abierto", contexto="c")
    srv.registrar_pendiente(proyecto="demo", tema="Cerrado", contexto="c")
    srv.cerrar_pendiente(proyecto="demo", id="P-002", resolucion="r")
    commits = log_git(proyecto["mem"])
    salida = srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c",
                                 resuelve="P-1, P-2 (parcial), p-99, ADR-1")
    assert salida.startswith("ERROR:") and "P-001" not in salida, salida
    assert "P-002 (no está abierto)" in salida and "P-099 (no existe)" in salida and "ADR-001 (no existe)" in salida
    assert not list((proyecto["mem"] / "tareas").glob("T-*.md")) and log_git(proyecto["mem"]) == commits


def test_sin_resuelve_no_hay_campo_ni_seccion(srv, proyecto):
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c", resuelve="  ")
    texto = _tarea(proyecto["mem"])
    assert "resuelve" not in texto and "## Resuelve" not in texto


def test_resuelve_no_rompe_la_idempotencia(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")
    primera = srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c", resuelve="P-1")
    segunda = srv.registrar_tarea(proyecto="demo", titulo="t ", objetivo="o", criterios_aceptacion="c", resuelve="P-1")
    assert primera.startswith("T-001 registrada") and "T-001 ya estaba registrado" in segunda
    assert len(list((proyecto["mem"] / "tareas").glob("T-*.md"))) == 1


# ───────────────────────── criterio 5: recordatorio al integrar ─────────────────────────

def test_integrada_recuerda_los_pendientes_abiertos_sin_tocarlos(srv, proyecto):
    for tema in ("Parry", "Esquiva", "Salto"):
        srv.registrar_pendiente(proyecto="demo", tema=tema, contexto="c")
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c",
                        resuelve="P-1, P-2 (parcial), P-3")
    srv.cerrar_pendiente(proyecto="demo", id="P-3", resolucion="r")
    pendientes = {p.name: p.read_bytes() for p in (proyecto["mem"] / "pendientes").glob("*.md")}
    salida = srv.actualizar_tarea(proyecto="demo", id="T-1", estado="integrada")
    cabecera, recordatorio = salida.split("\n\n")
    assert cabecera.startswith("T-001 → integrada · commit ")
    assert recordatorio.splitlines() == [
        'P-001 sigue abierto: ciérralo con cerrar_pendiente("demo", "P-001", ...) si quedó resuelto',
        "P-002 (parcial) sigue abierto: registra qué falta"]
    assert {p.name: p.read_bytes() for p in (proyecto["mem"] / "pendientes").glob("*.md")} == pendientes


def test_integrada_sin_resuelve_o_todos_cerrados_no_cambia(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")
    srv.registrar_tarea(proyecto="demo", titulo="Sin", objetivo="o", criterios_aceptacion="c")
    srv.registrar_tarea(proyecto="demo", titulo="Con", objetivo="o", criterios_aceptacion="c", resuelve="P-1")
    srv.cerrar_pendiente(proyecto="demo", id="P-1", resolucion="r")
    for id_ in ("T-001", "T-002"):
        salida = srv.actualizar_tarea(proyecto="demo", id=id_, estado="integrada")
        assert salida.startswith(f"{id_} → integrada · commit ") and "\n" not in salida, salida


def test_otros_estados_no_recuerdan(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Parry", contexto="c")
    srv.registrar_tarea(proyecto="demo", titulo="T", objetivo="o", criterios_aceptacion="c", resuelve="P-1")
    for estado in ("en_revision", "fallida", "descartada"):
        assert "sigue abierto" not in srv.actualizar_tarea(proyecto="demo", id="T-1", estado=estado)


# ───────────────────────── criterio 6: higiene en analizar_uso ─────────────────────────

def test_analizar_uso_pendientes_referenciados_por_tareas_integradas(srv, proyecto, entorno, monkeypatch, capsys):
    for tema in ("Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis"):
        srv.registrar_pendiente(proyecto="demo", tema=tema, contexto="c")
    srv.cerrar_pendiente(proyecto="demo", id="P-6", resolucion="r")
    srv.registrar_tarea(proyecto="demo", titulo="A", objetivo="Cubre P-002 y p-6", criterios_aceptacion="c",
                        resuelve="P-1 (parcial)", fuera_de_alcance="P-004", notas="P-005")
    srv.actualizar_tarea(proyecto="demo", id="T-1", estado="en_revision", resultado="Queda P-003")
    srv.devolver_tarea(proyecto="demo", id="T-1", observaciones="Falta P-004")
    srv.actualizar_tarea(proyecto="demo", id="T-1", estado="en_revision", resultado="Sigue P-005")
    srv.actualizar_tarea(proyecto="demo", id="T-1", estado="integrada")
    srv.registrar_tarea(proyecto="demo", titulo="B", objetivo="P-002 sin integrar", criterios_aceptacion="c")
    hoy = dt.date.today().isoformat()
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "buscar", "resp_chars": 10}])
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
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "buscar", "resp_chars": 10}])
    _correr(monkeypatch, "--log", str(log))
    seccion = capsys.readouterr().out.split("Pendientes abiertos referenciados por tareas integradas\n")[1]
    assert seccion.split("\n\n")[0].splitlines() == [
        "  demo", "    declarados en resuelve: (ninguno)", "    mencionados en la spec: (ninguno)",
        "    mencionados en el Resultado: (ninguno)"]


# ───────────────────────── criterio 7: contrato ─────────────────────────

def test_contrato_registrar_tarea_tiene_resuelve():
    contrato = json.loads((Path(__file__).parent / "contrato_herramientas.json").read_text(encoding="utf-8"))
    herramientas = {h["nombre"]: h for h in contrato["herramientas"]}
    assert len(herramientas) == 26
    tarea = herramientas["registrar_tarea"]
    assert tarea["esquema_entrada"]["properties"]["resuelve"] == {"default": "", "title": "Resuelve", "type": "string"}
    assert "`resuelve`" in tarea["descripcion"] and "Nunca cierra pendientes" in tarea["descripcion"]
    assert "pendientes abiertos" in herramientas["obtener_contexto"]["descripcion"]
    assert "'integrada'" in herramientas["actualizar_tarea"]["descripcion"]
