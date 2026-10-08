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
    """Criterio 2: ADR-010 también se aplica al actualizar (no solo al dar de alta)."""
    repo = crear_repo(entorno["base"] / "interno2")
    srv.registrar_proyecto(nombre="interno2", ruta=str(repo))   # memoria en <base>/.memorias/interno2
    ruta_config = Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"])
    antes = ruta_config.read_text()

    salida = srv.actualizar_proyecto(nombre="interno2", ruta=str(entorno["base"]))   # contendría la memoria
    assert salida.startswith("ERROR:") and "ADR-010" in salida
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
