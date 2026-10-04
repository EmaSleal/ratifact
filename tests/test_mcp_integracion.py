"""Pruebas de punta a punta por el protocolo MCP (stdio), como lo usan Claude Desktop, Claude Code y Pi."""
import asyncio
import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from conftest import RAIZ_REPO


def _correr(entorno, cuerpo, elicitacion=None):
    async def principal():
        params = StdioServerParameters(command=sys.executable, args=[str(RAIZ_REPO / "servidor.py")],
                                       env={**os.environ, **entorno["env"]})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w, elicitation_callback=elicitacion) as s:
                await s.initialize()
                return await cuerpo(s)
    return asyncio.run(principal())


def _texto(res):
    return res.content[0].text


def test_expone_todas_las_herramientas_y_prompts(srv, proyecto, entorno):
    async def cuerpo(s):
        return ({t.name for t in (await s.list_tools()).tools}, (await s.list_prompts()).prompts)
    herramientas, prompts = _correr(entorno, cuerpo)
    assert {"obtener_contexto", "registrar_decision", "confirmar_decision", "decidir_propuestas",
            "crear_documento", "registrar_proyecto"} <= herramientas
    assert {p.name for p in prompts} == {"cierre", "inicio"}
    assert all(not a.required for p in prompts for a in p.arguments)


def test_prompts_sin_proyecto_no_asumen_ninguno(srv, proyecto, entorno):
    async def cuerpo(s):
        return [(await s.get_prompt(n, {})).messages[0].content.text for n in ("inicio", "cierre")] + \
               [(await s.get_prompt("inicio", {"proyecto": "demo"})).messages[0].content.text]
    inicio, cierre, inicio_demo = _correr(entorno, cuerpo)
    for texto in (inicio, cierre):
        assert "proyecto:" in texto and "No asumas ningún proyecto" in texto
    assert "`demo`" in inicio_demo


def test_escrituras_en_paralelo_no_se_pisan(srv, proyecto, entorno):
    async def cuerpo(s):
        return await asyncio.gather(*[s.call_tool("registrar_decision", {
            "proyecto": "demo", "titulo": f"D{i}", "decision": "d", "justificacion": "j"}) for i in range(5)])
    salidas = [_texto(r) for r in _correr(entorno, cuerpo)]
    assert all("registrada como propuesta" in s for s in salidas)
    ids = sorted(p.name[:7] for p in (proyecto["mem"] / "decisiones").glob("ADR-*.md"))
    assert ids == [f"ADR-00{i}" for i in range(1, 6)]


def test_formulario_sin_soporte_orienta_al_chat(srv, proyecto, entorno):
    srv.registrar_decision(proyecto="demo", titulo="X", decision="d", justificacion="j")

    async def cuerpo(s):
        return _texto(await s.call_tool("decidir_propuestas", {"proyecto": "demo"}))
    assert "no soporta formularios" in _correr(entorno, cuerpo)


def test_formulario_aplica_lo_que_elige_el_usuario(srv, proyecto, entorno):
    for t in "ABCD":
        srv.registrar_decision(proyecto="demo", titulo=t, decision=f"d{t}", justificacion="j")
    respuestas = iter([("accept", {"accion": "confirmar", "comentario": "me gusta"}),
                       ("accept", {"accion": "descartar", "comentario": "no aplica"}),
                       ("accept", {"accion": "ajustar", "comentario": "bajar a 2 semanas"}),
                       ("cancel", None)])

    async def elicitar(contexto, params):
        assert params.requestedSchema["properties"]["accion"]["enum"] == ["confirmar", "descartar", "ajustar", "posponer"]
        accion, datos = next(respuestas)
        return types.ElicitResult(action=accion, content=datos)

    async def cuerpo(s):
        return _texto(await s.call_tool("decidir_propuestas", {"proyecto": "demo"}))
    salida = _correr(entorno, cuerpo, elicitar)
    assert "ADR-001 acordada" in salida and "ADR-002 descartada" in salida
    assert "ADR-003: bajar a 2 semanas" in salida and "Siguen como propuesta: ADR-004" in salida
    assert "[formulario] confirmar — me gusta" in next((proyecto["mem"] / "decisiones").glob("ADR-001*.md")).read_text()
