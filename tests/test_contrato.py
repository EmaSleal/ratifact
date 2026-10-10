"""Contrato de herramientas y prompts: nombre, descripción y esquema de entrada de cada herramienta registrada, y
nombre, descripción y argumentos de cada prompt. Se compara contra una instantánea (contrato_herramientas.json):
cualquier cambio en lo que ve el cliente MCP rompe esta prueba.

Para regenerar la instantánea a propósito (solo si el cambio de contrato es intencional):
    uv run --with pytest --with "mcp>=1.2,<2" python tests/test_contrato.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

INSTANTANEA = Path(__file__).resolve().parent / "contrato_herramientas.json"


def contrato(mcp) -> dict:
    herramientas = asyncio.run(mcp.list_tools())
    prompts = asyncio.run(mcp.list_prompts())
    return {
        "herramientas": [
            {"nombre": t.name, "descripcion": t.description, "esquema_entrada": t.inputSchema}
            for t in sorted(herramientas, key=lambda t: t.name)
        ],
        "prompts": [
            {"nombre": p.name, "descripcion": p.description,
             "argumentos": [{"nombre": a.name, "descripcion": a.description, "requerido": a.required}
                            for a in (p.arguments or [])]}
            for p in sorted(prompts, key=lambda p: p.name)
        ],
    }


def serializar(datos: dict) -> str:
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def test_contrato_de_herramientas_y_prompts_sin_cambios(srv):
    actual = serializar(contrato(srv.mcp))
    esperado = INSTANTANEA.read_text(encoding="utf-8")
    assert actual == esperado, "El contrato MCP cambió respecto de tests/contrato_herramientas.json"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(INSTANTANEA.parents[1]))
    import servidor
    INSTANTANEA.write_text(serializar(contrato(servidor.mcp)), encoding="utf-8")
    print(f"Instantánea escrita en {INSTANTANEA}")
