"""analizar_uso.py lee el mismo log que escribe el servidor: --log, luego MEMORIA_PROYECTOS_LOG, luego
<repo>/logs/uso.jsonl (igual que LOG_USO). Si el archivo no existe, lo dice y termina con estado distinto de cero."""
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


def test_ruta_por_defecto_sin_variable_ni_flag(monkeypatch):
    monkeypatch.delenv("MEMORIA_PROYECTOS_LOG", raising=False)
    assert analizar_uso.ruta_log(None) == RAIZ_REPO / "logs" / "uso.jsonl"


def test_archivo_inexistente_avisa_y_sale_con_error(entorno, monkeypatch, capsys):
    faltante = entorno["tmp"] / "no-existe" / "uso.jsonl"
    with pytest.raises(SystemExit) as salida:
        _correr(monkeypatch, "--log", str(faltante))
    assert salida.value.code != 0
    assert str(faltante) in capsys.readouterr().err


def _log_diario(ruta: Path, dias_atras: list[int], llamadas_por_dia: int) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ahora = dt.datetime.now()
    filas = [{"ts": (ahora - dt.timedelta(days=d, minutes=i)).isoformat(timespec="seconds"), "herramienta": "buscar",
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
