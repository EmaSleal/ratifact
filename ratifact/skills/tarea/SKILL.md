---
name: tarea
description: Deprecated alias of run-task (removed in 1.1). Runs a code task recorded in ratifact (e.g. /tarea T-001, or $tarea T-001 in Codex). Use it only when the user asks to run a T-NNN task.
argument-hint: T-NNN
---

`/tarea` was renamed to **`/run-task`** (`$run-task` in Codex); this alias is removed in 1.1.

Run task **$ARGUMENTS** (if you see the literal text `$ARGUMENTS`, use the `T-NNN` from the user's message) by following the run-task instructions exactly. They are in the `run-task/SKILL.md` file next to this alias's folder (`../run-task/SKILL.md`, inside the installed ratifact package); `ratifact install --apply` also links them at `~/.claude/commands/run-task.md` (Claude Code), `~/.pi/agent/prompts/run-task.md` (Pi) and `~/.codex/skills/run-task/SKILL.md` (Codex). Their first step reads the task with `read_task("<project>", "$ARGUMENTS")`.

If you cannot find them, stop and ask the user to run `ratifact install --apply` (it relinks `/run-task`).
