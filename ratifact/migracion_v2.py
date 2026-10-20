"""Migración del esquema v1 → v2 (docs/v1-english-naming.md §2, §5, §6, §8 y addendum; ADR-028, ADR-029, ADR-030):
carpetas (git mv), claves y estados del frontmatter, títulos de sección conocidos y las dos etiquetas de los bloques
de revisión; las vistas se regeneran. El cuerpo de los registros no cambia: solo el bloque de frontmatter y las líneas
de título/etiqueta mapeadas (sin modelo de por medio, mapeo determinista). INDEX.md y docs/ no se tocan.
La llama ratifact.esquema bajo el bloqueo, con el repo limpio y el tag pre-v2 ya creado; devuelve el informe que va
en el cuerpo del commit."""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

from ratifact.registros import _escribir_atomico, _regenerar_vistas_en
from ratifact.vocabulario import CARPETAS_V1, CLAVES_V1, ESTADOS_V1, TIPO_DE_CARPETA_V1, VISTAS_V1

PREFIJOS = {"decisiones": "ADR", "pendientes": "P", "tareas": "T"}
CLAVES_SIN_CAMBIO = {"id", "commit"}

# títulos de sección fijos, por tipo de registro (línea completa)
TITULOS = {
    "decision": {"## Decisión": "## Decision", "## Justificación": "## Rationale",
                 "## Alternativas consideradas": "## Alternatives considered"},
    "pendiente": {},
    "tarea": {"## Objetivo": "## Goal", "## Criterios de aceptación": "## Acceptance criteria",
              "## Resuelve": "## Resolves", "## Decisiones aplicables": "## Applicable decisions",
              "## Archivos involucrados": "## Files involved", "## Fuera de alcance": "## Out of scope",
              "## Notas": "## Notes", "## Cómo verificar": "## How to verify", "## Resultado": "## Result"},
}
FECHA = r"\d{4}-\d{2}-\d{2}"
# títulos con fecha o número, por tipo: (patrón, reemplazo)
TITULOS_PATRON = {
    "decision": [(re.compile(rf"^## Confirmación \(({FECHA})\)$"), r"## Acceptance (\1)"),
                 (re.compile(rf"^## Confirmación \(({FECHA}), en lote\)$"), r"## Acceptance (\1, batch)"),
                 (re.compile(rf"^## Descartada \(({FECHA})\)$"), r"## Rejected (\1)"),
                 (re.compile(rf"^## Resolución \(({FECHA})\)$"), r"## Resolution (\1)")],
    "pendiente": [(re.compile(rf"^## Resolución \(({FECHA})\)$"), r"## Resolution (\1)")],
    "tarea": [(re.compile(rf"^### Revisión (\d+) · ({FECHA}) · devuelta$"), r"### Review \1 · \2 · changes_requested")],
}
ESTADO_EN_TITULO = re.compile(rf"^### ({FECHA}) · (\w+)$")      # "### 2026-10-17 · en_revision" (Resultado)
INICIO_REVISION = re.compile(r"^### Revisión \d+( |$)")
ETIQUETAS_REVISION = {"**Observaciones**": "**Findings**", "**Criterios adicionales**": "**Additional criteria**"}
TITULO_SESIONES = re.compile(rf"^# Sesiones ({FECHA})$")
FRONTMATTER = re.compile(r"^---\r?\n(.*?\r?\n)---(\r?\n|$)", re.S)
LINEA_CLAVE = re.compile(r"^([A-Za-z_]+)(\s*:\s*)(.*?)(\s*)$")
PARCIAL = re.compile(r"\(\s*parcial\s*\)", re.I)


class Informe:
    """Lo que la migración hizo y lo que dejó como estaba, para el cuerpo del commit."""

    def __init__(self):
        self.carpetas: list[str] = []
        self.registros = Counter()
        self.claves_sin_mapeo = Counter()
        self.estados_sin_mapeo = Counter()
        self.titulos_libres = Counter()
        self.otros_archivos: list[str] = []

    def lineas(self) -> list[str]:
        def lista(c: Counter) -> str:
            return ", ".join(f"{k} ×{n}" for k, n in sorted(c.items())) or "(none)"
        salida = ["Folders: " + ("; ".join(self.carpetas) or "(none)"),
                  "Records rewritten: " + lista(self.registros),
                  f"Views: {', '.join(VISTAS_V1)} → {', '.join(VISTAS_V1.values())} (regenerated)",
                  "Frontmatter keys left as is: " + lista(self.claves_sin_mapeo),
                  "State values left as is: " + lista(self.estados_sin_mapeo),
                  "Non-record files moved without changes: " + (", ".join(self.otros_archivos) or "(none)"),
                  f"Headings left untouched (free text, {len(self.titulos_libres)} distinct):"]
        return salida + [f"  {t} ×{n}" for t, n in sorted(self.titulos_libres.items())]


