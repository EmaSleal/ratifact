"""T-008 / ADR-024, ADR-025: integraciones opcionales (codegraph, gentle-ai, engram) por guía condicional.
ratifact nunca llama a otros MCP: solo detecta señales en disco (alcance proyecto) y devuelve guía condicional en
get_context, create_task y update_task(..., "en_curso"). Nunca se escribe guía en la tarea."""
import importlib
import json
import re
from pathlib import Path

import pytest

from conftest import RAIZ_REPO, crear_repo


@pytest.fixture
def reg(srv):
    return importlib.import_module("ratifact.integraciones.registro")


def _por_nombre(reg, nombre):
    return next(i for i in reg.INTEGRACIONES if i.nombre == nombre)


# ───────────────────────── criterio 1: registro y descriptores ─────────────────────────

def test_registro_lista_exactamente_las_tres(reg):
    assert [i.nombre for i in reg.INTEGRACIONES] == ["codegraph", "gentle-ai", "engram"]


def test_cada_modulo_de_integracion_esta_registrado_una_vez(reg):
    """Agregar una integración = agregar un módulo y registrarlo: cada módulo (salvo base/registro) aporta una."""
    carpeta = RAIZ_REPO / "ratifact" / "integraciones"
    modulos = sorted(p.stem for p in carpeta.glob("*.py") if p.stem not in ("__init__", "base", "registro"))
    assert modulos == ["codegraph", "engram", "gentle_ai"]
    for m in modulos:
        integ = importlib.import_module(f"ratifact.integraciones.{m}").INTEGRACION
        assert sum(1 for i in reg.INTEGRACIONES if i is integ) == 1


def test_cada_descriptor_tiene_todos_los_campos(reg):
    for i in reg.INTEGRACIONES:
        assert i.nombre and i.prefijo and i.rol and i.limite and i.guia, i
        assert i.alcance in ("project", "user")
        assert (i.detectar is not None) == (i.alcance == "project")
        assert set(i.guia) <= set(reg.FASES) and all(i.guia.values())
    assert _por_nombre(reg, "codegraph").alcance == "project"
    assert _por_nombre(reg, "gentle-ai").alcance == "project"
    assert _por_nombre(reg, "engram").alcance == "user"
    assert set(_por_nombre(reg, "codegraph").guia) == {"plan", "execute", "verify"}
    assert set(_por_nombre(reg, "gentle-ai").guia) == {"execute", "verify"}
    assert set(_por_nombre(reg, "engram").guia) == {"close"}


# ───────────────────────── criterio 3: guía condicional con su límite ─────────────────────────

def test_cada_fragmento_es_condicional_y_nombra_su_prefijo(reg):
    for i in reg.INTEGRACIONES:
        assert "never decisions or task status" in i.limite, i.nombre
        for fase, texto in i.guia.items():
            assert f"`{i.prefijo}" in texto, (i.nombre, fase)
            assert texto.startswith("if you have ") and "; otherwise" in texto, (i.nombre, fase)
            # gentle-ai (T-014) lleva umbrales de delegación y RDD: tope más alto
            assert len(texto) <= (360 if i.nombre == "gentle-ai" else 260), (i.nombre, fase, len(texto))


# ───────────────────────── criterio 2: detección en disco ─────────────────────────

def test_deteccion_en_la_raiz_de_un_repo(reg, tmp_path):
    raiz = crear_repo(tmp_path / "uno")
    cg, ga = _por_nombre(reg, "codegraph"), _por_nombre(reg, "gentle-ai")
    assert not reg._detectada(cg, raiz) and not reg._detectada(ga, raiz)
    (raiz / ".codegraph").mkdir()
    assert reg._detectada(cg, raiz) and not reg._detectada(ga, raiz)
    (raiz / ".atl").mkdir()
    assert reg._detectada(ga, raiz)
    (raiz / ".codegraph").rmdir()                                    # sin caché: se relee el disco cada vez
    assert not reg._detectada(cg, raiz)


def test_un_archivo_no_cuenta_como_senal(reg, tmp_path):
    raiz = crear_repo(tmp_path / "uno")
    (raiz / ".codegraph").write_text("")
    assert not reg._detectada(_por_nombre(reg, "codegraph"), raiz)


