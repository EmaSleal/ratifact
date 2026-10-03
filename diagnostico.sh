#!/usr/bin/env bash
# Reproduce el arranque de Claude Desktop y muestra el error real.
cd "$(dirname "$0")"
export MEMORIA_PROYECTOS_CONFIG="$PWD/projects.json"
echo "== uv: $(/usr/bin/uv --version 2>&1)"
echo "== últimas líneas del log de Claude Desktop:"
tail -n 25 ~/.config/Claude/logs/mcp-server-memoria-proyectos.log 2>/dev/null || echo "(no se encontró el log)"
echo "== arranque manual (la primera vez descarga dependencias):"
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"diag","version":"0"}}}' \
  | timeout 120 /usr/bin/uv run --script servidor.py 2>&1 | head -40
echo "== código de salida: ${PIPESTATUS[1]}"
