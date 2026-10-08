"""T-001 / ADR-018: `actualizar_proyecto` permite corregir `ruta` (y, como antes `configurar_pruebas`, las
pruebas) sin editar projects.json a mano. La migración de los casos de `pruebas`/`repositorio` que antes cubría
`configurar_pruebas` vive en tests/test_pruebas_por_proyecto.py y tests/test_multirepo.py."""
import json
import shutil
from pathlib import Path

from conftest import crear_repo


def test_actualizar_ruta_valida_igual_que_registrar_proyecto(srv, proyecto, entorno):
    """Criterio 2: mismas validaciones que registrar_proyecto (dentro de la carpeta de proyectos, carpeta
    existente); ningún rechazo escribe el archivo."""
    nueva = crear_repo(entorno["base"] / "demo" / "codigo2")
    ruta_config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta_config.read_text()

    assert "dentro de" in srv.actualizar_proyecto(nombre="demo", ruta="/tmp")
    assert "No existe" in srv.actualizar_proyecto(nombre="demo", ruta=str(entorno["base"] / "demo" / "no-existe"))
    assert ruta_config.read_text() == antes      # ningún rechazo tocó el archivo

    salida = srv.actualizar_proyecto(nombre="demo", ruta=str(nueva))
    assert not salida.startswith("ERROR"), salida
    assert str(proyecto["repo"]) in salida and str(nueva) in salida     # criterio 3: ruta vieja y nueva
    config = json.loads(ruta_config.read_text())
    assert config["demo"]["ruta"] == str(nueva)


def test_actualizar_ruta_rechaza_memoria_adentro_adr010(srv, entorno):
    """Criterio 2: ADR-010 también se aplica al actualizar (no solo al dar de alta). Obs. 4 / Criterio E:
    actualizar_proyecto usa la redacción de corrección, distinta de la de registrar_proyecto (ver
    tests/test_proyectos_y_telemetria.py::test_memoria_dentro_del_repo_mensaje_de_alta_distinto_de_actualizar)."""
    repo = crear_repo(entorno["base"] / "interno2")
    srv.registrar_proyecto(nombre="interno2", ruta=str(repo))   # memoria en <base>/.memorias/interno2
    ruta_config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta_config.read_text()

    salida = srv.actualizar_proyecto(nombre="interno2", ruta=str(entorno["base"]))   # contendría la memoria
    assert salida.startswith("ERROR:") and "ADR-010" in salida
    assert "elige otra ruta" in salida and "no está soportado aquí" in salida
    assert "omite `memoria`" not in salida
    assert ruta_config.read_text() == antes


def test_actualizar_proyecto_sin_campos_no_escribe_nada(srv, proyecto, entorno):
    """Criterio 5."""
    ruta_config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta_config.read_text()
    assert srv.actualizar_proyecto(nombre="demo").startswith("ERROR:")
    assert ruta_config.read_text() == antes


def test_nombre_de_proyecto_admite_guion_bajo(srv, entorno):
    """Criterio 6."""
    repo = crear_repo(entorno["base"] / "erp_spring_manager")
    salida = srv.registrar_proyecto(nombre="erp_spring_manager", ruta=str(repo))
    assert not salida.startswith("ERROR"), salida
    assert "erp_spring_manager" in srv.listar_proyectos()


def test_sugerencia_de_nombre_equivalente_con_guion(srv, entorno):
    """Criterio 7: '_' vs '-' sugiere el nombre real registrado."""
    repo = crear_repo(entorno["base"] / "erp_spring_manager")
    srv.registrar_proyecto(nombre="erp_spring_manager", ruta=str(repo))
    salida = srv.obtener_contexto(proyecto="erp-spring-manager")
    assert salida.startswith("ERROR:") and "¿Quisiste decir 'erp_spring_manager'?" in salida


def test_sin_coincidencia_lista_los_disponibles(srv, proyecto):
    """Criterio 7: sin equivalente, se mantiene el mensaje con la lista de proyectos."""
    salida = srv.obtener_contexto(proyecto="no-existe")
    assert salida.startswith("ERROR:") and "Disponibles" in salida and "demo" in salida
    assert "¿Quisiste decir" not in salida


def test_obtener_contexto_avisa_si_la_ruta_ya_no_existe(srv, proyecto):
    """Criterio 8: el contexto de memoria se sigue devolviendo; se antepone la advertencia."""
    normal = srv.obtener_contexto(proyecto="demo")
    assert not normal.startswith("ERROR") and "⚠" not in normal

    shutil.rmtree(proyecto["repo"])
    salida = srv.obtener_contexto(proyecto="demo")
    assert not salida.startswith("ERROR")
    assert str(proyecto["repo"]) in salida and "actualizar_proyecto" in salida
    assert "INDEX" in salida or "demo" in salida   # el contexto de memoria sigue presente, no solo la advertencia


# ───────────────────────── revisión 1: redetectar, docstring, claves huérfanas (T-001) ─────────────────────────

def test_docstring_menciona_redetectar_y_no_la_frase_vieja_contradictoria(srv):
    """Obs. 1 / Criterio C: el docstring describe exactamente los comportamientos alcanzables; antes decía que
    una llamada sin `repositorio` y sin `pruebas` "redetecta todos los repos", pero eso ahora da ERROR salvo
    con `redetectar=True` explícito."""
    doc = srv.actualizar_proyecto.__doc__ or ""
    assert "redetectar" in doc
    assert "sin él y sin pruebas, redetecta" not in doc.lower()
    assert "sin repositorio y sin pruebas, redetecta" not in doc.lower()


