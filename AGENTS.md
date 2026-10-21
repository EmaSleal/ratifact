## Project memory (read first)
This repository uses the `ratifact` MCP server with project `memoria-proyectos`. Before working, call
`get_context("memoria-proyectos")`. Only **accepted** decisions are rules; proposals are not implemented without the
user's confirmation. Code tasks run with `/run-task T-NNN` (in Codex: `$run-task T-NNN`).
Decisions, pending items and tasks live in `ratifact`; on a contradiction with another memory, the
accepted decision wins.
Test command (from the repository root): `uv run --with pytest --with "mcp>=1.2,<2" pytest -q`
