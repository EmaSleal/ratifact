"""T-015 / ADR-036: política de delegación (required | suggested | off) con precedencia tarea > proyecto > global,
bloque Delegation en update_task(in_progress), rastro `routing:`, línea Workers parseable, aviso blando en in_review,
métrica en `ratifact report` y política en doctor."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from test_upgrade import hogar  # noqa: F401  (fixture: HOME temporal para doctor)

WORKERS_OK = "Workers: explore/haiku×1, write/sonnet×2, verify/sonnet×1"


def _config(entorno) -> Path:
    return Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])


def _settings(entorno, contenido) -> Path:
    ruta = _config(entorno).parent / "settings.json"
    ruta.write_text(contenido if isinstance(contenido, str) else json.dumps(contenido))
    return ruta


def _tarea(mem: Path, id_: str = "T-001") -> Path:
    return next((mem / "tasks").glob(f"{id_}-*.md"))


def _meta(mem: Path, id_: str = "T-001") -> dict:
    from ratifact.registros import _leer_registro
    return _leer_registro(_tarea(mem, id_))[0]


def _en_curso(srv, id_="T-001", **kw) -> str:
    srv.create_task(project="demo", title=f"Algo {id_}", goal="o", acceptance_criteria="c", **kw)
    return srv.update_task(project="demo", id=id_, status="in_progress")


# ───────────────────────── criterio 4: precedencia (unitaria) ─────────────────────────

@pytest.mark.parametrize("tarea,proyecto,global_,esperado", [
    ("", "", "", ("required", "global")),                 # sin nada: required por defecto
    ("", "", "suggested", ("suggested", "global")),
    ("", "off", "required", ("off", "project")),          # proyecto gana al global
    ("", "suggested", "off", ("suggested", "project")),
    ("off", "required", "required", ("off", "task")),     # tarea gana a todo
    ("required", "off", "off", ("required", "task")),
    ("", "", "off", ("off", "global")),
    ("off", "", "", ("off", "task")),
])
def test_precedencia_tarea_proyecto_global(tarea, proyecto, global_, esperado):
    from ratifact.delegacion import resolver
    assert resolver(tarea, proyecto, global_) == esperado


def test_precedencia_con_inherit_en_el_proyecto(srv, proyecto, entorno):
    from ratifact.delegacion import efectiva
    _settings(entorno, {"delegation": "suggested"})
    srv.update_project(name="demo", delegation="off")
    assert efectiva(json.loads(_config(entorno).read_text())["demo"])[:2] == ("off", "project")
    srv.update_project(name="demo", delegation="inherit")
    entrada = json.loads(_config(entorno).read_text())["demo"]
    assert "delegation" not in entrada
    assert efectiva(entrada)[:2] == ("suggested", "global")
    assert efectiva(entrada, {"delegation": "required"})[:2] == ("required", "task")


# ───────────────────────── criterios 1 y 2: configuración ─────────────────────────

def test_settings_acepta_delegation_junto_a_models(srv, proyecto, entorno):
    _settings(entorno, {"models": {"write": "sonnet"}, "delegation": "suggested"})
    salida = _en_curso(srv)
    assert "Delegation (suggested, set by global policy)" in salida and "- write: sonnet (global)" in salida


def test_settings_con_delegation_invalida_avisa_y_usa_required(srv, proyecto, entorno):
    _settings(entorno, {"delegation": "always"})
    salida = _en_curso(srv)
    assert salida.startswith("T-001 → in_progress")
    assert "Delegation (required, set by global policy" in salida
    assert "⚠ settings.json: invalid `delegation` value 'always'" in salida
    assert not srv.get_context(project="demo").startswith("ERROR")


def test_update_project_delegation_guarda_quita_y_valida(srv, proyecto, entorno):
    assert "delegation: off" in srv.update_project(name="demo", delegation="off")
    datos = json.loads(_config(entorno).read_text())
    assert list(datos) == ["demo"] and datos["demo"]["delegation"] == "off"     # ADR-035: sin claves globales
    antes = _config(entorno).read_text()
    salida = srv.update_project(name="demo", delegation="sometimes")
    assert salida.startswith("ERROR") and "required, suggested, off, inherit" in salida
    assert _config(entorno).read_text() == antes
    srv.update_project(name="demo", delegation="inherit")
    assert "delegation" not in json.loads(_config(entorno).read_text())["demo"]
    assert "`delegation`" in srv.update_project(name="demo")


# ───────────────────────── criterio 3: create_task y amend_task ─────────────────────────

def test_create_task_guarda_delegation_solo_si_se_da(srv, proyecto):
    srv.create_task(project="demo", title="Uno", goal="o", acceptance_criteria="c", delegation="off")
    srv.create_task(project="demo", title="Dos", goal="o", acceptance_criteria="c")
    assert "delegation: off\n" in _tarea(proyecto["mem"], "T-001").read_text()
    assert "delegation" not in _tarea(proyecto["mem"], "T-002").read_text()
    salida = srv.create_task(project="demo", title="Tres", goal="o", acceptance_criteria="c", delegation="suggested")
    assert salida.startswith("ERROR") and "required or off" in salida
    assert len(list((proyecto["mem"] / "tasks").glob("T-*.md"))) == 2


def test_amend_task_fija_delegation_en_todo_y_changes_requested(srv, proyecto):
    srv.create_task(project="demo", title="Uno", goal="o", acceptance_criteria="c")
    salida = srv.amend_task(project="demo", id="T-001", delegation="off")
    assert "amended (delegation: off)" in salida
    texto = _tarea(proyecto["mem"]).read_text()
    assert "delegation: off\n" in texto and "### Amendment" not in texto
    assert "already has delegation: off" in srv.amend_task(project="demo", id="T-001", delegation="off")
    srv.amend_task(project="demo", id="T-001", notes="nota", delegation="required")
    texto = _tarea(proyecto["mem"]).read_text()
    assert "delegation: required\n" in texto and "### Amendment 1" in texto
    srv.update_task(project="demo", id="T-001", status="in_progress")
    salida = srv.amend_task(project="demo", id="T-001", delegation="off")
    assert salida.startswith("ERROR") and "todo or changes_requested" in salida
    srv.update_task(project="demo", id="T-001", status="in_review", result=WORKERS_OK)
    srv.request_changes(project="demo", id="T-001", findings="falta algo")
    assert "delegation: off" in srv.amend_task(project="demo", id="T-001", delegation="off")
    assert srv.amend_task(project="demo", id="T-001", delegation="sometimes").startswith("ERROR")


# ───────────────────────── criterios 5, 6 y 8: bloque de delegación ─────────────────────────

def test_sin_configuracion_el_bloque_required_es_imperativo(srv, proyecto):
    salida = _en_curso(srv)
    bloque = salida[salida.index("Delegation (required"):]
    assert "if you have" not in bloque and "otherwise implement directly" not in bloque
    for texto in ("orchestrate", "do not write the code yourself", "explore worker (model: session model)",
                  "write workers (model: session model)", "verify worker that did not see the implementation",
                  "full task spec", "complete diff", "Before update_task(in_review)", "fails verification twice",
                  "`escalated: write`", "Workers:"):
        assert texto in bloque, texto
    assert "Model routing" not in salida


def test_required_usa_los_modelos_de_model_routing(srv, proyecto, entorno):
    _settings(entorno, {"models": {"explore": "haiku", "write": "sonnet"}})
    salida = _en_curso(srv)
    routing = salida[salida.index("Model routing"):salida.index("Delegation")]
    assert "explore worker (model: haiku)" in salida and "write workers (model: sonnet)" in salida
    assert "verify worker that did not see the implementation (model: session model)" in salida
    assert routing.startswith("Model routing (configured by the user):\n- explore: haiku (global)")


def test_model_routing_igual_en_las_tres_politicas(srv, proyecto, entorno):
    _settings(entorno, {"models": {"write": "sonnet"}})
    bloques = {}
    for i, politica in enumerate(("required", "suggested", "off"), 1):
        srv.update_project(name="demo", delegation=politica)
        salida = _en_curso(srv, f"T-00{i}")
        inicio = salida.index("Model routing")
        fin = salida.index("Delegation") if "Delegation" in salida else len(salida)
        bloques[politica] = salida[inicio:fin].strip()
        if politica == "suggested":
            assert "Delegation (suggested" in salida and "you may delegate" in salida
        if politica == "off":
            assert "Delegation" not in salida
    assert bloques["required"] == bloques["suggested"] == bloques["off"]


def test_tarea_off_gana_al_global_required(srv, proyecto, entorno):
    _settings(entorno, {"delegation": "required"})
    salida = _en_curso(srv, delegation="off")
    assert "Delegation" not in salida


# ───────────────────────── criterio 12: routing en el frontmatter ─────────────────────────

def test_routing_se_graba_y_se_sobrescribe_en_reejecuciones(srv, proyecto, entorno):
    _settings(entorno, {"models": {"explore": "haiku", "write": "sonnet", "verify": "sonnet"}})
    _en_curso(srv)
    assert _meta(proyecto["mem"])["routing"].startswith("explore=haiku,write=sonnet,verify=sonnet · delegation=required · ")
    texto = _tarea(proyecto["mem"]).read_text()
    assert "Delegation (" not in texto and "Model routing" not in texto          # la guía no se escribe
    srv.update_task(project="demo", id="T-001", status="failed", result="falló")
    _settings(entorno, {"delegation": "suggested"})
    srv.update_task(project="demo", id="T-001", status="in_progress")
    assert _meta(proyecto["mem"])["routing"].startswith("explore=session,write=session,verify=session · "
                                                        "delegation=suggested · build=")
    assert _tarea(proyecto["mem"]).read_text().count("routing:") == 1


# ───────────────────────── criterio 10: parser de la línea Workers ─────────────────────────

def test_parser_reconoce_las_formas_validas():
    from ratifact.delegacion import parsear_workers
    t = parsear_workers("Workers: explore/haiku×1, write/sonnet×2, verify/sonnet×1")
    assert t.roles == [("explore", "haiku", 1), ("write", "sonnet", 2), ("verify", "sonnet", 1)] and t.total == 4
    t = parsear_workers("Workers: write/sonnet×1, escalated: write")
    assert t.roles == [("write", "sonnet", 1)] and t.escalados == ["write"]
    t = parsear_workers("Workers: none — reason: tarea de una línea")
    assert t.total == 0 and t.motivo == "tarea de una línea"
    assert parsear_workers("- Workers: write/claude-sonnet-5-5×1").roles == [("write", "claude-sonnet-5-5", 1)]


@pytest.mark.parametrize("linea", ["Workers: none", "Workers: none — reason:", "Workers:", "Workers: write/sonnet",
                                   "Workers: planner/haiku×1", "Workers: write/sonnet×0", "Workers: escalated: write",
                                   "Workers: write/sonnet×1; verify/sonnet×1", "Integrations used: none"])
def test_parser_rechaza_lineas_mal_formadas(linea):
    from ratifact.delegacion import parsear_workers
    with pytest.raises(ValueError):
        parsear_workers(linea)


# ───────────────────────── criterio 11: validación blanda en in_review ─────────────────────────

@pytest.mark.parametrize("resultado,falta", [("hecho\nIntegrations used: none", "has no `Workers:` line"),
                                             ("Workers: write/sonnet", "`Workers:` line is invalid"),
                                             ("Workers: none", "needs a reason")])
def test_in_review_required_sin_workers_valida_avisa(srv, proyecto, resultado, falta):
    _en_curso(srv)
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=resultado)
    assert salida.startswith("T-001 → in_review · commit")
    assert "⚠ Delegation was required" in salida and falta in salida
    assert _meta(proyecto["mem"])["status"] == "in_review"


@pytest.mark.parametrize("resultado", [WORKERS_OK, "Workers: none — reason: una línea"])
def test_in_review_required_con_workers_valida_no_avisa(srv, proyecto, resultado):
    _en_curso(srv)
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result=f"hecho\n{resultado}")
    assert re.fullmatch(r"T-001 → in_review · commit \S+", salida), salida


@pytest.mark.parametrize("politica", ["suggested", "off"])
def test_in_review_sin_required_no_avisa(srv, proyecto, politica):
    srv.update_project(name="demo", delegation=politica)
    _en_curso(srv)
    salida = srv.update_task(project="demo", id="T-001", status="in_review", result="hecho")
    assert re.fullmatch(r"T-001 → in_review · commit \S+", salida), salida


# ───────────────────────── criterio 13: report ─────────────────────────

def test_report_mide_cumplimiento_y_compara(srv, proyecto, entorno):
    from ratifact.informe_memoria import indicador_delegacion
    srv.create_task(project="demo", title="Vieja", goal="o", acceptance_criteria="c")       # sin routing
    _en_curso(srv, "T-002")
    srv.update_task(project="demo", id="T-002", status="in_review", result=WORKERS_OK)
    _en_curso(srv, "T-003")
    srv.update_task(project="demo", id="T-003", status="in_review", result="Workers: write/sonnet×1, escalated: write")
    srv.request_changes(project="demo", id="T-003", findings="x")
    _en_curso(srv, "T-004")
    srv.update_task(project="demo", id="T-004", status="in_review", result="sin línea")
    srv.request_changes(project="demo", id="T-004", findings="y")
    srv.update_task(project="demo", id="T-004", status="in_progress")
    srv.update_task(project="demo", id="T-004", status="in_review", result="Workers: none — reason: trivial")
    srv.request_changes(project="demo", id="T-004", findings="z")
    _en_curso(srv, "T-005", delegation="off")
    lineas = indicador_delegacion(dt.datetime.now() - dt.timedelta(days=7), "demo")
    assert lineas[0] == ("  demo: 4 tareas con routing · required 3 · con trabajadores 2 · cumplimiento 67 % · "
                         "escalamientos 1 · sin routing (anteriores a la política): 1")
    assert re.fullmatch(r"    delegadas: 2 tareas · revisiones \(changes_requested\) promedio 0\.5 · "
                        r"in_progress → in_review promedio \d+\.\d h", lineas[1]), lineas[1]
    assert re.fullmatch(r"    no delegadas: 2 tareas · revisiones \(changes_requested\) promedio 1\.0 · "
                        r"in_progress → in_review promedio \d+\.\d h", lineas[2]), lineas[2]


def test_report_imprime_la_seccion(srv, proyecto, entorno, monkeypatch, capsys):
    from test_analizar_uso import _correr, _log_filas
    _en_curso(srv)
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "search", "resp_chars": 10}])
    _correr(monkeypatch, "--log", str(log))
    salida = capsys.readouterr().out
    seccion = salida.split("Delegación (ADR-036)")[1]
    assert "demo: 1 tareas con routing · required 1 · con trabajadores 0 · cumplimiento 0 %" in seccion


# ───────────────────────── criterio 14: doctor ─────────────────────────

def test_doctor_muestra_la_politica_efectiva(srv, proyecto, entorno, hogar):
    from ratifact import doctor
    texto = "\n".join(doctor.informe(procesos=lambda: [])[0])
    assert "    models: session default · delegation=required (global)" in texto
    _settings(entorno, {"delegation": "suggested"})
    srv.update_project(name="demo", delegation="off")
    lineas, acciones = doctor.informe(procesos=lambda: [])
    texto = "\n".join(lineas)
    assert "delegation=off (project)" in texto and "delegation: suggested" in texto
    _settings(entorno, {"delegation": "always"})
    lineas, acciones = doctor.informe(procesos=lambda: [])
    assert any("settings.json" in a and "always" in a for a in acciones), acciones


# ───────────────────────── criterio 9: skill ─────────────────────────

def test_skill_pide_linea_workers_separada_de_integraciones(srv):
    from conftest import RAIZ_REPO
    for ruta in (RAIZ_REPO / "ratifact" / "skills" / "run-task" / "SKILL.md", RAIZ_REPO / "run-task.md"):
        skill = ruta.read_text(encoding="utf-8")
        ejecutar = skill.split("## 2. Execute")[1].split("## 3.")[0]
        cerrar = skill.split("## 4. Close")[1]
        assert '"Delegation"' in ejecutar
        assert "`Workers: <role>/<model>×<n>, …`" in cerrar and "`Workers: none — reason: <why>`" in cerrar
        assert "escalated: write" in cerrar
        integraciones = re.search(r"`Integrations used: …`[^.]*\.", cerrar).group(0)
        assert not re.search(r"\b(explore|write|verify)/", integraciones)
    alias = (RAIZ_REPO / "ratifact" / "skills" / "tarea" / "SKILL.md").read_text(encoding="utf-8")
    assert "Workers:" in alias