def test_actualizar_proyecto_sin_campos_y_sin_redetectar_sigue_dando_error(srv, proyecto, entorno):
    """Criterio B: `redetectar=False` (default) explícito también cuenta como "nada para actualizar"; el
    mensaje de error menciona `redetectar=True` como la forma de redetectar."""
    ruta_config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta_config.read_text()
    salida = srv.actualizar_proyecto(nombre="demo", redetectar=False)
    assert salida.startswith("ERROR:") and "redetectar=True" in salida
    assert ruta_config.read_text() == antes


def test_redetectar_con_pruebas_es_incompatible(srv, proyecto, entorno):
    """Criterio A: `redetectar=True` junto con `pruebas` no vacío devuelve ERROR sin escribir."""
    ruta_config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta_config.read_text()
    salida = srv.actualizar_proyecto(nombre="demo", redetectar=True, pruebas="make test")
    assert salida.startswith("ERROR:")
    assert ruta_config.read_text() == antes


def test_redetectar_un_solo_repo_redetecta_el_proyecto_completo(srv, entorno):
    """Criterio A: en un proyecto de un solo repo, `redetectar=True` sin `pruebas` redetecta el comando
    completo del proyecto (el caso que antes cubría configurar_pruebas() sin argumentos — Obs. 2)."""
    repo = crear_repo(entorno["base"] / "web2")
    srv.registrar_proyecto(nombre="web2", ruta=str(repo), pruebas="make check")
    (repo / "go.mod").write_text("module web2")
    salida = srv.actualizar_proyecto(nombre="web2", redetectar=True)
    assert not salida.startswith("ERROR"), salida
    assert "go test ./..." in salida and "(detectado)" in salida
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["web2"]["pruebas"] == "go test ./..."


def test_redetectar_multirepo_sin_repositorio_redetecta_todos(srv, entorno):
    """Criterio A: en un proyecto de varios repos, `redetectar=True` sin `repositorio` redetecta TODOS."""
    raiz = entorno["base"] / "multi2"
    back = crear_repo(raiz / "backend")
    (back / "pom.xml").write_text("<project/>")
    front = crear_repo(raiz / "frontend")   # sin archivos reconocibles todavía
    srv.registrar_proyecto(nombre="multi2", ruta=str(raiz))
    config_antes = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config_antes["multi2"]["pruebas"] == {"backend": "mvn test"}   # frontend sin nada reconocible aún

    (front / "go.mod").write_text("module frontend")   # ahora sí se puede detectar
    salida = srv.actualizar_proyecto(nombre="multi2", redetectar=True)
    assert not salida.startswith("ERROR"), salida
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["multi2"]["pruebas"] == {"backend": "mvn test", "frontend": "go test ./..."}


def test_cambio_de_ruta_avisa_claves_de_pruebas_huerfanas(srv, entorno):
    """Obs. 3 / Criterio D: si `ruta` cambia en un proyecto multi-repo y el `pruebas` guardado es un dict con
    claves que no corresponden a ningún repo bajo la ruta nueva, el cambio se aplica igual (no bloquea) pero
    la respuesta lista esas claves "huérfanas" y sugiere `actualizar_proyecto(nombre, redetectar=True)`."""
    raiz = entorno["base"] / "multi3"
    back = crear_repo(raiz / "backend")
    (back / "pom.xml").write_text("<project/>")
    front = crear_repo(raiz / "frontend")
    (front / "package.json").write_text('{"scripts": {"test": "vitest"}}')
    srv.registrar_proyecto(nombre="multi3", ruta=str(raiz))
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["multi3"]["pruebas"] == {"backend": "mvn test", "frontend": "npm test"}

    # la ruta nueva solo tiene "backend"; "frontend" queda huérfana
    nueva_raiz = entorno["base"] / "multi3-mudado"
    shutil.copytree(raiz / "backend", nueva_raiz / "backend")   # solo "backend" sobrevive a la mudanza

    salida = srv.actualizar_proyecto(nombre="multi3", ruta=str(nueva_raiz))
    assert not salida.startswith("ERROR"), salida
    assert "huérfanas" in salida and "frontend" in salida and "redetectar=True" in salida
    config = json.loads(Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).read_text())
    assert config["multi3"]["ruta"] == str(nueva_raiz.resolve())
    assert config["multi3"]["pruebas"] == {"backend": "mvn test", "frontend": "npm test"}   # se aplicó el cambio


def test_memoria_sigue_funcionando_si_la_ruta_del_codigo_desaparece(srv, proyecto):
    """Criterio F: la memoria es independiente de la ruta del código (_mem(proyecto) ya no exige que exista).
    registrar_pendiente, registrar_decision y obtener_contexto tienen éxito con la carpeta de código borrada;
    listar_documentos SIGUE fallando porque necesita leer/escribir en esa carpeta vía `escritura` (usa
    _ruta_segura → _raiz(proyecto) con verificar_existe=True por defecto, a diferencia de obtener_contexto que
    llama _raiz(proyecto, verificar_existe=False))."""
    shutil.rmtree(proyecto["repo"])

    salida = srv.registrar_pendiente(proyecto="demo", tema="T", contexto="c")
    assert not salida.startswith("ERROR"), salida

    salida = srv.registrar_decision(proyecto="demo", titulo="D", decision="d", justificacion="j")
    assert not salida.startswith("ERROR"), salida

    salida = srv.obtener_contexto(proyecto="demo")
    assert not salida.startswith("ERROR"), salida

    salida = srv.listar_documentos(proyecto="demo")
    assert salida.startswith("ERROR:") and "no existe" in salida.lower()