def _git(mem: Path, *args: str) -> None:
    r = subprocess.run(["git", "-C", str(mem), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {(r.stdout + r.stderr).strip()[:200]}")


def _versionado(mem: Path, relativa: str) -> bool:
    r = subprocess.run(["git", "-C", str(mem), "ls-files", "--", relativa], capture_output=True, text=True)
    return bool(r.stdout.strip())


def _migrar_frontmatter(bloque: str, tipo: str, informe: Informe) -> str:
    """Solo el bloque entre los dos `---`: claves por CLAVES_V1, el estado por el mapa de su tipo y "(parcial)" de
    `resuelve`. Las líneas que no son `clave: valor` y las claves desconocidas quedan idénticas."""
    salida = []
    for linea in bloque.splitlines(keepends=True):
        fin = linea[len(linea.rstrip("\r\n")):]
        m = LINEA_CLAVE.match(linea.rstrip("\r\n"))
        if not m:
            salida.append(linea)
            continue
        clave, sep, valor, cola = m.groups()
        if clave not in CLAVES_V1:
            if clave not in CLAVES_SIN_CAMBIO:
                informe.claves_sin_mapeo[clave] += 1
            salida.append(linea)
            continue
        if clave == "estado":
            if valor in ESTADOS_V1[tipo]:
                valor = ESTADOS_V1[tipo][valor]
            else:
                informe.estados_sin_mapeo[f"{tipo}:{valor}"] += 1
        elif clave == "resuelve":
            valor = PARCIAL.sub("(partial)", valor)
        salida.append(f"{CLAVES_V1[clave]}{sep}{valor}{cola}{fin}")
    return "".join(salida)


def _titulo(linea: str, tipo: str) -> str | None:
    """Título v2 de una línea de título conocida de un registro de `tipo`, o None."""
    if linea in TITULOS[tipo]:
        return TITULOS[tipo][linea]
    for patron, reemplazo in TITULOS_PATRON[tipo]:
        if patron.match(linea):
            return patron.sub(reemplazo, linea)
    m = ESTADO_EN_TITULO.match(linea) if tipo == "tarea" else None
    if m and m.group(2) in ESTADOS_V1["tarea"]:
        return f"### {m.group(1)} · {ESTADOS_V1['tarea'][m.group(2)]}"
    return None


def _anotar_libre(linea: str, informe: Informe) -> None:
    if (linea.startswith("## ") or linea.startswith("### ")) and re.search(r"[^\W\d_]", linea):
        informe.titulos_libres[linea] += 1


def _migrar_cuerpo(cuerpo: str, tipo: str, informe: Informe) -> str:
    """Cambia solo las líneas de título conocidas y, dentro de un bloque "### Revisión N" (hasta el siguiente ##/###),
    las líneas que son exactamente una etiqueta de ETIQUETAS_REVISION. Todo lo demás queda byte por byte."""
    salida, en_revision = [], False
    for linea in cuerpo.splitlines(keepends=True):
        texto = linea.rstrip("\r\n")
        fin = linea[len(texto):]
        if texto.startswith("## ") or texto.startswith("### "):
            en_revision = tipo == "tarea" and bool(INICIO_REVISION.match(texto))
        nuevo = _titulo(texto, tipo)
        if nuevo is None and en_revision and texto in ETIQUETAS_REVISION:
            nuevo = ETIQUETAS_REVISION[texto]
        if nuevo is None:
            _anotar_libre(texto, informe)
        salida.append((nuevo + fin) if nuevo is not None else linea)
    return "".join(salida)


def _migrar_registro(ruta: Path, tipo: str, informe: Informe) -> None:
    texto = ruta.read_bytes().decode("utf-8")
    m = FRONTMATTER.match(texto)
    if m:
        texto = ("---" + texto[3:m.start(1)] + _migrar_frontmatter(m.group(1), tipo, informe) + texto[m.end(1):m.end()]
                 + _migrar_cuerpo(texto[m.end():], tipo, informe))
    else:
        texto = _migrar_cuerpo(texto, tipo, informe)
    _escribir_atomico(ruta, texto)
    informe.registros[CARPETAS_V1[ruta.parent.name] if ruta.parent.name in CARPETAS_V1 else ruta.parent.name] += 1


def _migrar_sesion(ruta: Path, informe: Informe) -> None:
    texto = ruta.read_bytes().decode("utf-8")
    salida = []
    for linea in texto.splitlines(keepends=True):
        contenido = linea.rstrip("\r\n")
        if TITULO_SESIONES.match(contenido):
            linea = TITULO_SESIONES.sub(r"# Sessions \1", contenido) + linea[len(contenido):]
        else:
            _anotar_libre(contenido, informe)
        salida.append(linea)
    _escribir_atomico(ruta, "".join(salida))
    informe.registros["sessions"] += 1


def _mover_carpetas(mem: Path, informe: Informe) -> None:
    for viejo, nuevo in CARPETAS_V1.items():
        if not (mem / viejo).exists():
            continue
        if (mem / nuevo).exists():
            raise RuntimeError(f"{viejo}/ y {nuevo}/ both exist")
        n = sum(1 for p in (mem / viejo).rglob("*") if p.is_file())
        if _versionado(mem, viejo):
            _git(mem, "mv", viejo, nuevo)
        else:                       # carpeta vacía o sin versionar: git no la conoce
            (mem / viejo).rename(mem / nuevo)
        informe.carpetas.append(f"{viejo}/ → {nuevo}/ ({n} files)")


def _migrar_1_a_2(mem: Path) -> list[str]:
    informe = Informe()
    _mover_carpetas(mem, informe)
    for viejo, nuevo in CARPETAS_V1.items():
        carpeta = mem / nuevo
        if not carpeta.is_dir():
            continue
        for p in sorted(carpeta.glob("*.md")):
            if viejo == "sesiones":
                _migrar_sesion(p, informe)
            elif re.match(rf"{PREFIJOS[viejo]}-\d+", p.name):
                _migrar_registro(p, TIPO_DE_CARPETA_V1[viejo], informe)
            else:
                informe.otros_archivos.append(f"{nuevo}/{p.name}")
    _regenerar_vistas_en(mem)
    for vista in VISTAS_V1:
        if _versionado(mem, vista):
            _git(mem, "rm", "-q", "--", vista)
        (mem / vista).unlink(missing_ok=True)
    return informe.lineas()
