"""T-011 (v1 paso 2): amend_task (ADR-021), read_task (ADR-031), variables RATIFACT_* con respaldo, telemetría y
analizar_uso con nombres ingleses, modos de update_document y textos en inglés."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

from conftest import log_git, recargar_servidor
from ratifact.vocabulario import HERRAMIENTAS_V0


def _tarea(mem: Path, id_: str = "T-001") -> Path:
    return next((mem / "tasks").glob(f"{id_}-*.md"))


def _nueva(srv, criterios="1. original"):
    srv.create_task(project="demo", title="Tope NC", goal="o", acceptance_criteria=criterios)


# ───────────────────────── amend_task (ADR-021) ─────────────────────────

def test_amend_agrega_bloque_fechado_sin_tocar_los_criterios(srv, proyecto):
    _nueva(srv)
    commits = len(log_git(proyecto["mem"]))
    salida = srv.amend_task(project="demo", id="t-1", additional_criteria="2. nuevo", notes="ojo con X")
    assert re.fullmatch(r"T-001 amended \(Amendment 1\) · commit \w+\nRun it with: /run-task T-001", salida), salida
    texto = _tarea(proyecto["mem"]).read_text()
    assert "## Acceptance criteria\n\n1. original\n\n## Amendments\n\n### Amendment 1 · " in texto
    bloque = texto.split("### Amendment 1 · ")[1].split("\n## How to verify")[0]
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}\n\*\*Additional criteria\*\*\n2\. nuevo\n\n\*\*Notes\*\*\nojo con X\n",
                    bloque), bloque
    assert texto.index("## Amendments") < texto.index("## How to verify") < texto.index("## Result")
    assert len(log_git(proyecto["mem"])) == commits + 1 and log_git(proyecto["mem"])[0] == "memoria: T-001 amendment 1"
    assert "status: todo" in texto


def test_segunda_enmienda_va_despues_de_la_primera(srv, proyecto, monkeypatch):
    _nueva(srv)
    srv.amend_task(project="demo", id="T-001", additional_criteria="2. a")
    salida = srv.amend_task(project="demo", id="T-001", notes="solo una nota")
    assert "(Amendment 2)" in salida
    texto = _tarea(proyecto["mem"]).read_text()
    assert texto.count("## Amendments") == 1
    assert texto.index("### Amendment 1") < texto.index("### Amendment 2") < texto.index("## How to verify")
    segunda = texto.split("### Amendment 2 · ")[1].split("\n\n## How to verify")[0]
    assert segunda.endswith("**Notes**\nsolo una nota") and "Additional criteria" not in segunda


def test_amend_exige_al_menos_un_campo(srv, proyecto):
    _nueva(srv)
    commits = log_git(proyecto["mem"])
    salida = srv.amend_task(project="demo", id="T-001", additional_criteria="  ", notes="")
    assert salida.startswith("ERROR:") and "additional_criteria" in salida and "notes" in salida
    assert log_git(proyecto["mem"]) == commits


@pytest.mark.parametrize("estado", ["in_progress", "in_review", "failed", "merged", "discarded"])
def test_amend_rechaza_otros_estados_nombrandolo(srv, proyecto, estado):
    _nueva(srv)
    srv.update_task(project="demo", id="T-001", status=estado)
    antes = _tarea(proyecto["mem"]).read_text()
    salida = srv.amend_task(project="demo", id="T-001", notes="n")
    assert salida.startswith(f"ERROR: T-001 is '{estado}'") and "request_changes" in salida
    assert _tarea(proyecto["mem"]).read_text() == antes


def test_amend_acepta_changes_requested(srv, proyecto):
    _nueva(srv)
    srv.update_task(project="demo", id="T-001", status="in_review", result="hecho")
    srv.request_changes(project="demo", id="T-001", findings="falta algo")
    assert "(Amendment 1)" in srv.amend_task(project="demo", id="T-001", additional_criteria="3. otro")
    texto = _tarea(proyecto["mem"]).read_text()
    assert texto.index("### Amendment 1") < texto.index("## Result") < texto.index("### Review 1")


def test_amend_idempotente_dentro_de_la_ventana(srv, proyecto, monkeypatch):
    from ratifact import registros
    _nueva(srv)
    ahora = dt.datetime.now().replace(second=0, microsecond=0)
    monkeypatch.setattr(registros, "_ahora", lambda: ahora)
    srv.amend_task(project="demo", id="T-001", additional_criteria="2. a", notes="n")
    commits = log_git(proyecto["mem"])
    monkeypatch.setattr(registros, "_ahora", lambda: ahora + dt.timedelta(minutes=5))
    repetida = srv.amend_task(project="demo", id="T-001", additional_criteria=" 2. a ", notes="n")
    assert "T-001 Amendment 1 was already registered" in repetida and log_git(proyecto["mem"]) == commits
    assert "(Amendment 2)" in srv.amend_task(project="demo", id="T-001", notes="otra")        # distinta: se escribe
    monkeypatch.setattr(registros, "_ahora", lambda: ahora + dt.timedelta(minutes=30))
    assert "(Amendment 3)" in srv.amend_task(project="demo", id="T-001", notes="otra")        # fuera de la ventana


def test_amend_de_tarea_vieja_sin_how_to_verify(srv, proyecto):
    ruta = proyecto["mem"] / "tasks" / "T-001-vieja.md"
    ruta.write_text("---\nid: T-001\ntitle: Vieja\nstatus: todo\n---\n# T-001 — Vieja\n\n## Goal\no\n\n## Result\n(x)\n")
    srv.amend_task(project="demo", id="T-001", notes="n")
    texto = ruta.read_text()
    assert texto.index("## Amendments") < texto.index("## Result")


# ───────────────────────── read_task (ADR-031) ─────────────────────────

SPEC = """# T-025 — Bloqueo fiscal

