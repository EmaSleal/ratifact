"""analizar_uso.py lee el mismo log que escribe el servidor: --log, luego MEMORIA_PROYECTOS_LOG, luego
$XDG_STATE_HOME/ratifact/uso.jsonl (igual que LOG_USO). Si el archivo no existe, lo dice y termina con estado distinto de cero."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

import analizar_uso
from conftest import RAIZ_REPO


def _escribir_log(ruta: Path, herramienta: str) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fila = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "herramienta": herramienta, "proyecto": "demo",
            "ms": 1.0, "resp_chars": 40, "error": False}
    ruta.write_text(json.dumps(fila) + "\n", encoding="utf-8")
    return ruta


def _correr(monkeypatch, *argumentos: str) -> None:
    monkeypatch.setattr(sys, "argv", ["analizar_uso.py", *argumentos])
    analizar_uso.main()


def test_respeta_la_variable_de_entorno(entorno, monkeypatch, capsys):
    _escribir_log(Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]), "herramienta_del_entorno")
    _correr(monkeypatch)
    assert "herramienta_del_entorno" in capsys.readouterr().out


def test_log_tiene_prioridad_sobre_la_variable(entorno, monkeypatch, capsys):
    _escribir_log(Path(entorno["env"]["MEMORIA_PROYECTOS_LOG"]), "herramienta_del_entorno")
    otro = _escribir_log(entorno["tmp"] / "otro" / "uso.jsonl", "herramienta_del_flag")
    _correr(monkeypatch, "--log", str(otro), "--dias", "3")
    salida = capsys.readouterr().out
    assert "herramienta_del_flag" in salida and "herramienta_del_entorno" not in salida
    assert "últimos 3 días" in salida


def test_ruta_por_defecto_sin_variable_ni_flag(monkeypatch, tmp_path):
    """T-012: el log por defecto sale del repositorio a $XDG_STATE_HOME/ratifact/uso.jsonl (~/.local/state si no)."""
    monkeypatch.delenv("MEMORIA_PROYECTOS_LOG", raising=False)
    monkeypatch.delenv("RATIFACT_LOG", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "estado"))
    assert analizar_uso.ruta_log(None) == tmp_path / "estado" / "ratifact" / "uso.jsonl"
    monkeypatch.delenv("XDG_STATE_HOME")
    assert analizar_uso.ruta_log(None) == Path.home() / ".local" / "state" / "ratifact" / "uso.jsonl"
    assert RAIZ_REPO not in analizar_uso.ruta_log(None).parents


def test_archivo_inexistente_avisa_y_sale_con_error(entorno, monkeypatch, capsys):
    faltante = entorno["tmp"] / "no-existe" / "uso.jsonl"
    with pytest.raises(SystemExit) as salida:
        _correr(monkeypatch, "--log", str(faltante))
    assert salida.value.code != 0
    assert str(faltante) in capsys.readouterr().err


def _log_diario(ruta: Path, dias_atras: list[int], llamadas_por_dia: int) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ahora = dt.datetime.now()
    filas = [{"ts": (ahora - dt.timedelta(days=d, minutes=i)).isoformat(timespec="seconds"), "herramienta": "search",
              "proyecto": "demo", "ms": 1.0, "resp_chars": 40, "error": False}
             for d in dias_atras for i in range(llamadas_por_dia)]
    ruta.write_text("\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    return ruta


def test_criterio_2_cuenta_dias_corridos_no_dias_con_uso(entorno, monkeypatch, capsys):
    """ADR-009 pide 14 días consecutivos de telemetría: un día sin llamadas no rompe la ventana (caso real 2026-10-17:
    1202 llamadas, 0,08 %, telemetría desde el 3 de octubre pero 13 días con uso)."""
    dias = [d for d in range(0, 15) if d != 12]                      # 14 días cubiertos, uno sin uso
    log = _log_diario(entorno["tmp"] / "log" / "uso.jsonl", dias + [14], 25)
    _correr(monkeypatch, "--log", str(log), "--dias", "15")
    assert "→ CUMPLE" in capsys.readouterr().out


def test_criterio_2_no_cumple_con_menos_de_14_dias_de_telemetria(entorno, monkeypatch, capsys):
    log = _log_diario(entorno["tmp"] / "log" / "uso.jsonl", list(range(0, 10)), 40)   # 400 llamadas en 10 días
    _correr(monkeypatch, "--log", str(log), "--dias", "14")
    assert "→ aún no" in capsys.readouterr().out


def _log_filas(ruta: Path, filas: list[dict]) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ahora = dt.datetime.now()
    base = {"proyecto": "demo", "ms": 1.0, "error": False}
    ruta.write_text("\n".join(json.dumps({**base, "ts": (ahora - dt.timedelta(minutes=i)).isoformat(timespec="seconds"), **f})
                              for i, f in enumerate(filas)) + "\n", encoding="utf-8")
    return ruta


def test_tamanos_de_respuesta_por_herramienta(entorno, monkeypatch, capsys):
    """T-007: p50/p90/máx de resp_chars por herramienta y las 5 respuestas más grandes."""
    filas = [{"herramienta": "search", "resp_chars": c} for c in range(10, 110, 10)]          # 10..100
    filas += [{"herramienta": "read_document", "resp_chars": 5000, "ruta": "docs/grande.md", "proyecto": "otro"}]
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)
    _correr(monkeypatch, "--log", str(log))
    salida = capsys.readouterr().out
    tamanos = salida.split("Tamaño de respuesta por herramienta")[1].split("\n\n")[0].splitlines()
    assert next(l for l in tamanos if l.startswith("search")).split()[1:] == ["60", "100", "100"]
    seccion = salida.split("Respuestas más grandes")[1].splitlines()
    assert "read_document" in seccion[1] and "otro" in seccion[1] and "5000" in seccion[1] and "docs/grande.md" in seccion[1]
    assert len([l for l in seccion[1:] if l.startswith("  ")]) == 5


def test_lecturas_de_codigo_por_proyecto_y_sin_indicador_sin_rango(entorno, monkeypatch, capsys):
    filas = [{"herramienta": "read_document", "resp_chars": 100, "ruta": "src/A.java"},
             {"herramienta": "read_document", "resp_chars": 50, "ruta": "web/b.vue"},
             {"herramienta": "read_document", "resp_chars": 70, "ruta": "x.yaml", "proyecto": "otro"},
             {"herramienta": "read_document", "resp_chars": 999, "ruta": ".project/INDEX.md"},
             {"herramienta": "search", "resp_chars": 10}]
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", filas)
    _correr(monkeypatch, "--log", str(log))
    salida = capsys.readouterr().out
    assert "sin rango" not in salida
    linea = next(l for l in salida.splitlines() if l.startswith("- Lecturas de código"))
    assert "demo: 2 (150 caracteres)" in linea and "otro: 1 (70 caracteres)" in linea


# ───────────────────────── T-008: indicador de decisiones desde la memoria ─────────────────────────

def _adr(carpeta: Path, id_: str, estado: str, fecha: dt.date, titulo: str) -> None:
    """ADR en la carpeta indicada; con claves v1 si la carpeta es la v1 (decisiones/), si no v2 (decisions/)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    titulo_, estado_, fecha_, creado_ = (("titulo", "estado", "fecha", "creado") if carpeta.name == "decisiones"
                                        else ("title", "status", "date", "created"))
    (carpeta / f"{id_}-x.md").write_text(
        f"---\nid: {id_}\n{titulo_}: {titulo}\n{estado_}: {estado}\n{fecha_}: {fecha.isoformat()}\n"
        f"{creado_}: {fecha.isoformat()}T10:00:00\n---\n# {id_} — {titulo}\n", encoding="utf-8")


