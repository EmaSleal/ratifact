"""P-011: ids normalizados en toda escritura y eco, orden numérico de ids en vistas y listados, y telemetría
igual para llamadas posicionales y por nombre."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from conftest import RAIZ_REPO, log_git
from ratifact import registros


def _escribir_registro_a_mano(carpeta: Path, id_: str, campos: str) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{id_}-registro-{id_.lower()}.md"
    ruta.write_text(f"---\nid: {id_}\n{campos}\n---\n# {id_} — Registro {id_}\n\nCuerpo de {id_}.\n", encoding="utf-8")
    return ruta


def _adr(mem: Path, id_: str, estado: str = "propuesta", extra: str = "") -> Path:
    campos = f"titulo: Titulo {id_}\nestado: {estado}\nfecha: 2026-01-01\nresumen: Resumen {id_}" + (f"\n{extra}" if extra else "")
    return _escribir_registro_a_mano(mem / "decisiones", id_, campos)


def _antes(texto: str, primero: str, segundo: str) -> bool:
    return primero in texto and segundo in texto and texto.index(primero) < texto.index(segundo)


def _filas_log(entorno) -> list[dict]:
    return [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]


# ───────────────────────── orden numérico (ADR-101 antes que ADR-1000) ─────────────────────────

def test_acuerdos_ordena_ids_numericamente(srv, proyecto):
    _adr(proyecto["mem"], "ADR-1000")
    _adr(proyecto["mem"], "ADR-101")
    registros._regenerar_vistas("demo")
    texto = (proyecto["mem"] / "acuerdos.md").read_text()
    assert _antes(texto, "**ADR-101**", "**ADR-1000**"), texto


def test_abiertas_ordena_pendientes_numericamente(srv, proyecto):
    for id_ in ("P-1000", "P-101"):
        _escribir_registro_a_mano(proyecto["mem"] / "pendientes", id_, f"tema: Tema {id_}\nestado: abierta\nfecha: 2026-01-01")
    registros._regenerar_vistas("demo")
    texto = (proyecto["mem"] / "abiertas.md").read_text()
    assert _antes(texto, "**P-101**", "**P-1000**"), texto


def test_resumen_tareas_ordena_ids_numericamente(srv, proyecto):
    for id_ in ("T-1000", "T-101"):
        _escribir_registro_a_mano(proyecto["mem"] / "tareas", id_, f"titulo: Tarea {id_}\nestado: pendiente\nfecha: 2026-01-01")
    filas = registros._resumen_tareas("demo")
    assert [f.split("**")[1] for f in filas] == ["T-101", "T-1000"]


def test_decidir_propuestas_ordena_ids_numericamente(srv, proyecto):
    _adr(proyecto["mem"], "ADR-1000")
    _adr(proyecto["mem"], "ADR-101")
    vistos = []

    async def elicit(mensaje, _esquema):
        vistos.append("ADR-1000" if "# ADR-1000" in mensaje else "ADR-101")
        return SimpleNamespace(action="accept", data=SimpleNamespace(accion="posponer", comentario=""))
    capacidades = SimpleNamespace(elicitation=SimpleNamespace())
    ctx = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(capabilities=capacidades)), elicit=elicit)

    salida = asyncio.run(srv.decidir_propuestas(proyecto="demo", ctx=ctx))

    assert vistos == ["ADR-101", "ADR-1000"]
    assert "Siguen como propuesta: ADR-101, ADR-1000" in salida, salida


def test_obtener_contexto_lista_propuestas_en_orden_numerico(srv, proyecto):
    _adr(proyecto["mem"], "ADR-1000")
    _adr(proyecto["mem"], "ADR-101")
    salida = srv.obtener_contexto(proyecto="demo")
    linea = next(l for l in salida.splitlines() if l.startswith("Decisiones propuestas pendientes"))
    assert linea.endswith(": ADR-101, ADR-1000"), linea


# ───────────────────────── ids normalizados al escribir y al mostrar ─────────────────────────

def test_confirmar_lote_con_ids_equivalentes_confirma_una_sola_vez(srv, proyecto):
    ruta = _adr(proyecto["mem"], "ADR-001")
    commits_antes = len(log_git(proyecto["mem"]))

    salida = srv.confirmar_decisiones_lote(proyecto="demo", ids=["ADR-1", "adr-001", "ADR-001"], cita_usuario="sí, las dos")

    assert salida.startswith("1 acordadas (ADR-001) · commit"), salida
    texto = ruta.read_text()
    assert texto.count("## Confirmación") == 1 and "estado: acordada" in texto
    assert len(log_git(proyecto["mem"])) == commits_antes + 1
    assert log_git(proyecto["mem"])[0] == "memoria: 1 decisiones acordadas en lote: ADR-001"


def test_reemplazar_decision_guarda_y_muestra_id_normalizado(srv, proyecto):
    ruta = _adr(proyecto["mem"], "ADR-001", estado="acordada")
    _adr(proyecto["mem"], "ADR-002")

    salida = srv.reemplazar_decision(proyecto="demo", id_anterior="adr-1", id_nuevo="ADR-2")

    assert salida.startswith("ADR-001 reemplazada por ADR-002 · commit"), salida
    assert "reemplazada_por: ADR-002" in ruta.read_text()
    assert "reemplazada por ADR-002" in (proyecto["mem"] / "acuerdos.md").read_text()
    assert log_git(proyecto["mem"])[0] == "memoria: ADR-001 reemplazada por ADR-002"


def test_vista_normaliza_reemplazada_por_guardado_sin_normalizar(srv, proyecto):
    _adr(proyecto["mem"], "ADR-001", estado="reemplazada", extra="reemplazada_por: ADR-5")
    registros._regenerar_vistas("demo")
    assert "reemplazada por ADR-005" in (proyecto["mem"] / "acuerdos.md").read_text()


def test_cerrar_pendiente_guarda_id_decision_normalizado(srv, proyecto):
    srv.registrar_pendiente(proyecto="demo", tema="Motor", contexto="c")

    salida = srv.cerrar_pendiente(proyecto="demo", id="P-1", resolucion="Godot", id_decision="adr-3")

    assert salida.startswith("P-001 cerrado"), salida
    meta, _ = registros._leer_registro(next((proyecto["mem"] / "pendientes").glob("P-001-*.md")))
    assert meta["resolucion"] == "Godot (ADR-003)"


def test_ningun_upper_fuera_de_normalizar_id():
    """Los ids entrantes se normalizan con registros._normalizar_id; un `.upper()` suelto (p. ej. `id_nuevo.upper()`)
    deja "ADR-2" sin rellenar. Si un `.upper()` nuevo no es sobre un id, agrégalo aquí con su motivo."""
    permitidos = {("ratifact/registros.py", "_normalizar_id")}
    encontrados = []
    for archivo in sorted((RAIZ_REPO / "ratifact").rglob("*.py")):
        rel = archivo.relative_to(RAIZ_REPO).as_posix()
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for funcion in [n for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for nodo in ast.walk(funcion):
                if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr == "upper"
                        and (rel, funcion.name) not in permitidos):
                    encontrados.append(f"{rel}:{nodo.lineno} en {funcion.name}")
    assert not encontrados, encontrados


# ───────────────────────── telemetría de llamadas posicionales ─────────────────────────

def _sin_tiempos(fila: dict) -> dict:
    return {k: v for k, v in fila.items() if k not in ("ts", "ms")}


def test_telemetria_posicional_igual_que_por_nombre(srv, proyecto, entorno):
    srv.registrar_pendiente(proyecto="demo", tema="Tema A", contexto="contexto")
    srv.registrar_pendiente("demo", "Tema B", "contexto")
    por_nombre, posicional = [f for f in _filas_log(entorno) if f["herramienta"] == "registrar_pendiente"][-2:]
    assert posicional["proyecto"] == "demo"
    assert posicional["args_chars"] == {"tema": 6, "contexto": 8}
    assert _sin_tiempos(posicional) == _sin_tiempos(por_nombre)


def test_telemetria_posicional_async_igual_que_por_nombre(srv, proyecto, entorno):
    ctx = SimpleNamespace(session=SimpleNamespace(client_params=SimpleNamespace(
        capabilities=SimpleNamespace(elicitation=SimpleNamespace()))))
    asyncio.run(srv.decidir_propuestas(proyecto="demo", ctx=ctx))
    asyncio.run(srv.decidir_propuestas("demo", ctx))
    por_nombre, posicional = [f for f in _filas_log(entorno) if f["herramienta"] == "decidir_propuestas"][-2:]
    assert posicional["proyecto"] == "demo"
    assert _sin_tiempos(posicional) == _sin_tiempos(por_nombre)