def test_deteccion_en_cualquier_repo_de_un_multirepo(reg, tmp_path):
    raiz = tmp_path / "multi"
    crear_repo(raiz / "backend")
    crear_repo(raiz / "frontend")
    cg = _por_nombre(reg, "codegraph")
    assert not reg._detectada(cg, raiz)
    (raiz / "frontend" / ".codegraph").mkdir()
    assert reg._detectada(cg, raiz)
    (raiz / "frontend" / ".codegraph").rmdir()
    (raiz / ".codegraph").mkdir()                                    # o en la carpeta que agrupa los repos
    assert reg._detectada(cg, raiz)


def test_carpeta_inexistente_no_detecta_nada(reg, tmp_path):
    assert not reg._detectada(_por_nombre(reg, "codegraph"), tmp_path / "no-existe")


def test_engram_nunca_se_detecta(srv, proyecto, reg):
    (proyecto["repo"] / ".engram").mkdir()
    assert _por_nombre(reg, "engram").detectar is None
    linea = reg._linea_integraciones("demo")
    assert "engram (if available)" in linea and "engram (detected)" not in linea


# ───────────────────────── criterio 4: configuración ─────────────────────────

def _config(entorno):
    return json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())


def test_actualizar_proyecto_apaga_y_reactiva_integraciones(srv, proyecto, entorno):
    salida = srv.update_project(name="demo", integrations="codegraph=off, engram=off")
    assert not salida.startswith("ERROR"), salida
    assert "integrations" in salida and "codegraph=off" in salida
    assert _config(entorno)["demo"]["integrations"] == {"codegraph": "off", "engram": "off"}
    srv.update_project(name="demo", integrations="codegraph=auto,gentle-ai=auto")
    assert _config(entorno)["demo"]["integrations"] == {"engram": "off"}   # auto se omite
    srv.update_project(name="demo", integrations="engram=auto")
    assert "integraciones" not in _config(entorno)["demo"]


@pytest.mark.parametrize("valor, esperado", [
    ("codegrap=off", "codegrap"),
    ("codegraph=no", "auto, off"),
    ("codegraph", "name=auto|off"),
])
def test_integraciones_invalidas_listan_las_validas_y_no_escriben(srv, proyecto, entorno, valor, esperado):
    ruta = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta.read_text()
    salida = srv.update_project(name="demo", integrations=valor)
    assert salida.startswith("ERROR:") and esperado in salida, salida
    assert "codegraph, gentle-ai, engram" in salida
    assert ruta.read_text() == antes


def test_nada_para_actualizar_menciona_integraciones(srv, proyecto):
    salida = srv.update_project(name="demo")
    assert salida.startswith("ERROR:") and "`integrations`" in salida


def test_integraciones_apagadas_no_aparecen_en_ningun_lado(srv, proyecto):
    (proyecto["repo"] / ".codegraph").mkdir()
    (proyecto["repo"] / ".atl").mkdir()
    srv.update_project(name="demo", integrations="codegraph=off,gentle-ai=off,engram=off")
    ctx = srv.get_context(project="demo")
    alta = srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    curso = srv.update_task(project="demo", id="T-001", status="en_curso")
    for texto in (ctx, alta, curso):
        assert "Integraciones" not in texto and "codegraph" not in texto and "engram" not in texto, texto


# ───────────────────────── criterio 5: get_context ─────────────────────────

def test_obtener_contexto_agrega_linea_y_planificar_dentro_del_presupuesto(srv, proyecto, reg, monkeypatch):
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    monkeypatch.setattr(reg, "INTEGRACIONES", ())
    antes = srv.get_context(project="demo")
    monkeypatch.undo()
    (proyecto["repo"] / ".codegraph").mkdir()
    (proyecto["repo"] / ".atl").mkdir()
    despues = srv.get_context(project="demo")
    assert despues.startswith(antes), "el contenido de arranque existente no cambia"
    agregado = despues[len(antes):]
    assert len(agregado) <= 600, (len(agregado), agregado)
    lineas = agregado.removeprefix("\n\n---\n\n").splitlines()
    assert lineas[0] == "Integrations: codegraph (detected), gentle-ai (detected) · engram (if available)"
    assert len(lineas) == 2 and lineas[1].startswith("- codegraph · plan: if you have `codegraph_*` tools")
    assert "never decisions or task status" in lineas[1]


