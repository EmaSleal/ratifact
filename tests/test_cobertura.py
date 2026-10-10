"""ADR-009, criterio 1: la suite debe cubrir todas las herramientas. Falla si se agrega una sin pruebas."""
import re
from pathlib import Path

from conftest import RAIZ_REPO


def test_cada_herramienta_tiene_al_menos_una_prueba():
    codigo = "\n".join(p.read_text() for p in [RAIZ_REPO / "servidor.py", *sorted((RAIZ_REPO / "ratifact").rglob("*.py"))])
    herramientas = set(re.findall(r"@herramienta(?:_async)?\n(?:async )?def (\w+)\(", codigo))
    pruebas = "\n".join(p.read_text() for p in Path(__file__).parent.glob("test_*.py") if p.name != Path(__file__).name)
    sin_prueba = sorted(h for h in herramientas if h not in pruebas)
    assert len(herramientas) >= 20
    assert not sin_prueba, f"Herramientas sin pruebas: {sin_prueba}"
