"""Detection of temporary-directory paths inside free text (used by the update_task warning)."""
from __future__ import annotations

import re

PREFIJOS_TEMPORALES = ("/tmp/", "/var/tmp/", "/private/tmp/")
_TOKEN = re.compile(r"[^\s\"'`<>]+")


def _es_temporal(ruta: str) -> bool:
    if ruta.startswith(PREFIJOS_TEMPORALES):
        return True
    return "/" in ruta and "scratchpad" in ruta.split("/")


def primera_ruta_temporal(texto: str) -> str:
    """First temporary path in `texto` (a /tmp-like prefix or a `scratchpad` segment), or "" if none.

    Surrounding punctuation is stripped; a bare word such as "scratchpad" or "tmp" is not a path."""
    for token in _TOKEN.findall(texto):
        ruta = token.strip("([{,;:").rstrip(".,;:!?)]}")
        if _es_temporal(ruta):
            return ruta
    return ""
