"""T-013 criterion 11: the repository can be published without personal data. No versioned file (`git ls-files`) may
contain a home path `/home/<username>/…` nor an e-mail address.

Exclusion (synthetic fixtures): inside tests/, the made-up user `u` (`/home/u/…`) is allowed, because some tests need
a literal absolute path that looks like a real one. Any other user name, anywhere, fails; outside tests/ no
`/home/<name>` path is allowed at all (use `~` or `<home>` in the docs)."""
from __future__ import annotations

import re
import subprocess

import pytest

from conftest import RAIZ_REPO

HOGAR = re.compile(r"/home/([A-Za-z0-9._-]+)")
CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
USUARIOS_SINTETICOS = {"u"}           # only in tests/
CORREOS_PERMITIDOS: set[str] = set()      # none expected: adding one must be a conscious decision


def _versionados() -> list[str]:
    r = subprocess.run(["git", "-C", str(RAIZ_REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("not a git checkout")
    return [f for f in r.stdout.split("\0") if f and (RAIZ_REPO / f).is_file() and not (RAIZ_REPO / f).is_symlink()]


def _texto(archivo: str) -> str:
    try:
        return (RAIZ_REPO / archivo).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def test_ningun_archivo_versionado_tiene_rutas_de_usuario():
    hallazgos = []
    for archivo in _versionados():
        for n, linea in enumerate(_texto(archivo).splitlines(), 1):
            for m in HOGAR.finditer(linea):
                if not (archivo.startswith("tests/") and m.group(1) in USUARIOS_SINTETICOS):
                    hallazgos.append(f"{archivo}:{n}: {m.group(0)}")
    assert not hallazgos, "home paths in versioned files (use ~ or <home>):\n" + "\n".join(hallazgos)


def test_ningun_archivo_versionado_tiene_correos():
    hallazgos = [f"{archivo}:{n}: {m.group(0)}" for archivo in _versionados()
                 for n, linea in enumerate(_texto(archivo).splitlines(), 1)
                 for m in CORREO.finditer(linea) if m.group(0) not in CORREOS_PERMITIDOS]
    assert not hallazgos, "e-mail addresses in versioned files:\n" + "\n".join(hallazgos)


def test_gitignore_cubre_configuracion_y_respaldos():
    reglas = (RAIZ_REPO / ".gitignore").read_text().splitlines()
    for regla in ("projects.json", "projects.json.bak-*", "*.bak-ratifact-*"):
        assert regla in reglas, regla
