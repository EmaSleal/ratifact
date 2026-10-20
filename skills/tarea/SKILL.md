---
name: tarea
description: Deprecated alias of run-task (removed in 1.1). Runs a code task recorded in memoria-proyectos (e.g. /tarea T-001, or $tarea T-001 in Codex). Use it only when the user asks to run a T-NNN task.
argument-hint: T-NNN
---

`/tarea` was renamed to **`/run-task`** (`$run-task` in Codex); this alias is removed in 1.1.

Run task **$ARGUMENTS** (if you see the literal text `$ARGUMENTS`, use the `T-NNN` from the user's message) by following the run-task instructions exactly. They are in the `skills/run-task/SKILL.md` file of the memoria-proyectos (ratifact) repository, next to this alias; when linked, also at `~/.claude/commands/run-task.md` (Claude Code), `~/.pi/agent/prompts/run-task.md` (Pi) or `~/.codex/skills/run-task/SKILL.md` (Codex). Their first step reads the task with `read_task("<project>", "$ARGUMENTS")`.

If you cannot find them, stop and ask the user to relink `/run-task` (see `docs/upgrade-v1.md`, or `project_instructions`).
