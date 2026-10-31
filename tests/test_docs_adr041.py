"""ADR-041 (T-018): the skill and the docs describe the extended Workers format."""
import re
from pathlib import Path

RAIZ = Path(__file__).parent.parent
SKILL = RAIZ / "ratifact" / "skills" / "run-task" / "SKILL.md"


def _leer(ruta):
    return Path(ruta).read_text(encoding="utf-8")


def test_skill_y_run_task_identicos_y_documentan_el_formato():
    assert _leer(SKILL) == _leer(RAIZ / "run-task.md")
    texto = _leer(SKILL)
    for clave in ("rework:", "— note:", "escalated:", "No parentheses"):
        assert clave in texto, clave
    ejemplos = [l for l in texto.splitlines() if l.strip().startswith("- `Workers:") and "rework:" in l]
    assert len(ejemplos) >= 2
    assert 'send **only** the corrected line' in texto
    assert 'update_task("<project>", "$ARGUMENTS", "in_review", result="Workers: …")' in texto


def test_docs_mencionan_formato_cliente_y_tasa_de_retrabajo():
    for doc in ("README.md", "LEEME.md", "docs/optional-integrations.md"):
        texto = _leer(RAIZ / doc)
        for clave in ("rework:", "note:", "client=", "ADR-041"):
            assert clave in texto, (doc, clave)
        assert re.search(r"rework rate|tasa de retrabajo", texto), doc


def test_alias_tarea_menciona_rework():
    assert "rework" in _leer(RAIZ / "ratifact" / "skills" / "tarea" / "SKILL.md")