def test_obtener_contexto_sin_integraciones_detectadas_solo_engram(srv, proyecto):
    salida = srv.get_context(project="demo")
    assert salida.endswith("\n\n---\n\nIntegrations: engram (if available)"), salida[-200:]


def test_obtener_contexto_con_ruta_inexistente_no_falla(srv, proyecto):
    import shutil
    shutil.rmtree(proyecto["repo"])
    salida = srv.get_context(project="demo")
    assert not salida.startswith("ERROR") and "Integrations: engram (if available)" in salida


def test_obtener_contexto_multirepo_detecta_en_un_repo(srv, entorno):
    raiz = entorno["base"] / "multi"
    crear_repo(raiz / "backend")
    crear_repo(raiz / "frontend")
    (raiz / "backend" / ".codegraph").mkdir()
    srv.register_project(name="multi", path=str(raiz))
    assert "Integrations: codegraph (detected) · engram (if available)" in srv.get_context(project="multi")


# ───────────────────────── criterio 6: create_task ─────────────────────────

def test_registrar_tarea_agrega_solo_la_linea_y_no_escribe_guia(srv, proyecto):
    (proyecto["repo"] / ".codegraph").mkdir()
    salida = srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    assert salida.splitlines()[-1] == "Integrations: codegraph (detected) · engram (if available)"
    assert "planificar" not in salida and "si tienes" not in salida
    tarea = next((proyecto["mem"] / "tasks").glob("T-001*.md")).read_text()
    assert "ntegraci" not in tarea and "codegraph" not in tarea and "engram" not in tarea


# ───────────────────────── criterio 7: update_task en_curso ─────────────────────────

def test_en_curso_calcula_la_guia_en_ese_momento(srv, proyecto, reg):
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    (proyecto["repo"] / ".codegraph").mkdir()                        # se instala entre el alta y la ejecución
    salida = srv.update_task(project="demo", id="T-001", status="en_curso")
    assert salida.startswith("T-001 → in_progress · commit")
    cg, en = _por_nombre(reg, "codegraph"), _por_nombre(reg, "engram")
    for texto in (cg.guia["execute"], cg.guia["verify"], en.guia["close"], cg.limite, en.limite):
        assert texto in salida
    assert cg.guia["plan"] not in salida and "gentle-ai" not in salida
    tarea = next((proyecto["mem"] / "tasks").glob("T-001*.md")).read_text()
    assert "codegraph" not in tarea and "engram" not in tarea


def test_en_curso_incluye_gentle_ai_detectada(srv, proyecto, reg):
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    (proyecto["repo"] / ".atl").mkdir()
    salida = srv.update_task(project="demo", id="T-001", status="en_curso")
    assert _por_nombre(reg, "gentle-ai").guia["execute"] in salida


@pytest.mark.parametrize("estado,guardado", [("en_revision", "in_review"), ("fallida", "failed"), ("pendiente", "todo"),
                                            ("in_review", "in_review")])
def test_otros_estados_no_cambian(srv, proyecto, estado, guardado):
    (proyecto["repo"] / ".codegraph").mkdir()
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    salida = srv.update_task(project="demo", id="T-001", status=estado)
    assert re.fullmatch(rf"T-001 → {guardado} · commit \S+", salida), salida


# ───────────────────────── criterio 8: migración del texto ad hoc ─────────────────────────

def test_texto_ad_hoc_de_engram_y_gentle_ai_migrado(srv):
    from ratifact import app, plantillas
    assert "engram" not in app.mcp.instructions and "this server wins" in app.mcp.instructions
    assert "engram" not in plantillas.PLANTILLA_AGENTES and "gentle-ai" not in plantillas.PLANTILLA_AGENTES
    skill = (RAIZ_REPO / "skills" / "run-task" / "SKILL.md").read_text(encoding="utf-8")
    assert "engram" not in skill and "gentle-ai" not in skill
    assert "Integrations used:" in skill and "integration guidance" in skill
