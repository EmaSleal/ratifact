"""T-019 (ADR-042): el guion ASCII separa nota y motivo solo cuando lo sigue `note:` / `reason:`; la definición ampliada
de rework y el separador aparecen en las guías y la documentación."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("ascii_,canonico", [
    ("Workers: write/sonnet×1 - note: x", "Workers: write/sonnet×1 — note: x"),
    ("Workers: write/sonnet×1 -- note: x", "Workers: write/sonnet×1 — note: x"),
    ("Workers: write/sonnet×1, rework: write×1 -- note: x", "Workers: write/sonnet×1, rework: write×1 — note: x"),
    ("Workers: write/sonnet×1, rework: write×1 - note: x", "Workers: write/sonnet×1, rework: write×1 – note: x"),
    ("Workers: write/claude-sonnet-5-5×1 - note: a - b", "Workers: write/claude-sonnet-5-5×1 — note: a - b"),
    ("Workers: none - reason: trivial", "Workers: none — reason: trivial"),
    ("Workers: none -- reason: trivial", "Workers: none — reason: trivial"),
])
def test_guion_ascii_equivale_al_canonico(ascii_, canonico):
    from ratifact.delegacion import parsear_workers
    assert parsear_workers(ascii_) == parsear_workers(canonico)


def test_nota_extraida_igual():
    from ratifact.delegacion import parsear_workers
    t = parsear_workers("Workers: write/sonnet×1, rework: write×1 -- note: x")
    assert (t.roles, t.reenvios, t.nota) == ([("write", "sonnet", 1)], {"write": 1}, "x")


@pytest.mark.parametrize("linea", [
    "Workers: write/sonnet×1 - resumed once",
    "Workers: write/sonnet×1 -- resumed once",
    "Workers: write/sonnet×1 - extra",
    "Workers: none - trivial",
    "Workers: write/sonnet×1-note: x",
])
def test_guion_ascii_fuera_de_note_sigue_invalido(linea):
    from ratifact.delegacion import parsear_workers
    with pytest.raises(ValueError):
        parsear_workers(linea)


def test_modelo_con_guiones_sigue_parseando():
    from ratifact.delegacion import parsear_workers
    assert parsear_workers("Workers: write/claude-sonnet-5-5×1").roles == [("write", "claude-sonnet-5-5", 1)]


def test_propuesta_sigue_usando_raya_canonica():
    from ratifact.delegacion import proponer_workers
    p = proponer_workers("Workers: write/sonnet×1 (resumed once) - note: x")
    assert p is not None and " — note: " in p and " - note:" not in p


# ───────────────────────── documentación ─────────────────────────

SKILLS = [RAIZ / "ratifact/skills/run-task/SKILL.md", RAIZ / "run-task.md"]
DOCS = [RAIZ / "README.md", RAIZ / "LEEME.md", RAIZ / "docs/optional-integrations.md"]


@pytest.mark.parametrize("ruta", SKILLS + DOCS, ids=lambda p: p.name)
def test_docs_definicion_ampliada_y_separador(ruta):
    t = ruta.read_text(encoding="utf-8")
    assert "ADR-042" in t or ruta in SKILLS
    assert "diff review" in t or "revisión del diff" in t
    assert "write/sonnet×2" in t
    assert "- note:" in t and "- reason:" in t


@pytest.mark.parametrize("ruta", DOCS, ids=lambda p: p.name)
def test_docs_citan_adr042(ruta):
    assert "ADR-042" in ruta.read_text(encoding="utf-8")


def test_skill_ejemplo_de_rework_por_diff():
    for ruta in SKILLS:
        t = ruta.read_text(encoding="utf-8")
        assert re.search(r"verifier\*?\*? or by the orchestrator'?s diff review", t), ruta
