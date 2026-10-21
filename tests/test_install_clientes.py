"""`ratifact install` (T-013, criteria 1–3): each client file is parsed, edited and validated before an atomic replace,
with a `<file>.bak-ratifact-<date>` backup; the `ratifact` entry replaces `memoria-proyectos` (never both); every other
entry stays identical; an invalid input file is reported and left untouched. Everything runs in a temporary HOME."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

EXE = "/opt/tools/bin/ratifact"

try:
    import tomllib as _toml
except ModuleNotFoundError:          # Python 3.10: the installed package depends on tomli (pyproject marker)
    try:
        import tomli as _toml
    except ModuleNotFoundError:
        _toml = None
necesita_toml = pytest.mark.skipif(_toml is None, reason="no TOML parser (Python 3.10 without tomli)")


@pytest.fixture
def casa(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("sys.platform", "linux")
    return home


def _escribir(ruta: Path, texto: str) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def _cliente(nombre: str, casa: Path, correr=None, claude: str | None = None):
    from ratifact import clientes
    return next(c for c in clientes.clientes(claude=claude) if c.nombre == nombre)


def _backups(ruta: Path) -> list[Path]:
    return sorted(ruta.parent.glob(ruta.name + ".bak-ratifact-*"))


# ───────────────────────── JSON clients ─────────────────────────

DESKTOP = {
    "mcpServers": {
        "call-copilot": {"command": "/x/call-copilot-mcp"},
        "memoria-proyectos": {"command": "uv", "args": ["run", "--script", "/r/servidor.py"],
                              "env": {"MEMORIA_PROYECTOS_CONFIG": "/r/projects.json"}},
        "otro": {"command": "npx", "args": ["-y", "otro"], "env": {"TOKEN": "x"}},
    },
    "preferences": {"sidebarMode": "chat", "desconocida": [1, {"a": None}]},
    "claveRara": True,
}


@pytest.mark.parametrize("nombre,relativa", [
    ("claude-desktop", ".config/Claude/claude_desktop_config.json"),
    ("pi", ".pi/agent/mcp.json"),
    ("claude-code", ".claude.json"),
])
def test_json_reemplaza_la_clave_vieja_y_conserva_el_resto(casa, nombre, relativa):
    from ratifact import clientes
    ruta = _escribir(casa / relativa, json.dumps(DESKTOP, indent=2))
    c = _cliente(nombre, casa)
    assert c.encontrado and c.archivo == ruta
    plan = clientes.planificar(c, EXE)
    assert plan.estado == clientes.VIEJA and plan.cambia
    assert ruta.read_text() == json.dumps(DESKTOP, indent=2)                   # planning writes nothing
    clientes.aplicar(plan)
    nuevo = json.loads(ruta.read_text())
    servidores = nuevo.pop("mcpServers")
    assert nuevo == {k: v for k, v in DESKTOP.items() if k != "mcpServers"}    # preferences & unknown keys identical
    assert list(servidores) == ["call-copilot", "ratifact", "otro"]            # same position, not both
    assert servidores["call-copilot"] == DESKTOP["mcpServers"]["call-copilot"]
    assert servidores["otro"] == DESKTOP["mcpServers"]["otro"]
    esperado = {"command": EXE, "args": ["serve"]}
    if nombre == "claude-code":
        esperado = {"type": "stdio", **esperado}
    assert servidores["ratifact"] == esperado                                  # no env vars
    [bak] = _backups(ruta)
    assert json.loads(bak.read_text()) == DESKTOP
    assert clientes.planificar(_cliente(nombre, casa), EXE).estado == clientes.CONFIGURADO


def test_json_conserva_claves_extra_de_la_entrada_vieja(casa):
    from ratifact import clientes
    pi = {"mcpServers": {"memoria-proyectos": {"command": "uv", "args": ["x"], "lifecycle": "lazy",
                                               "directTools": False, "env": {"A": "1"}}}}
    ruta = _escribir(casa / ".pi/agent/mcp.json", json.dumps(pi))
    clientes.aplicar(clientes.planificar(_cliente("pi", casa), EXE))
    assert json.loads(ruta.read_text())["mcpServers"] == {
        "ratifact": {"command": EXE, "args": ["serve"], "lifecycle": "lazy", "directTools": False}}


def test_json_invalido_da_error_claro_y_no_toca_el_archivo(casa):
    from ratifact import clientes
    texto = '{\n  "mcpServers": {\n    "a": {"command": "x"},\n  }\n}\n'          # the stray comma of 2026-10-20
    ruta = _escribir(casa / ".config/Claude/claude_desktop_config.json", texto)
    plan = clientes.planificar(_cliente("claude-desktop", casa), EXE)
    assert plan.estado.startswith("error") and "not valid JSON" in plan.error and str(ruta) in plan.error
    assert "line 4" in plan.error
    with pytest.raises(clientes.ErrorInstalacion):
        clientes.aplicar(plan)
    assert ruta.read_text() == texto and not _backups(ruta)


def test_json_sin_mcpservers_o_cliente_sin_archivo(casa):
    from ratifact import clientes
    (casa / ".config" / "Claude").mkdir(parents=True)                        # Claude Desktop installed, no file yet
    c = _cliente("claude-desktop", casa)
    plan = clientes.planificar(c, EXE)
    assert c.encontrado and plan.estado == clientes.SIN_CONFIGURAR
    clientes.aplicar(plan)
    assert json.loads(c.archivo.read_text()) == {"mcpServers": {"ratifact": {"command": EXE, "args": ["serve"]}}}
    assert not _backups(c.archivo)                                           # nothing to back up
    assert _cliente("pi", casa).encontrado is False
    assert clientes.planificar(_cliente("pi", casa), EXE).estado == clientes.NO_ENCONTRADO


def test_ruta_de_claude_desktop_en_macos(casa, monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    from ratifact import clientes
    c = next(c for c in clientes.clientes() if c.nombre == "claude-desktop")
    assert c.archivo == casa / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def test_escritura_atomica_valida_antes_de_reemplazar(casa, monkeypatch):
    from ratifact import archivos
    ruta = _escribir(casa / "a.json", '{"a": 1}')
    os.chmod(ruta, 0o600)

    def invalido(texto):
        raise archivos.ErrorInstalacion("bad")
    with pytest.raises(archivos.ErrorInstalacion):
        archivos.escribir_validado(ruta, '{"a": 2}', invalido)
    assert ruta.read_text() == '{"a": 1}' and not _backups(ruta) and not list(casa.glob("*.tmp"))
    bak = archivos.escribir_validado(ruta, '{"a": 2}', archivos.validar_json)
    assert ruta.read_text() == '{"a": 2}' and bak.read_text() == '{"a": 1}' and oct(ruta.stat().st_mode)[-3:] == "600"
    assert bak.name.startswith("a.json.bak-ratifact-")
    bak2 = archivos.escribir_validado(ruta, '{"a": 3}', archivos.validar_json)
    assert bak2 != bak and bak.read_text() == '{"a": 1}'                    # a backup is never overwritten


# ───────────────────────── Claude Code through the `claude` CLI ─────────────────────────

class ClaudeFalso:
    """Stands in for `claude mcp add/remove --scope user`: edits ~/.claude.json like the real CLI."""

    def __init__(self, ruta: Path):
        self.ruta, self.llamadas = ruta, []

    def __call__(self, args, **kwargs):
        import subprocess
        self.llamadas.append(args[1:])
        datos = json.loads(self.ruta.read_text()) if self.ruta.exists() else {}
        servidores = datos.setdefault("mcpServers", {})
        if args[1:3] == ["mcp", "remove"]:
            servidores.pop(args[3])
        elif args[1:3] == ["mcp", "add"]:
            i = args.index("--")
            servidores[args[i - 1]] = {"type": "stdio", "command": args[i + 1], "args": args[i + 2:], "env": {}}
        self.ruta.write_text(json.dumps(datos, indent=2))
        return subprocess.CompletedProcess(args, 0, "", "")


def test_claude_code_usa_claude_mcp_add_si_existe_el_ejecutable(casa):
    from ratifact import clientes
    ruta = _escribir(casa / ".claude.json", json.dumps({"numStartups": 3, "mcpServers": {
        "codegraph": {"command": "codegraph"}, "memoria-proyectos": {"command": "/old/ratifact", "args": ["serve"]}}}))
    falso = ClaudeFalso(ruta)
    c = _cliente("claude-code", casa, claude="/usr/bin/claude")
    plan = clientes.planificar(c, EXE)
    assert plan.estado == clientes.VIEJA and "claude mcp add" in plan.descripcion
    clientes.aplicar(plan, correr=falso)
    assert falso.llamadas == [["mcp", "remove", "memoria-proyectos", "--scope", "user"],
                              ["mcp", "add", "--scope", "user", "ratifact", "--", EXE, "serve"]]
    datos = json.loads(ruta.read_text())
    assert datos["numStartups"] == 3 and set(datos["mcpServers"]) == {"codegraph", "ratifact"}
    assert len(_backups(ruta)) == 1
    assert clientes.planificar(c, EXE).estado == clientes.CONFIGURADO       # empty env counts as no env


def test_claude_code_cli_que_falla_es_un_error_claro(casa):
    import subprocess
    from ratifact import clientes
    _escribir(casa / ".claude.json", "{}")
    plan = clientes.planificar(_cliente("claude-code", casa, claude="/usr/bin/claude"), EXE)
    with pytest.raises(clientes.ErrorInstalacion, match="claude mcp add.*boom"):
        clientes.aplicar(plan, correr=lambda a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))


# ───────────────────────── Codex (TOML, bounded edit) ─────────────────────────

CODEX = '''model = "gpt-5"
# a comment that must survive
[features]
hooks = true

[mcp_servers.codegraph]
command = "codegraph"
args = ["serve", "--mcp"]

[mcp_servers.memoria-proyectos]
command = "uv"
args = [
  "run", "--script",
  "/r/servidor.py",   # trailing comment
]
startup_timeout_sec = 30

[mcp_servers.memoria-proyectos.env]
MEMORIA_PROYECTOS_CONFIG = "/r/projects.json"

[mcp_servers.memoria-proyectos.tools.obtener_contexto]
approval_mode = "approve"

[mcp_servers.memoria-proyectos.tools.search]
approval_mode = "approve"

[projects."/home/u/x"]
trust_level = "trusted"
unknown = { a = 1, b = [true] }
'''


@necesita_toml
def test_codex_reemplaza_la_tabla_y_conserva_el_resto(casa):
    from ratifact import clientes
    ruta = _escribir(casa / ".codex/config.toml", CODEX)
    plan = clientes.planificar(_cliente("codex", casa), EXE)
    assert plan.estado == clientes.VIEJA
    clientes.aplicar(plan)
    texto = ruta.read_text()
    antes, despues = _toml.loads(CODEX), _toml.loads(texto)
    assert despues["mcp_servers"]["ratifact"] == {
        "command": EXE, "args": ["serve"], "startup_timeout_sec": 30,
        "tools": {"get_context": {"approval_mode": "approve"}, "search": {"approval_mode": "approve"}}}
    assert "memoria-proyectos" not in despues["mcp_servers"]
    for k in ("model", "features", "projects"):
        assert despues[k] == antes[k]
    assert despues["mcp_servers"]["codegraph"] == antes["mcp_servers"]["codegraph"]
    assert texto.startswith('model = "gpt-5"\n# a comment that must survive\n[features]')   # untouched text
    assert '[projects."/home/u/x"]\ntrust_level = "trusted"\nunknown = { a = 1, b = [true] }\n' in texto
    assert [b.read_text() for b in _backups(ruta)] == [CODEX]
    assert clientes.planificar(_cliente("codex", casa), EXE).estado == clientes.CONFIGURADO


@necesita_toml
def test_codex_sin_entrada_agrega_la_tabla_al_final(casa):
    from ratifact import clientes
    ruta = _escribir(casa / ".codex/config.toml", 'model = "x"\n')
    plan = clientes.planificar(_cliente("codex", casa), EXE)
    assert plan.estado == clientes.SIN_CONFIGURAR
    clientes.aplicar(plan)
    assert _toml.loads(ruta.read_text()) == {"model": "x", "mcp_servers": {"ratifact": {"command": EXE,
                                                                                       "args": ["serve"]}}}


@necesita_toml
def test_codex_con_las_dos_claves_deja_solo_ratifact(casa):
    from ratifact import clientes
    texto = ('[mcp_servers.ratifact]\ncommand = "/viejo"\nargs = ["serve"]\n[mcp_servers.ratifact.tools.search]\n'
             'approval_mode = "prompt"\n\n[mcp_servers.memoria-proyectos]\ncommand = "uv"\n'
             '[mcp_servers.memoria-proyectos.tools.get_context]\napproval_mode = "approve"\n')
    ruta = _escribir(casa / ".codex/config.toml", texto)
    clientes.aplicar(clientes.planificar(_cliente("codex", casa), EXE))
    assert _toml.loads(ruta.read_text())["mcp_servers"] == {"ratifact": {
        "command": EXE, "args": ["serve"], "tools": {"search": {"approval_mode": "prompt"}}}}


@necesita_toml
@pytest.mark.parametrize("texto", [
    '[mcp_servers]\nmemoria-proyectos = { command = "uv" }\n',            # inline table: outside the bounded edit
    'mcp_servers.memoria-proyectos.command = "uv"\n',
    '[mcp_servers.memoria-proyectos]\ncommand = """uv"""\n',
])
def test_codex_fuera_del_formato_conocido_no_se_toca_y_da_instrucciones(casa, texto):
    from ratifact import clientes
    ruta = _escribir(casa / ".codex/config.toml", texto)
    plan = clientes.planificar(_cliente("codex", casa), EXE)
    assert plan.estado.startswith("error") and "[mcp_servers.ratifact]" in plan.error, plan.error
    assert ruta.read_text() == texto


def test_codex_toml_invalido_no_se_toca(casa):
    from ratifact import clientes
    if _toml is None:
        pytest.skip("no TOML parser")
    ruta = _escribir(casa / ".codex/config.toml", "model = \n")
    plan = clientes.planificar(_cliente("codex", casa), EXE)
    assert plan.estado.startswith("error") and "not valid TOML" in plan.error and ruta.read_text() == "model = \n"
