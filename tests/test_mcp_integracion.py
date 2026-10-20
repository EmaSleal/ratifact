"""Pruebas de punta a punta por el protocolo MCP (stdio), como lo usan Claude Desktop, Claude Code y Pi."""
import asyncio
import os
import shutil
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
    assert {"get_context", "propose_decision", "accept_decision", "decide_proposals",
            "create_document", "register_project"} <= herramientas
    assert {p.name for p in prompts} == {"close", "start"}
    assert all(not a.required for p in prompts for a in p.arguments)


def test_prompts_sin_proyecto_no_asumen_ninguno(srv, proyecto, entorno):
    async def cuerpo(s):
        return [(await s.get_prompt(n, {})).messages[0].content.text for n in ("start", "close")] + \
               [(await s.get_prompt("start", {"project": "demo"})).messages[0].content.text]
    inicio, cierre, inicio_demo = _correr(entorno, cuerpo)
    for texto in (inicio, cierre):
        assert "project:" in texto and "Never assume a default project" in texto
    assert "`demo`" in inicio_demo


def test_escrituras_en_paralelo_no_se_pisan(srv, proyecto, entorno):
    async def cuerpo(s):
        return await asyncio.gather(*[s.call_tool("propose_decision", {
            "project": "demo", "title": f"D{i}", "decision": "d", "rationale": "j"}) for i in range(5)])
    salidas = [_texto(r) for r in _correr(entorno, cuerpo)]
    assert all("recorded as proposed" in s for s in salidas)
    ids = sorted(p.name[:7] for p in (proyecto["mem"] / "decisions").glob("ADR-*.md"))
    assert ids == [f"ADR-00{i}" for i in range(1, 6)]


def test_formulario_sin_soporte_orienta_al_chat(srv, proyecto, entorno):
    srv.propose_decision(project="demo", title="X", decision="d", rationale="j")

    async def cuerpo(s):
        return _texto(await s.call_tool("decide_proposals", {"project": "demo"}))
    assert "does not support MCP forms" in _correr(entorno, cuerpo)


def test_formulario_aplica_lo_que_elige_el_usuario(srv, proyecto, entorno):
    for t in "ABCD":
        srv.propose_decision(project="demo", title=t, decision=f"d{t}", rationale="j")
    respuestas = iter([("accept", {"action": "accept", "comment": "me gusta"}),
                       ("accept", {"action": "reject", "comment": "no aplica"}),
                       ("accept", {"action": "adjust", "comment": "bajar a 2 semanas"}),
                       ("cancel", None)])

    async def elicitar(contexto, params):
        assert params.requestedSchema["properties"]["action"]["enum"] == ["accept", "reject", "adjust", "postpone"]
        accion, datos = next(respuestas)
        return types.ElicitResult(action=accion, content=datos)

    async def cuerpo(s):
        return _texto(await s.call_tool("decide_proposals", {"project": "demo"}))
    salida = _correr(entorno, cuerpo, elicitar)
    assert "ADR-001 → accepted" in salida and "ADR-002 → rejected" in salida
    assert "ADR-003: bajar a 2 semanas" in salida and "Still proposed: ADR-004" in salida
    assert "[form] accept — me gusta" in next((proyecto["mem"] / "decisions").glob("ADR-001*.md")).read_text()


def test_confirmar_lote_acepta_lista_por_mcp(srv, proyecto, entorno):
    for t in "AB":
        srv.propose_decision(project="demo", title=t, decision="d", rationale="j")

    async def cuerpo(s):
        esquema = next(t for t in (await s.list_tools()).tools if t.name == "accept_decisions").inputSchema
        res = await s.call_tool("accept_decisions",
                                {"project": "demo", "ids": ["ADR-001", "ADR-002"], "user_quote": "confirmo ambas"})
        return esquema, _texto(res)
    esquema, salida = _correr(entorno, cuerpo)
    assert esquema["properties"]["ids"]["type"] == "array"
    assert "2 → accepted" in salida


@pytest.mark.parametrize("comando", [[sys.executable], ["uv", "run", "--script"]], ids=["python", "uv"])
def test_arranca_desde_cualquier_carpeta(entorno, tmp_path, comando):
    """servidor.py importa el paquete ratifact aunque el cwd esté fuera del repositorio."""
    if comando[0] == "uv" and not shutil.which("uv"):
        pytest.skip("uv no está instalado")
    cwd = tmp_path / "otra_carpeta"
    cwd.mkdir()
    assert RAIZ_REPO not in cwd.resolve().parents

    async def principal():
        params = StdioServerParameters(command=comando[0], args=[*comando[1:], str(RAIZ_REPO / "servidor.py")],
                                       env={**os.environ, **entorno["env"]}, cwd=str(cwd))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return {t.name for t in (await s.list_tools()).tools}
    herramientas = asyncio.run(principal())
    assert len(herramientas) == 28 and {"get_context", "register_project"} <= herramientas
