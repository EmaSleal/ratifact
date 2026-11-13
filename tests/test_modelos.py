"""T-014 / ADR-033 §2, ADR-035: modelos por rol (explore, write, verify). Global en settings.json junto a projects.json,
excepciones por proyecto en su entrada, bloque "Model routing" en update_task(..., "in_progress") y doctor."""
import json
import re
from pathlib import Path

import pytest

from test_upgrade import hogar  # noqa: F401  (fixture: HOME temporal para doctor)


def _config(entorno) -> Path:
    return Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])


def _settings(entorno, contenido) -> Path:
    ruta = _config(entorno).parent / "settings.json"
    ruta.write_text(contenido if isinstance(contenido, str) else json.dumps(contenido))
    return ruta


def _en_curso(srv) -> str:
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    return srv.update_task(project="demo", id="T-001", status="in_progress")


def _bloque(salida: str) -> str:
    return salida[salida.index("Model routing"):] if "Model routing" in salida else ""


# ───────────────────────── criterio 4: sin configuración, nada cambia ─────────────────────────

def test_sin_configuracion_la_respuesta_es_identica(srv, proyecto):
    """Sin modelos configurados no hay bloque Model routing. Desde T-015 (ADR-036) la respuesta sí trae el bloque de
    delegación required, porque es la política por defecto (test_delegacion lo fija); con delegation=off la respuesta
    es la de T-014."""
    from ratifact.integraciones import registro
    srv.update_project(name="demo", delegation="off")
    salida = _en_curso(srv)
    sha = re.match(r"T-001 → in_progress · commit (\S+)", salida).group(1)
    from ratifact.idioma import bloque_idioma    # T-023: the language block comes first, nothing else is added
    assert salida == f"T-001 → in_progress · commit {sha}\n\n{bloque_idioma('en')}\n\n{registro._guia_en_curso('demo')}"
    assert "Model routing" not in salida


def test_settings_sin_models_no_agrega_bloque(srv, proyecto, entorno):
    _settings(entorno, {"otra": 1})
    assert "Model routing" not in _en_curso(srv)


# ───────────────────────── criterios 1, 2 y 4: global, proyecto y combinación ─────────────────────────

def test_bloque_presente_sin_integraciones(srv, proyecto, entorno):
    srv.update_project(name="demo", integrations="engram=off")      # ninguna integración activa
    _settings(entorno, {"models": {"explore": "haiku"}})
    salida = _en_curso(srv)
    assert "Integration guidance" not in salida
    bloque = _bloque(salida)
    assert bloque.splitlines()[:4] == ["Model routing (configured by the user):", "- explore: haiku (global)",
                                       "- write: session model (not set)", "- verify: session model (not set)"]
    assert "explicit request" in bloque and "cannot choose the model" in bloque and "inherit the session" in bloque


def test_proyecto_gana_rol_por_rol_y_hereda_el_resto(srv, proyecto, entorno):
    _settings(entorno, {"models": {"explore": "haiku", "write": "sonnet", "verify": "sonnet"}})
    salida = srv.update_project(name="demo", models="write=opus")
    assert "models: write=opus" in salida
    bloque = _bloque(_en_curso(srv))
    assert "- explore: haiku (global)\n- write: opus (project)\n- verify: sonnet (global)" in bloque


def _en_curso_sin_crear(srv) -> str:
    return srv.update_task(project="demo", id="T-001", status="in_progress")


def test_settings_se_lee_en_cada_llamada(srv, proyecto, entorno):
    srv.create_task(project="demo", title="Algo", goal="o", acceptance_criteria="c")
    assert "Model routing" not in _en_curso_sin_crear(srv)
    _settings(entorno, {"models": {"verify": "sonnet"}})
    assert "- verify: sonnet (global)" in _en_curso_sin_crear(srv)
    _settings(entorno, {"models": {"verify": "haiku"}})
    assert "- verify: haiku (global)" in _en_curso_sin_crear(srv)


# ───────────────────────── criterio 3: update_project(models=...) ─────────────────────────

def test_update_project_guarda_en_la_entrada_y_no_en_el_nivel_superior(srv, proyecto, entorno):
    srv.update_project(name="demo", models="explore=haiku, write=claude-sonnet-5-5")
    datos = json.loads(_config(entorno).read_text())
    assert list(datos) == ["demo"]
    assert datos["demo"]["models"] == {"explore": "haiku", "write": "claude-sonnet-5-5"}
    assert not (_config(entorno).parent / "settings.json").exists()      # install/update nunca lo crean


def test_inherit_quita_la_excepcion_del_rol(srv, proyecto, entorno):
    _settings(entorno, {"models": {"explore": "haiku"}})
    srv.update_project(name="demo", models="explore=opus,write=sonnet")
    salida = srv.update_project(name="demo", models="explore=inherit")
    assert "models: explore=inherit" in salida
    assert json.loads(_config(entorno).read_text())["demo"]["models"] == {"write": "sonnet"}
    assert "- explore: haiku (global)\n- write: sonnet (project)" in _bloque(_en_curso(srv))
    srv.update_project(name="demo", models="write=INHERIT")
    assert "models" not in json.loads(_config(entorno).read_text())["demo"]


@pytest.mark.parametrize("valor,esperado", [("planner=haiku", "Unknown role 'planner'"),
                                            ("explore=", "Empty model for 'explore'"),
                                            ("explore", "Format of `models`"),
                                            (" , ", "Empty `models`")])
