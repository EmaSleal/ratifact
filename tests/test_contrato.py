"""Contrato de herramientas y prompts: nombre, descripción y esquema de entrada de cada herramienta registrada, y
nombre, descripción y argumentos de cada prompt. Se compara contra una instantánea (contrato_herramientas.json):
cualquier cambio en lo que ve el cliente MCP rompe esta prueba.

Para regenerar la instantánea a propósito (solo si el cambio de contrato es intencional):
    uv run --with pytest --with "mcp>=1.2,<2" python tests/test_contrato.py
Es el único comando de regeneración: normaliza las descripciones (inspect.cleandoc) y escribe con formato fijo, así
dos regeneraciones seguidas dan los mismos bytes.
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
    """Formato fijo de la instantánea: claves ordenadas, sangría 2, sin escapar ASCII y salto de línea final."""
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _sin_sangria(datos: dict) -> dict:
    """Descripciones con inspect.cleandoc: Python 3.13+ quita la sangría de los docstrings al compilar, así que el
    texto crudo depende de la versión de Python que corre las pruebas (no del contrato)."""
    import inspect
    return {grupo: [{**e, "descripcion": inspect.cleandoc(e["descripcion"] or "")} for e in elementos]
            for grupo, elementos in datos.items()}


def instantanea(mcp) -> str:
    """Texto exacto de tests/contrato_herramientas.json: contrato normalizado y serializado. Lo usan la regeneración
    y la prueba, así que no dependen de la sangría del docstring del intérprete."""
    return serializar(_sin_sangria(contrato(mcp)))


def test_contrato_de_herramientas_y_prompts_sin_cambios(srv):
    actual = instantanea(srv.mcp)
    esperado = serializar(_sin_sangria(json.loads(INSTANTANEA.read_text(encoding="utf-8"))))
    assert actual == esperado, "El contrato MCP cambió respecto de tests/contrato_herramientas.json"


def test_instantanea_regeneracion_determinista(srv):
    """T-019: regenerar dos veces da los mismos bytes, y el archivo versionado es exactamente esa salida (regenerarlo
    no cambia la sangría de descripciones ajenas al cambio)."""
    primera, segunda = instantanea(srv.mcp), instantanea(srv.mcp)
    assert primera == segunda
    assert INSTANTANEA.read_bytes() == primera.encode("utf-8"), \
        "tests/contrato_herramientas.json no está normalizado: regenerarlo con el comando del docstring"


def test_descripciones_normalizadas_al_registrar(srv):
    """T-013 criterio 10: las descripciones se registran ya normalizadas (inspect.cleandoc), así todos los clientes ven
    el mismo texto en Python 3.10 a 3.14."""
    import inspect
    herramientas = asyncio.run(srv.mcp.list_tools())
    assert len(herramientas) == 28
    for t in herramientas:
        assert t.description and t.description == inspect.cleandoc(t.description), t.name
        assert "\n    " not in t.description, t.name


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(INSTANTANEA.parents[1]))
    import servidor
    INSTANTANEA.write_text(instantanea(servidor.mcp), encoding="utf-8")
    print(f"Instantánea escrita en {INSTANTANEA}")


# ───────────────────────── T-011: renombrado del contrato (v1 paso 2) ─────────────────────────
# contrato_herramientas_v0.json es la instantánea de main antes del renombrado (git show main:tests/…), guardada
# para comprobar que el mapeo español → inglés es completo.

INSTANTANEA_V0 = INSTANTANEA.with_name("contrato_herramientas_v0.json")


def _cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_mapeo_de_nombres_completo_y_solo_dos_herramientas_nuevas():
    from ratifact.vocabulario import HERRAMIENTAS_NUEVAS, HERRAMIENTAS_V0, PROMPTS_V0
    viejo, nuevo = _cargar(INSTANTANEA_V0), _cargar(INSTANTANEA)
    viejas = [h["nombre"] for h in viejo["herramientas"]]
    nuevas = {h["nombre"] for h in nuevo["herramientas"]}
    assert len(viejas) == 26 and len(nuevas) == 28
    destinos = [HERRAMIENTAS_V0[v] for v in viejas]                  # KeyError = herramienta vieja sin mapeo
    assert len(set(destinos)) == len(destinos) == 26                 # cada una a exactamente una nueva, sin choques
    assert set(destinos) <= nuevas
    assert nuevas - set(destinos) == set(HERRAMIENTAS_NUEVAS) == {"amend_task", "read_task"}
    assert {PROMPTS_V0[p["nombre"]] for p in viejo["prompts"]} == {p["nombre"] for p in nuevo["prompts"]}


# Parámetros nuevos agregados después de la instantánea v0 (ya en inglés, sin nombre v0 que traducir).
POSTERIORES_A_V0 = {"actualizar_proyecto": {"models", "delegation"}, "registrar_tarea": {"delegation"}}  # T-014, T-015


def test_ningun_nombre_ni_parametro_en_espanol_queda_expuesto():
    from ratifact.vocabulario import HERRAMIENTAS_V0, PARAMETROS_V0
    viejo, nuevo = _cargar(INSTANTANEA_V0), _cargar(INSTANTANEA)
    assert not {h["nombre"] for h in nuevo["herramientas"]} & set(HERRAMIENTAS_V0)    # sin alias duplicados
    por_nombre = {h["nombre"]: h for h in nuevo["herramientas"]}
    for h in viejo["herramientas"]:
        nueva = por_nombre[HERRAMIENTAS_V0[h["nombre"]]]
        params = set(nueva["esquema_entrada"]["properties"])
        esperados = {PARAMETROS_V0.get(p, p) for p in h["esquema_entrada"]["properties"]}
        esperados |= POSTERIORES_A_V0.get(h["nombre"], set())
        assert params == esperados, (h["nombre"], params, esperados)
        assert not params & (set(PARAMETROS_V0) - set(PARAMETROS_V0.values())), h["nombre"]
    for p in nuevo["prompts"]:
        assert [a["nombre"] for a in p["argumentos"]] == ["project"]


# T-021 (ADR-043): las descripciones se reescribieron sin identificadores ADR; todo lo demás debe ser idéntico a main.
# SHA-256 del contrato de main SIN descripciones, calculado con `sin_descripciones` y `serializar`:
#   git show main:tests/contrato_herramientas.json | python -c "import json,sys,hashlib; \
#     from tests.test_contrato import sin_descripciones, serializar; \
#     print(hashlib.sha256(serializar(sin_descripciones(json.load(sys.stdin))).encode()).hexdigest())"
# (no depende de git al correr la prueba).
SHA256_CONTRATO_MAIN_SIN_DESCRIPCIONES = "28bc6f89fb6e1f199c68729b46306702b1715b0558160c5fc3319028a59826c1"


def sin_descripciones(valor):
    """Quita recursivamente `descripcion` (herramientas, prompts, argumentos) y `description` (esquema de entrada) cuyo
    valor es texto; un parámetro llamado "description" (valor dict) se conserva."""
    if isinstance(valor, dict):
        return {k: sin_descripciones(v) for k, v in valor.items()
                if not (k in ("descripcion", "description") and isinstance(v, str))}
    if isinstance(valor, list):
        return [sin_descripciones(v) for v in valor]
    return valor


def test_contrato_sin_descripciones_identico_a_main():
    """T-021 criterio 15: nombres, parámetros, tipos y número de herramientas/prompts no cambian respecto de main."""
    import hashlib
    datos = json.loads(INSTANTANEA.read_text(encoding="utf-8"))
    canonico = serializar(sin_descripciones(datos))
    assert hashlib.sha256(canonico.encode("utf-8")).hexdigest() == SHA256_CONTRATO_MAIN_SIN_DESCRIPCIONES
    assert len(datos["herramientas"]) == 28
