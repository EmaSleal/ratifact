---
name: tarea
description: Deprecated alias of run-task (removed in 1.1). Runs a code task recorded in ratifact (e.g. /tarea T-001, or $tarea T-001 in Codex). Use it only when the user asks to run a T-NNN task.
argument-hint: T-NNN
---

`/tarea` was renamed to **`/run-task`** (`$run-task` in Codex); this alias is removed in 1.1.

Run task **$ARGUMENTS** (if you see the literal text `$ARGUMENTS`, use the `T-NNN` from the user's message) by following the run-task instructions exactly. They are in the `run-task/SKILL.md` file next to this alias's folder (`../run-task/SKILL.md`, inside the installed ratifact package); `ratifact install --apply` also links them at `~/.claude/commands/run-task.md` (Claude Code), `~/.pi/agent/prompts/run-task.md` (Pi) and `~/.codex/skills/run-task/SKILL.md` (Codex). Their first step reads the task with `read_task("<project>", "$ARGUMENTS")`. Like them, the result must carry a `Workers:` line (`Workers: <role>/<model>×<n>, …` or `Workers: none — reason: <why>`), separate from `Integrations used:`. The format also accepts `rework: <role>×<n>`, `escalated: <role>` and `— note: <text>` (no parentheses); the run-task instructions give the details and examples, and a wrong line is fixed by sending only the corrected line with `update_task(…, "in_review")`.

If you cannot find them, stop and ask the user to run `ratifact install --apply` (it relinks `/run-task`).