def test_update_project_rechaza_roles_y_valores_invalidos(srv, proyecto, entorno, valor, esperado):
    antes = _config(entorno).read_text()
    salida = srv.update_project(name="demo", models=valor)
    assert salida.startswith("ERROR") and esperado in salida, salida
    assert "Valid roles: explore, write, verify." in salida
    assert _config(entorno).read_text() == antes


def test_update_project_sin_nada_menciona_models(srv, proyecto):
    assert "`models`" in srv.update_project(name="demo")


# ───────────────────────── criterio 10: settings.json inválido ─────────────────────────

@pytest.mark.parametrize("contenido,esperado", [("{no es json", "is not valid JSON"),
                                                ({"models": {"planner": "haiku"}}, "unknown role(s) in `models`: planner"),
                                                ({"models": {"write": ""}}, "empty model for write"),
                                                ({"models": ["haiku"]}, "must be an object")])
def test_settings_invalido_no_rompe_y_avisa(srv, proyecto, entorno, contenido, esperado):
    ruta = _settings(entorno, contenido)
    antes = ruta.read_text()
    srv.update_project(name="demo", models="write=sonnet")
    assert not srv.get_context(project="demo").startswith("ERROR")
    salida = _en_curso(srv)
    assert salida.startswith("T-001 → in_progress · commit")
    bloque = _bloque(salida)
    assert esperado in bloque and "Global models ignored." in bloque and "- write: sonnet (project)" in bloque
    assert ruta.read_text() == antes


def test_settings_invalido_no_afecta_a_otro_proyecto(srv, proyecto, entorno):
    from conftest import crear_repo
    repo = crear_repo(entorno["base"] / "otro")
    srv.register_project(name="otro", path=str(repo))
    _settings(entorno, "[")
    assert not srv.get_context(project="otro").startswith("ERROR")
    srv.create_task(project="otro", title="X", goal="o", acceptance_criteria="c")
    salida = srv.update_task(project="otro", id="T-001", status="in_progress")
    assert salida.startswith("T-001 → in_progress") and "is not valid JSON" in salida


# ───────────────────────── criterio 8: doctor ─────────────────────────

def _doctor():
    from ratifact import doctor
    lineas, acciones = doctor.informe(procesos=lambda: [])
    return "\n".join(lineas), acciones


def test_doctor_muestra_modelos_efectivos(srv, proyecto, entorno, hogar):
    texto, acciones = _doctor()
    assert "    models: session default" in texto and "(not created; models: session default)" in texto
    _settings(entorno, {"models": {"explore": "haiku", "write": "sonnet"}})
    srv.update_project(name="demo", models="write=opus")
    texto, acciones = _doctor()
    assert "    models: explore=haiku (global), write=opus (project)" in texto
    assert "global models: explore=haiku, write=sonnet" in texto
    assert not any("settings.json" in a for a in acciones)


def test_doctor_reporta_settings_invalido_sin_tocarlo(srv, proyecto, entorno, hogar):
    for contenido, esperado in (("{x", "is not valid JSON"), ({"models": {"bogus": "x"}}, "bogus")):
        ruta = _settings(entorno, contenido)
        antes = ruta.read_bytes()
        texto, acciones = _doctor()
        assert "(INVALID)" in texto
        assert any("settings.json" in a and esperado in a for a in acciones), acciones
        assert ruta.read_bytes() == antes


def test_doctor_reporta_excepcion_de_proyecto_invalida(srv, proyecto, entorno, hogar):
    datos = json.loads(_config(entorno).read_text())
    datos["demo"]["models"] = {"planner": "haiku"}
    _config(entorno).write_text(json.dumps(datos))
    texto, acciones = _doctor()
    assert any(a.startswith("demo:") and "planner" in a for a in acciones), acciones


# ───────────────────────── criterios 5 y 7: guía gentle-ai y skill ─────────────────────────

def test_guia_gentle_ai_delegated_direct_odd_y_rdd(srv):
    from ratifact.integraciones import gentle_ai
    i = gentle_ai.INTEGRACION
    todo = " ".join(i.guia.values()) + i.prefijo + i.rol
    assert "sdd-" not in todo and "sdd-" != i.prefijo
    ejecutar, verificar = i.guia["execute"], i.guia["verify"]
    for texto in ("delegated-direct", "never SDD", "no SDD artifacts", "Delegation block", "feature document",
                  "no other ODD document"):
        assert texto in ejecutar, texto
    for texto in ("4+ files", "2+ non-trivial files", "otherwise implement directly"):      # T-015 / ADR-036
        assert texto not in ejecutar, texto
    for texto in ("clean worker", "if RDD is on", "before update_task(in_review)", "receipt", "depth", "findings",
                  "corrections", "if RDD is off, start no review"):
        assert texto in verificar, texto


def test_skill_pide_seguir_model_routing_e_informar_trabajadores(srv):
    from conftest import RAIZ_REPO
    for ruta in (RAIZ_REPO / "ratifact" / "skills" / "run-task" / "SKILL.md", RAIZ_REPO / "run-task.md"):
        skill = ruta.read_text(encoding="utf-8")
        ejecutar = skill.split("## 2. Execute")[1].split("## 3.")[0]
        cerrar = skill.split("## 4. Close")[1]
        assert '"Model routing"' in ejecutar
        assert "Workers:" in cerrar and "explore/haiku×1, write/sonnet×2" in cerrar and "receipt" in cerrar
