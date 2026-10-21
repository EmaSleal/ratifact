#!/usr/bin/env python3
"""Envoltorio deprecado de `ratifact report` (se quita en 1.1): mismo resumen del uso, mismas opciones
(--dias/--days N, --proyecto/--project P, --log RUTA). El código vive en ratifact/informe.py y
ratifact/informe_memoria.py.

Uso:  python3 analizar_uso.py [--dias N] [--proyecto game] [--log RUTA]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ratifact import informe, informe_memoria  # noqa: E402

# Reexporta los nombres de los dos módulos para quien importe `analizar_uso` (p. ej. las pruebas).
for _modulo in (informe_memoria, informe):
    globals().update({k: v for k, v in vars(_modulo).items() if not k.startswith("__")})
del _modulo

main = informe.main

if __name__ == "__main__":
    main()
