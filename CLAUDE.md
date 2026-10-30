# worktree-hooks

`devbox run -- task check` runs ruff and the tests; run it before finishing. `devbox run -- task lint-file -- <files>` formats and fixes the Python files given.

The scripts in `scripts/` run under `python3 -I` with only the standard library, so keep them free of dependencies. The session record's location and fields are a contract with repo-tools' `repo_list/agents.py`; they're tagged `COUPLED:claude-sessions.`, so change both together.