## Goal

Bloquear facturas emitidas.

## Acceptance criteria

1. Criterio uno.
2. Criterio dos.

## Applicable decisions

ADR-029

## Files involved

src/Factura.java

## Out of scope

Notas de crédito.

## Notes

Fase 0 primero.

## Amendments

### Amendment 1 · 2026-10-17 12:00
**Additional criteria**
3. Criterio enmendado.

## How to verify

From the repository root: `./mvnw test`

## Result
"""

HISTORIA = [
    ("result", "### 2026-10-17 · in_review\n## Estado: detenida tras la fase 0\n" + "hallazgo-uno\n" * 40
     + "### (a) Relación 1:1\ntexto a\n## Verificación\nok\n"),
    ("review", "### Review 1 · 2026-10-17 · changes_requested\nFix on the SAME branch.\n\n**Findings**\nrevision-uno\n"),
    ("result", "### 2026-10-18 · in_review\n## Revisión 1: correcciones\n### Commit 4f24548: rojo\n"
     + "resultado-dos\n" * 60 + "## Pruebas\n652 verdes\n"),
    ("review", "### Review 2 · 2026-10-18 · changes_requested\nFix on the SAME branch.\n\n**Findings**\nrevision-dos\n\n"
     "**Additional criteria**\n7. otro\n"),
]


def _t025(mem: Path, estado: str, historia=HISTORIA) -> Path:
    ruta = mem / "tasks" / "T-025-bloqueo-fiscal.md"
    cuerpo = SPEC + "\n" + "\n".join(b for _, b in historia)
    ruta.write_text(f"---\nid: T-025\ntitle: Bloqueo fiscal\nstatus: {estado}\nreviews: 2\n---\n{cuerpo}")
    return ruta


def _rangos(salida: str) -> list[tuple[str, int, int, int]]:
    return [(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4).replace(",", "")))
            for m in re.finditer(r"^- (### .+?) · lines (\d+)–(\d+) · ([\d,]+) chars$", salida, re.M)]


def test_read_task_devuelta_trae_spec_enmiendas_ultima_review_e_indice(srv, proyecto):
    ruta = _t025(proyecto["mem"], "changes_requested")
    salida = srv.read_task(project="demo", id="T-25")
    assert salida.startswith("(→ .project/tasks/T-025-bloqueo-fiscal.md)\n---\nid: T-025\n")
    for parte in ("## Goal", "1. Criterio uno.", "## Out of scope", "## Notes", "### Amendment 1 · 2026-10-17 12:00",
                  "3. Criterio enmendado.", "## How to verify"):
        assert parte in salida, parte
    assert "## Result — latest Review (lines " in salida and "revision-dos" in salida and "7. otro" in salida
    assert "hallazgo-uno" not in salida and "resultado-dos" not in salida and "revision-uno" not in salida
    indice = _rangos(salida)
    assert [h for h, *_ in indice] == ["### 2026-10-17 · in_review", "### Review 1 · 2026-10-17 · changes_requested",
                                       "### 2026-10-18 · in_review"]
    lineas = ruta.read_text().splitlines()
    for cabecera, desde, hasta, tam in indice:      # cada rango se lee con read_document y empieza en su cabecera
        bloque = srv.read_document(project="demo", path=".project/tasks/T-025-bloqueo-fiscal.md", from_line=desde,
                                   to_line=hasta)
        assert bloque.splitlines()[0] == cabecera and len(bloque) == tam
        assert next(l for l in lineas[hasta:] if l.strip()).startswith("### ")   # sin huecos entre bloques
    assert 'read_document("demo", ".project/tasks/T-025-bloqueo-fiscal.md", from_line, to_line)' in salida
    assert len(salida) < len(ruta.read_text())


@pytest.mark.parametrize("estado", ["in_review", "failed"])
def test_read_task_en_revision_o_fallida_trae_el_ultimo_resultado(srv, proyecto, estado):
    _t025(proyecto["mem"], estado, HISTORIA[:3])
    salida = srv.read_task(project="demo", id="T-025")
    assert "## Result — latest Result (lines " in salida and "resultado-dos" in salida and "652 verdes" in salida
    assert "### Commit 4f24548: rojo" in salida           # los títulos internos del resultado no cortan el bloque
    assert [h for h, *_ in _rangos(salida)] == ["### 2026-10-17 · in_review",
                                                 "### Review 1 · 2026-10-17 · changes_requested"]


def test_read_task_en_curso_tras_una_review_la_incluye(srv, proyecto):
    _t025(proyecto["mem"], "in_progress")
    salida = srv.read_task(project="demo", id="T-025")
    assert "## Result — latest Review" in salida and "revision-dos" in salida and len(_rangos(salida)) == 3


def test_read_task_sin_resultados(srv, proyecto):
    _nueva(srv)
    salida = srv.read_task(project="demo", id="T-001")
    assert salida.endswith("## Result\n(no result yet)") and "## Acceptance criteria\n\n1. original" in salida
    assert "(filled in by the coding agent when done)" not in salida


def test_read_task_merged_solo_indice(srv, proyecto):
    _t025(proyecto["mem"], "merged")
    salida = srv.read_task(project="demo", id="T-025")
    assert "## Result —" not in salida and len(_rangos(salida)) == 4


def test_read_task_id_inexistente(srv, proyecto):
    assert srv.read_task(project="demo", id="T-099") == "ERROR: T-099 does not exist."


def test_read_task_muestra_la_enmienda_escrita_por_amend(srv, proyecto):
    _nueva(srv)
    srv.amend_task(project="demo", id="T-001", additional_criteria="2. extra")
    assert "### Amendment 1 · " in srv.read_task(project="demo", id="T-001")


# ───────────────────────── update_task merged: recordatorio de parciales (P-016) ─────────────────────────

def test_recordatorio_parcial_es_aplicable_con_update_document(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="c")
    srv.create_task(project="demo", title="T", goal="o", acceptance_criteria="c", resolves="P-1 (partial)")
    salida = srv.update_task(project="demo", id="T-001", status="merged")
    ruta = re.search(r'update_document\("demo", "([^"]+)", "<what remains>", mode="append"\)', salida).group(1)
    assert "add_pending(" in salida and "close_pending(" in salida
    assert "saved (append)" in srv.update_document(project="demo", path=ruta, content="Falta X", mode="append")


# ───────────────────────── update_document: modos ─────────────────────────

@pytest.mark.parametrize("modo,esperado", [("replace", "replace"), ("append", "append"), ("reemplazar", "replace"),
                                           ("anexar", "append")])
def test_modos_ingleses_y_espanoles_hasta_1_1(srv, proyecto, modo, esperado):
    srv.create_document(project="demo", path="docs/n.md", content="uno")
    assert f"saved ({esperado})" in srv.update_document(project="demo", path="docs/n.md", content="dos", mode=modo)
    texto = (proyecto["repo"] / "docs" / "n.md").read_text()
    assert texto == ("uno\n\ndos\n" if esperado == "append" else "dos\n")


def test_modo_invalido(srv, proyecto):
    srv.create_document(project="demo", path="docs/n.md", content="uno")
    assert srv.update_document(project="demo", path="docs/n.md", content="x", mode="pisar").startswith(
        "ERROR: Invalid mode: 'replace' or 'append'")


# ───────────────────────── textos en inglés ─────────────────────────

def test_instrucciones_y_bloque_con_nombres_nuevos(srv, proyecto):
    salida = srv.project_instructions(project="demo")
    for nombre in ("get_context", "propose_decision", "accept_decision", "add_pending", "create_task", "amend_task",
                   "read_task", "request_changes", "/run-task T-NNN", "$run-task T-NNN"):
        assert nombre in salida, nombre
    for viejo in HERRAMIENTAS_V0:
        assert not re.search(rf"\b{viejo}\b", salida), viejo


def test_arranque_en_ingles(srv, proyecto):
    srv.add_pending(project="demo", topic="Parry", context="c")
    ctx = srv.get_context(project="demo")
    assert "# Open items (1)" in ctx and 'Detail: read_document("demo", "P-NNN")' in ctx
    assert "Content language: en — " in ctx and "Integrations: engram (if available)" in ctx


# ───────────────────────── variables de entorno RATIFACT_* ─────────────────────────

def test_ratifact_gana_sobre_el_respaldo(entorno, monkeypatch, capsys):
    nuevo = entorno["tmp"] / "nuevo.json"
    monkeypatch.setenv("RATIFACT_CONFIG", str(nuevo))
    monkeypatch.setenv("RATIFACT_LOG", str(entorno["tmp"] / "nuevo.jsonl"))
    srv = recargar_servidor()
    assert srv.CONFIG == nuevo and srv.LOG_USO == entorno["tmp"] / "nuevo.jsonl"
    err = capsys.readouterr().err
    assert "MEMORIA_PROYECTOS_CONFIG" not in err and "MEMORIA_PROYECTOS_LOG" not in err
    assert "MEMORIA_PROYECTOS_BASE is deprecated; rename it to RATIFACT_BASE" in err     # BASE sigue por respaldo


def test_respaldo_avisa_una_sola_vez_por_variable(entorno, capsys):
    from ratifact import config
    srv = recargar_servidor()
    assert str(srv.CONFIG) == entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]
    err = capsys.readouterr().err
    for var in ("CONFIG", "LOG", "BASE"):
        assert err.count(f"MEMORIA_PROYECTOS_{var} is deprecated") == 1, err
    assert config._entorno("CONFIG") == entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]
    assert "deprecated" not in capsys.readouterr().err                            # una sola vez por proceso


def test_ruta_de_configuracion_por_defecto(entorno, monkeypatch, tmp_path):
    for var in ("RATIFACT_CONFIG", "MEMORIA_PROYECTOS_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    vieja = tmp_path / "casa" / ".config" / "memoria-proyectos" / "projects.json"
    assert recargar_servidor().CONFIG == vieja
    nueva = tmp_path / "casa" / ".config" / "ratifact" / "projects.json"
    nueva.parent.mkdir(parents=True)
    nueva.write_text("{}")
    assert recargar_servidor().CONFIG == nueva and not vieja.exists()             # no se mueve ni crea nada


# ───────────────────────── telemetría y analizar_uso ─────────────────────────

def _filas(entorno) -> list[dict]:
    return [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]


def test_telemetria_con_nombres_ingleses(srv, proyecto, entorno):
    srv.read_document(project="demo", path="docs/vision.md")
    srv.search(project="demo", query="nada-de-nada")
    srv.list_documents(project="demo", folder="docs")
    lectura, busqueda, listado = _filas(entorno)[-3:]
    assert (lectura["herramienta"], lectura["proyecto"], lectura["ruta"]) == ("read_document", "demo", "docs/vision.md")
    assert (busqueda["herramienta"], busqueda["resultados"]) == ("search", 0)
    assert (listado["herramienta"], listado["carpeta"]) == ("list_documents", "docs")
    assert all(f["herramienta"] not in HERRAMIENTAS_V0 for f in _filas(entorno))


def test_analizar_uso_agrega_nombres_viejos_y_nuevos(entorno, monkeypatch, capsys):
    import analizar_uso
    ahora = dt.datetime.now()
    filas = [{"ts": (ahora - dt.timedelta(minutes=i)).isoformat(timespec="seconds"), "herramienta": h,
              "proyecto": "demo", "ms": 1.0, "resp_chars": 400, "error": False}
             for i, h in enumerate(["obtener_contexto", "get_context", "get_context", "buscar", "search",
                                    "leer_documento", "registrar_sesion", "configurar_pruebas"])]
    log = entorno["tmp"] / "mixto.jsonl"
    log.write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    monkeypatch.setenv("RATIFACT_LOG", str(log))                  # gana sobre MEMORIA_PROYECTOS_LOG
    monkeypatch.setattr(sys, "argv", ["analizar_uso.py"])
    analizar_uso.main()
    salida = capsys.readouterr().out
    tabla = salida.split("\n\n")[1].splitlines()
    conteo = {l.split()[0]: int(l.split()[1]) for l in tabla[1:]}
    assert conteo == {"get_context": 3, "search": 2, "read_document": 1, "log_session": 1, "update_project": 1}
    assert not any(viejo in salida for viejo in ("obtener_contexto", "leer_documento", "registrar_sesion"))
    assert "Chats iniciados: 3" in salida and "Lecturas: 1 vs búsquedas: 2" in salida


# ───────────────────────── docs/upgrade-v1.md ─────────────────────────

def test_guia_de_actualizacion_trae_el_texto_exacto_a_pegar():
    from conftest import RAIZ_REPO
    from ratifact.plantillas import PLANTILLA_AGENTES, PLANTILLA_INSTRUCCIONES
    from ratifact.vocabulario import HERRAMIENTAS_NUEVAS
    guia = (RAIZ_REPO / "docs" / "upgrade-v1.md").read_text(encoding="utf-8")
    assert PLANTILLA_INSTRUCCIONES.format(proyecto="<project>") in guia
    assert PLANTILLA_AGENTES.format(proyecto="<project>") in guia
    assert "ln -sf ~/Projects/.memoria-proyectos/run-task.md ~/.claude/commands/run-task.md" in guia
    for nombre in ("accept_decision", "accept_decisions", "propose_decision", "register_project", *HERRAMIENTAS_NUEVAS):
        assert f"`{nombre}`" in guia, nombre
    for es, en in HERRAMIENTAS_V0.items():
        if es != "configurar_pruebas":
            assert f"| `{es}` | `{en}` |" in guia, es