def _memorias(entorno) -> dict:
    """Dos proyectos: 'demo' con memoria explícita y aún en schema v1 (T-010: analizar_uso lee las dos versiones) y
    'otro' sin clave de memoria y todavía en la ruta por defecto vieja (<base>/.memorias/otro), ya en v2."""
    hoy = dt.date.today()
    mem_demo = entorno["tmp"] / "mem-demo"
    _adr(mem_demo / "decisiones", "ADR-001", "acordada", hoy, "Usar git")
    _adr(mem_demo / "decisiones", "ADR-002", "propuesta", hoy - dt.timedelta(days=2), "Reciente")
    _adr(mem_demo / "decisiones", "ADR-003", "propuesta", hoy - dt.timedelta(days=9), "Vieja abierta")
    _adr(mem_demo / "decisiones", "ADR-004", "reemplazada", hoy - dt.timedelta(days=1), "Cambiada")
    _adr(mem_demo / "decisiones", "ADR-005", "acordada", hoy - dt.timedelta(days=40), "Fuera de ventana")
    _adr(entorno["base"] / ".memorias" / "otro" / "decisions", "ADR-010", "rejected", hoy, "No va")
    config = {"demo": {"ruta": str(entorno["base"] / "demo"), "memoria": str(mem_demo)},
              "otro": {"ruta": str(entorno["base"] / "otro")}}
    Path(entorno["env"]["MEMORIA_PROYECTOS_CONFIG"]).write_text(json.dumps(config), encoding="utf-8")
    return config


def test_decisiones_por_estado_desde_la_memoria(entorno, monkeypatch, capsys):
    _memorias(entorno)
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl",
                     [{"herramienta": "accept_decision", "resp_chars": 10}] * 3)
    _correr(monkeypatch, "--log", str(log), "--dias", "14")
    salida = capsys.readouterr().out
    assert "confirmadas por el usuario" not in salida
    linea = next(l for l in salida.splitlines() if l.startswith("- Decisiones creadas en el período"))
    assert "demo: accepted 1 · proposed 2 · superseded 1 · rejected 0" in linea       # v1, normalizado
    assert "otro: accepted 0 · proposed 0 · superseded 0 · rejected 1" in linea
    viejas = salida.split("- Propuestas abiertas hoy: 2 · con más de 7 días: 1")[1].splitlines()
    fecha = (dt.date.today() - dt.timedelta(days=9)).isoformat()
    assert viejas[1] == f"  demo ADR-003 {fecha} Vieja abierta"


def test_decisiones_respetan_el_filtro_de_proyecto(entorno, monkeypatch, capsys):
    _memorias(entorno)
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl",
                     [{"herramienta": "search", "resp_chars": 10, "proyecto": "otro"}])
    _correr(monkeypatch, "--log", str(log), "--proyecto", "otro")
    linea = next(l for l in capsys.readouterr().out.splitlines() if l.startswith("- Decisiones creadas"))
    assert "otro:" in linea and "demo:" not in linea


def test_decisiones_sin_projects_json_lo_dice(entorno, monkeypatch, capsys):
    log = _log_filas(entorno["tmp"] / "log" / "uso.jsonl", [{"herramienta": "search", "resp_chars": 10}])
    _correr(monkeypatch, "--log", str(log))
    assert f"sin configuración ({entorno['env']['MEMORIA_PROYECTOS_CONFIG']})" in capsys.readouterr().out


def test_ruta_de_configuracion_igual_que_el_servidor(monkeypatch):
    monkeypatch.delenv("MEMORIA_PROYECTOS_CONFIG", raising=False)
    assert analizar_uso.ruta_config() == Path.home() / ".config" / "memoria-proyectos" / "projects.json"
