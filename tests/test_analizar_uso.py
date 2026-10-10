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
