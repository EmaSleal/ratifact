"""Alta de proyectos, instrucciones generadas, memoria en repo propio y telemetría."""
import json
import re
from pathlib import Path

from conftest import crear_repo, log_git, RAIZ_REPO


def test_alta_crea_memoria_con_repo_propio_e_instrucciones(srv, proyecto, entorno):
    assert (proyecto["mem"] / ".git").exists()
    assert "memoria: inicializar memoria" in log_git(proyecto["mem"])
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["demo"]["memoria"] == str(proyecto["mem"])
    instr = srv.instrucciones_proyecto(proyecto="demo")
    assert "proyecto: demo" in instr and 'obtener_contexto("demo")' in instr


def test_alta_valida_nombre_rutas_y_duplicados(srv, proyecto, entorno):
    otro = crear_repo(entorno["base"] / "otro")
    assert "Nombre inválido" in srv.registrar_proyecto(nombre="Mi Proyecto", ruta=str(otro))
    assert "dentro de" in srv.registrar_proyecto(nombre="otro", ruta="/tmp")
    assert "No existe" in srv.registrar_proyecto(nombre="otro", ruta=str(entorno["base"] / "nada"))
    assert "ya está registrado" in srv.registrar_proyecto(nombre="demo", ruta=str(otro))
    assert "no registrado" in srv.instrucciones_proyecto(proyecto="nada")


def test_alta_sin_git_avisa(srv, entorno):
    (entorno["base"] / "suelto").mkdir()
    assert "no es un repositorio git" in srv.registrar_proyecto(nombre="suelto", ruta=str(entorno["base"] / "suelto"))


def test_memoria_dentro_del_repo_del_codigo_se_rechaza(srv, entorno):
    """ADR-010: un solo modo; la memoria nunca vive dentro del repositorio del código."""
    repo = crear_repo(entorno["base"] / "interno")
    salida = srv.registrar_proyecto(nombre="interno", ruta=str(repo), memoria=str(repo / ".project"))
    assert "ADR-010" in salida and "interno" not in srv.listar_proyectos()


def test_memoria_dentro_del_repo_mensaje_de_alta_distinto_de_actualizar(srv, entorno):
    """Obs. 4 / Criterio E: registrar_proyecto sugiere omitir `memoria` (no existe aún una memoria elegida
    para "corregir"); actualizar_proyecto, en cambio, usa la redacción de corrección (ver
    tests/test_actualizar_proyecto.py::test_actualizar_ruta_rechaza_memoria_adentro_adr010 para su mensaje)."""
    repo = crear_repo(entorno["base"] / "interno3")
    salida = srv.registrar_proyecto(nombre="interno3", ruta=str(repo), memoria=str(repo / ".project"))
    assert "ADR-010" in salida
    assert "omite `memoria`" in salida
    assert "no está soportado aquí" not in salida


def test_config_heredada_con_memoria_interna_avisa_como_migrar(srv, entorno):
    repo = crear_repo(entorno["base"] / "viejo")
    Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).write_text(json.dumps(
        {"viejo": {"ruta": str(repo), "memoria": str(repo / ".project")}}))
    salida = srv.registrar_pendiente(proyecto="viejo", tema="t", contexto="c")
    assert salida.startswith("ERROR:") and ".memorias/viejo" in salida
    assert "configuración inválida" in srv.listar_proyectos()


def test_sin_clave_memoria_usa_memorias_por_defecto(srv, entorno):
    repo = crear_repo(entorno["base"] / "legado")
    Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).write_text(json.dumps({"legado": {"ruta": str(repo)}}))
    srv.inicializar_memoria(proyecto="legado")
    assert (entorno["base"] / ".memorias" / "legado" / ".git").exists() and not (repo / ".project").exists()


def test_inicializar_es_idempotente(srv, proyecto):
    assert not srv.inicializar_memoria(proyecto="demo").startswith("ERROR")
    assert "memoria lista" in srv.listar_proyectos()


def test_telemetria_registra_y_clasifica_errores(srv, proyecto, entorno):
    srv.obtener_contexto(proyecto="demo")
    srv.confirmar_decision(proyecto="demo", id="ADR-404", cita_usuario="ok")    # rechazo de validación
    srv.leer_documento(proyecto="demo", ruta="docs/vision.md")
    filas = [json.loads(l) for l in Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()]
    ultimas = {f["herramienta"]: f for f in filas}
    assert ultimas["obtener_contexto"]["error"] is False and ultimas["obtener_contexto"]["resp_chars"] > 0
    assert ultimas["confirmar_decision"]["tipo_error"] == "validacion"
    assert ultimas["leer_documento"]["ruta"] == "docs/vision.md"
    assert all("contenido" not in f.get("args_chars", {}) or isinstance(f["args_chars"]["contenido"], int) for f in filas)


def test_falla_inesperada_se_registra_como_interna(srv, proyecto, entorno, monkeypatch):
    def rota(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(srv, "_regenerar_vistas", rota)
    salida = srv.registrar_pendiente(proyecto="demo", tema="t", contexto="c")
    assert salida.startswith("ERROR INTERNO: OSError")
    fila = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]).read_text().splitlines()[-1])
    assert fila["tipo_error"] == "interno"


def test_sin_nombres_de_proyecto_fijos_en_el_codigo():
    """Regresión: 'game' como valor por defecto hizo que 'inicio' cargara otro proyecto."""
    codigo = (RAIZ_REPO / "servidor.py").read_text()
    sin_docstring = codigo.split('"""', 2)[2]
    assert "game" not in sin_docstring
    assert not re.search(r'proyecto: str = "[^"]+"', sin_docstring)


def test_instrucciones_cubren_codex(srv, proyecto):
    """ADR-008: Codex no tiene comandos propios (custom prompts eliminados); /tarea se instala como skill."""
    salida = srv.instrucciones_proyecto(proyecto="demo")
    assert "skills/tarea ~/.codex/skills/tarea" in salida and "skills/tarea ~/.agents/skills/tarea" in salida
    assert "$tarea T-NNN" in salida
    skill = srv.Path(srv.__file__).parent / "skills" / "tarea" / "SKILL.md"
    assert skill.is_file() and not skill.is_symlink()                   # Codex no sigue SKILL.md enlazados
    assert (skill.parent.parent.parent / "tarea.md").resolve() == skill.resolve()   # una sola fuente
    cabecera = skill.read_text().split("---")[1]
    assert "name: tarea" in cabecera and "description:" in cabecera      # requisitos de una skill de Codex


def test_servidor_se_declara_fuente_de_verdad(srv):
    """Hallazgo Codex/Fractall: con engram presente, "carga el contexto" consultó solo engram."""
    texto = srv.mcp.instructions
    assert "obtener_contexto" in texto and "engram" in texto and "gana memoria-proyectos" in texto
