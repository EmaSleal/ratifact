#!/usr/bin/env bash
# PreToolUse(Write): si el archivo NO existe, pide confirmación; si existe, no interviene
# (la regla "Edit" de settings.json ya lo permite).
python3 -c '
import json, os, sys
d = json.load(sys.stdin)
ruta = (d.get("tool_input") or {}).get("file_path", "")
if ruta and not os.path.exists(ruta):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": f"Archivo nuevo: {ruta}"}}))
'
exit 0
