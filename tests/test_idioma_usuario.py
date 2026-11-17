"""T-023 (P-035, amendment 1): la regla de idioma del usuario es una constante única y aparece en los lugares
obligatorios: instructions del servidor, skill run-task, read_task y update_task(in_progress)."""
from __future__ import annotations

import json

from conftest import RAIZ_REPO

SKILL = RAIZ_REPO / "ratifact" / "skills" / "run-task" / "SKILL.md"


def test_constante_unica_en_ingles():
    from ratifact import idioma
    regla = idioma.REGLA_IDIOMA
    assert "language" in regla and "user wrote" in regla
    for texto in ("/run-task", "tool descriptions", "ratifact responses", "worker reports", "Content language"):
        assert texto in regla, texto
    assert "content of the records you save in ratifact follows the \"Content language\" line" in regla
    assert regla == regla.strip() and "\n" not in regla


def test_regla_en_instructions_del_servidor(srv):
    from ratifact import idioma
    assert idioma.REGLA_IDIOMA in srv.mcp.instructions


def test_regla_en_la_skill_y_copias_identicas():
    from ratifact import idioma
    texto = SKILL.read_text(encoding="utf-8")
    assert idioma.REGLA_IDIOMA in texto
    # al principio, antes del paso 1 (criterio 20)
    assert texto.index(idioma.REGLA_IDIOMA) < texto.index("## 1. Prepare")
    otra = RAIZ_REPO / "skills" / "run-task" / "SKILL.md"
    assert otra.read_bytes() == SKILL.read_bytes()
    assert (RAIZ_REPO / "run-task.md").read_bytes() == SKILL.read_bytes()


def _con_idioma(proyecto, codigo):
    ruta = proyecto["mem"] / "schema.json"
    datos = json.loads(ruta.read_text())
    datos["content_language"] = codigo
    ruta.write_text(json.dumps(datos))


def test_read_task_trae_idioma_y_regla_corta_e_in_progress_la_completa(srv, proyecto):
    from ratifact import idioma
    _con_idioma(proyecto, "es")
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    leida = srv.read_task(project="demo", id="T-001")
    en_curso = srv.update_task(project="demo", id="T-001", status="in_progress")
    assert idioma.linea_contenido("es") in leida and idioma.REGLA_IDIOMA_CORTA in leida
    assert idioma.REGLA_IDIOMA not in leida and len(idioma.REGLA_IDIOMA_CORTA) <= 250
    assert "\n" not in idioma.REGLA_IDIOMA_CORTA
    assert "Content language: es" in en_curso and idioma.REGLA_IDIOMA in en_curso


def test_skill_pide_encargos_autosuficientes_sin_llamadas_a_ratifact():
    texto = SKILL.read_text(encoding="utf-8")
    assert "self-sufficient" in texto and "must not call ratifact tools" in texto


def test_plantilla_de_agentes_dice_que_el_trabajador_no_llama_a_ratifact():
    from ratifact.plantillas import PLANTILLA_AGENTES, PLANTILLA_AGENTES_V2
    assert "A worker delegated by `/run-task` does not call `get_context` or `read_task`" in PLANTILLA_AGENTES
    assert PLANTILLA_AGENTES.startswith(PLANTILLA_AGENTES_V2) and PLANTILLA_AGENTES != PLANTILLA_AGENTES_V2


def test_get_context_usa_la_misma_linea(srv, proyecto):
    from ratifact import idioma
    _con_idioma(proyecto, "es")
    assert idioma.linea_contenido("es") in srv.get_context(project="demo")
