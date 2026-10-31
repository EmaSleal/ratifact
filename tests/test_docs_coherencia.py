"""T-021: la documentación pública no se desalinea del código ni del contrato de herramientas."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SKILL = RAIZ / "ratifact/skills/run-task/SKILL.md"
DOCS = sorted((RAIZ / "docs").glob("*.md"))
PUBLICOS = [RAIZ / "README.md", RAIZ / "LEEME.md", *DOCS]
CONTRATO = RAIZ / "tests/contrato_herramientas.json"


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


# ── separador de la nota (un solo párrafo coherente) ──

FRASES_VIEJAS = ("everything after ` — `", "todo lo que sigue a ` — `")


@pytest.mark.parametrize("ruta", [RAIZ / "README.md", RAIZ / "LEEME.md", RAIZ / "docs/optional-integrations.md", SKILL],
                         ids=lambda p: p.name)
def test_sin_la_frase_vieja_del_separador(ruta):
    t = _leer(ruta)
    for frase in FRASES_VIEJAS:
        assert frase not in t, (ruta.name, frase)


def test_skill_define_el_separador_una_sola_vez():
    t = _leer(SKILL)
    assert " — note:" in t and "` - note:` / ` -- note:`" in t
    assert len(re.findall(r"canonical", t.split("**`Workers:` format:**")[1].split("\n")[0])) == 1


# ── número de herramientas ──

def test_numero_de_herramientas_coincide_con_el_contrato():
    n = len(json.loads(_leer(CONTRATO))["herramientas"])
    for ruta in (RAIZ / "README.md", RAIZ / "LEEME.md", RAIZ / "docs/upgrade-v1.md"):
        t = _leer(ruta)
        for m in re.finditer(r"(\d+)\s+(?:tools|herramientas)\b", t):
            assert int(m.group(1)) == n, (ruta.name, m.group(0), n)
    assert re.search(rf"\b{n} tools\b", _leer(RAIZ / "README.md"))


# ── sin cifras de pruebas ──

CIFRAS = re.compile(r"\b\d+\s+(?:passed|tests? pass(?:ed|ing)?|pruebas? pas(?:an|aron|adas)|pruebas verdes)\b", re.I)


@pytest.mark.parametrize("ruta", PUBLICOS, ids=lambda p: p.name)
def test_sin_cifras_de_pruebas(ruta):
    assert not CIFRAS.search(_leer(ruta)), ruta.name


# ── /tarea retirado ──
# Amplía la cobertura de T-017 (que mira la salida de project_instructions y el árbol del paquete): aquí se barren
# los documentos públicos y la skill, que ninguna prueba cubría.

@pytest.mark.parametrize("ruta", [r for r in PUBLICOS if r.name != "upgrade-v1.md"] + [SKILL], ids=lambda p: p.name)
def test_tarea_no_figura_como_comando_vigente(ruta):
    assert not re.search(r"(?<![\w/])/tarea\b", _leer(ruta)), ruta.name


# ── enlaces del README (long_description de PyPI) ──

def test_readme_sin_enlaces_relativos_a_archivos_del_repositorio():
    for destino in re.findall(r"\]\(([^)\s]+)\)", _leer(RAIZ / "README.md")):
        assert re.match(r"(https?://|#|mailto:)", destino), destino


# ── sin identificadores ADR en el texto público ──

ADR = re.compile(r"ADR[- ]?\d{3}")


@pytest.mark.parametrize("ruta", PUBLICOS + [SKILL], ids=lambda p: p.name)
def test_sin_identificadores_adr_en_la_documentacion(ruta):
    assert not ADR.findall(_leer(ruta)), ruta.name


def _descripciones(nodo):
    """Todas las cadenas 'description'/'descripcion' de un objeto JSON anidado."""
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            if k in ("description", "descripcion") and isinstance(v, str):
                yield v
            else:
                yield from _descripciones(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _descripciones(v)


def test_sin_identificadores_adr_en_las_descripciones_del_contrato():
    malas = [d[:80] for d in _descripciones(json.loads(_leer(CONTRATO))) if ADR.search(d)]
    assert not malas, malas


# ── sin identificadores del historial de desarrollo (T-NNN / P-NNN) ──

ID_HISTORIAL = re.compile(r"\b[TtPp]-\d+\b")
IDS_PERMITIDOS = {("T", 1), ("T", 2), ("P", 1)}
PUBLICOS_Y_SKILL = [*PUBLICOS, SKILL]


def _ids_historicos(texto: str):
    for n, linea in enumerate(texto.splitlines(), 1):
        for m in ID_HISTORIAL.finditer(linea):
            clave = (m.group(0)[0].upper(), int(m.group(0)[2:]))
            if clave not in IDS_PERMITIDOS:
                yield n, m.group(0)


@pytest.mark.parametrize("ruta", PUBLICOS_Y_SKILL, ids=lambda p: p.name)
def test_sin_ids_del_historial(ruta):
    ofensores = [f"{ruta.name}:{n} {i}" for n, i in _ids_historicos(_leer(ruta))]
    assert not ofensores, ofensores


# Marcadores de formato permitidos en las descripciones del contrato (ejemplos de entrada).
FORMATOS_PERMITIDOS = {"P-036", "P-037", "T-24", "T-024", "T-1"}


def test_descripciones_del_contrato_sin_ids_del_historial():
    ofensores = []

    def recorrer(nodo, ruta=""):
        if isinstance(nodo, dict):
            for k, v in nodo.items():
                if k == "descripcion" and isinstance(v, str):
                    for m in ID_HISTORIAL.finditer(v):
                        if m.group(0).upper() not in FORMATOS_PERMITIDOS:
                            ofensores.append((ruta, m.group(0)))
                else:
                    recorrer(v, f"{ruta}/{k}")
        elif isinstance(nodo, list):
            for i, v in enumerate(nodo):
                recorrer(v, f"{ruta}[{i}]")

    recorrer(json.loads(_leer(CONTRATO)))
    assert not ofensores, ofensores
