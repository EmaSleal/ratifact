"""Paquete instalable (T-012, criterios 1 y 2): `uv tool install <repo>` deja el ejecutable `ratifact` (copia fija, no
editable) y `ratifact serve` no escribe nada dentro de site-packages: la telemetría va a $XDG_STATE_HOME/ratifact.
Instala en carpetas temporales (HOME, UV_TOOL_DIR, UV_TOOL_BIN_DIR); tarda unos segundos (usa la caché de uv)."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import RAIZ_REPO, crear_repo

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv no está instalado")


def _arbol(raiz: Path) -> dict[str, str]:
    return {p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(raiz.rglob("*")) if p.is_file()}


def _mensajes(*mensajes: dict) -> str:
    return "".join(json.dumps(m) + "\n" for m in mensajes)


IDENTIDAD_GIT = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "pruebas",
                 "GIT_AUTHOR_EMAIL": "pruebas@local", "GIT_COMMITTER_NAME": "pruebas",
                 "GIT_COMMITTER_EMAIL": "pruebas@local"}     # sin depender de una identidad git global


def test_instalacion_fija_y_serve_no_escribe_en_site_packages(tmp_path, monkeypatch):
    for k, v in IDENTIDAD_GIT.items():
        monkeypatch.setenv(k, v)
    estado_repo = subprocess.run(["git", "-C", str(RAIZ_REPO), "status", "--porcelain"], capture_output=True,
                                 text=True).stdout
    home = tmp_path / "home"
    base = home / "Projects"
    repo = crear_repo(base / "demo")
    config = home / ".config" / "ratifact" / "projects.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"demo": {"path": str(repo), "memory": str(base / ".ratifact" / "demo")}}))
    cache = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True).stdout.strip()   # la del usuario
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RATIFACT_", "MEMORIA_PROYECTOS_", "XDG_",
                                                                       "VIRTUAL_ENV", "UV_TOOL"))}
    env.update(HOME=str(home), UV_CACHE_DIR=cache, UV_TOOL_DIR=str(tmp_path / "tools"), UV_TOOL_BIN_DIR=str(tmp_path / "bin"),
               XDG_STATE_HOME=str(home / ".local" / "state"), XDG_DATA_HOME=str(home / ".local" / "share"))
    r = subprocess.run(["uv", "tool", "install", "--compile-bytecode", "--python", "3.10", str(RAIZ_REPO)],
                       capture_output=True, text=True, env=env, timeout=300)
    if r.returncode != 0 and "No interpreter found" in r.stderr:
        r = subprocess.run(["uv", "tool", "install", "--compile-bytecode", str(RAIZ_REPO)], capture_output=True,
                           text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr
    ratifact = tmp_path / "bin" / "ratifact"
    sitio = next((tmp_path / "tools" / "ratifact").glob("lib/python*/site-packages"))
    assert (sitio / "ratifact" / "cli.py").is_file()                                       # copia, no editable
    assert not any(str(RAIZ_REPO) in pth.read_text() for pth in sitio.glob("*.pth"))
    assert subprocess.run([str(ratifact), "--version"], capture_output=True, text=True, env=env).stdout.strip() \
        == "ratifact 1.0.1"
    antes = _arbol(sitio)

    entrada = _mensajes(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "prueba", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_projects", "arguments": {}}})
    proc = subprocess.Popen([str(ratifact), "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, cwd=tmp_path)
    proc.stdin.write(entrada)
    proc.stdin.flush()
    respuestas = [proc.stdout.readline(), proc.stdout.readline()]
    proc.stdin.close()
    proc.wait(timeout=30)
    assert '"id":2' in respuestas[1].replace(" ", "") and "demo" in respuestas[1], respuestas

    doctor = subprocess.run([str(ratifact), "doctor"], capture_output=True, text=True, env=env)
    assert f"Running from: fixed installation {sitio / 'ratifact'} · installed from {RAIZ_REPO}" in doctor.stdout
    assert _arbol(sitio) == antes
    log = home / ".local" / "state" / "ratifact" / "uso.jsonl"
    assert json.loads(log.read_text().splitlines()[-1])["herramienta"] == "list_projects"
    assert subprocess.run(["git", "-C", str(RAIZ_REPO), "status", "--porcelain"], capture_output=True,
                          text=True).stdout == estado_repo      # construir el paquete no ensucia el repositorio
