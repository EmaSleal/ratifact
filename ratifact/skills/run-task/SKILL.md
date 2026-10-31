---
name: run-task
description: Runs a code task recorded in ratifact (e.g. /run-task T-001, or $run-task T-001 in Codex). Use it only when the user asks to run a T-NNN task; do not use it for tasks without an id.
argument-hint: T-NNN
---

Run task **$ARGUMENTS** of this repository's project.
(If you see the literal text `$ARGUMENTS` above —e.g. in Codex, where this is a skill—, the task is the `T-NNN` the user wrote in their message; use it wherever `$ARGUMENTS` appears. If they gave none, ask which one.)

## 0. Identify the project
The project name in `ratifact` is in this repository's `CLAUDE.md` / `AGENTS.md` ("with project `<name>`"). If you cannot find it, call `list_projects` and pick the project whose path contains the current directory (in multi-repo projects, the path is the folder that groups them); if it is still unclear, ask me. From here on, `<project>` is that name.

## 1. Prepare
1. Read the task with the `ratifact` MCP tool → `read_task("<project>", "$ARGUMENTS")` (e.g. `read_task("<project>", "T-007")`). It returns the frontmatter, the full spec, every Amendment, the block relevant to the status in full, and an index of older Result/Review blocks (read one with `read_document` and its line range only if you need it). If the id does not exist, use `list_tasks("<project>")` to find the task.
2. Depending on its status (`status` field):
   - `todo`: first run.
   - `changes_requested`: the user reviewed an earlier run and asks for corrections. The **latest** "Review N" block is included in full: its **Findings** and **Additional criteria** add to the original criteria, which still apply. What the review approves is not redone.
   - `failed`: retry; the latest result is included in full so you know what failed.
   - Any other status: stop and tell me.

   Amendments ("### Amendment N" blocks: **Additional criteria** and **Notes**) are part of the spec: they add to the original criteria.
   If the spec has a `repo` field (multi-repo projects), **everything that follows —git, branches, commands and tests— happens inside that folder**, not at the project root.
3. Read the decisions listed in "Applicable decisions" (`read_document("<project>", "ADR-NNN")`). Only `accepted` ones are rules.
4. Check with `git status` that the working tree is clean. If there are uncommitted changes, **stop** and ask me; do not move or discard them.
5. Branch (the spec's `branch` field). Check whether it already exists with `git branch --list <branch>`:
   - **It exists** (always for `changes_requested`, often for `failed`): `git switch <branch>` and continue on it. Do not recreate it, rebase it or `--amend` earlier commits: corrections go in new commits.
   - **It does not exist:** create it **from the repository's main branch** (`main`, or `master` if there is no `main`): `git switch <main> && git switch -c <branch>`.
   - If the spec says to work on another existing branch, switch to it and do not create another.
6. Mark the task: `update_task("<project>", "$ARGUMENTS", "in_progress")`. If the response brings **integration guidance** (e.g. codegraph), follow it in steps 2–4: it is conditional, use it only if you have those tools. Never store decisions or task status outside ratifact.

## 2. Execute
- The spec defines the contract and the acceptance criteria, not the method. New decisions: propose them to the user so they are recorded in ratifact.
- Implement **only** what the spec asks for. Whatever is in "Out of scope" is not touched.
- If the spec is ambiguous or contradicts an accepted ADR, **stop and ask me** before deciding on your own.
- Follow the rules of the repository's `CLAUDE.md` / `AGENTS.md`.
- Add or adjust tests that cover every verifiable acceptance criterion.
- If the `in_progress` response brought a **"Delegation"** block, follow it: with `required` it is an instruction (you orchestrate; explore, write and verify workers do the work), with `suggested` it is a suggestion. The task's delegation policy was decided when it was planned; you do not decide whether to delegate.
- If it brought a **"Model routing"** block, follow it whenever you delegate to a sub-agent: use the model it gives for that role (explore, write, verify). Roles without a model, or a client that cannot choose the model of sub-agents, use the session's model.

## 3. Verify
Run the command in the spec's **"How to verify"** section, from the repository root, and keep the summary (pass/fail per suite). If the spec has no command, use the one in `CLAUDE.md` / `AGENTS.md`; if there is none either, ask me before considering the task verified. Go over every acceptance criterion and mark which one is met and how it was verified.

## 4. Close
- **Tests green and criteria met:** commit on the branch (`T-NNN: <title>`; for a task sent back, `T-NNN: fixes from review N`) and call
  `update_task("<project>", "$ARGUMENTS", "in_review", result=..., commit=<short sha>)`.
- **Something fails and cannot be solved within scope:** commit the progress anyway and call `update_task(..., "failed", result=...)` explaining what fails and why.
- The `result` includes: files touched, tests run with their count (pass/fail), criterion by criterion, any deviation from the spec, a line `Workers: <role>/<model>×<n>, …` with every worker you delegated to (e.g. `Workers: explore/haiku×1, write/sonnet×2, verify/sonnet×1`; add `escalated: write` if you took over the implementation after a writer failed verification twice) or `Workers: none — reason: <why>`, and a separate line `Integrations used: …` only for integrations (e.g. `codegraph (n queries)`, or `none`; no role names there). If a review (e.g. RDD) ran on the change, add one line summarizing its receipt (depth, findings, corrections). For a task sent back, also go over each additional criterion of the review.
- **`Workers:` format (ADR-041, corrects ADR-036 §4–§5):** `Workers: <role>/<model>×<n>, …[, rework: <role>×<n>, …][, escalated: <role>][ — note: <free text>]`. `<role>/<model>×<n>` counts initial briefs only; `rework: <role>×<n>` counts re-sends of that role caused by a defect detected by the verifier or by the orchestrator's diff review (ADR-042; the role must appear among the workers, n ≥ 1); everything after the separator is a note the parser ignores. The canonical separator is ` — `; ` - note:` / ` -- note:` (and `none - reason:`) are also accepted, but an ASCII hyphen anywhere else is an invalid token. **No parentheses: rework goes in `rework:`, comments go in `— note:`.** Examples:
  - `Workers: explore/haiku×1, write/sonnet×1, verify/sonnet×1, rework: write×1 — note: resumed once for the verify fix`
  - `Workers: explore/haiku×1, write/sonnet×2, verify/sonnet×1, rework: write×2, verify×1, escalated: write`
  - Rework detected in the orchestrator's diff review (no verifier involved): `Workers: write/sonnet×1, rework: write×1 — note: re-sent after my diff review found a missing test`
  - Initial briefs only, including several workers of the same role in parallel, are not rework: two parallel writers are `Workers: write/sonnet×2`, not `write/sonnet×1, rework: write×1`.
  - ASCII separators are accepted only before `note:` / `reason:`: `Workers: write/sonnet×1 - note: x` and `Workers: none - reason: trivial`; `Workers: write/sonnet×1 - resumed once` is invalid.
- **Fixing the `Workers:` line:** if the `in_review` response warns that the line is invalid (it proposes a corrected line when it can), send **only** the corrected line: `update_task("<project>", "$ARGUMENTS", "in_review", result="Workers: …")`. ratifact replaces the line in the latest result block (or appends it there) instead of creating a new block. Do not resend the whole result.
- **Do not merge into another branch** or mark the task `merged`: I decide that after reviewing.
- **Never move, restore, rewrite or delete the main branch or any branch other than the task's** (no `git branch -f`, `git reset` on other branches, `git push --force` or `git branch -D`), even if you see they changed while you worked: I may have merged them. If you notice an unexpected change, just report it in the `result`.
