# worktree-hooks

A Claude Code plugin that makes parallel worktrees safe to work in, when several sessions run side by side in worktrees of one repository.

| Hook | When | What |
|---|---|---|
| `SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd` | as a session starts, takes a prompt, finishes its turn and ends | Records whether the session is busy or idle in the git directory of the worktree it's in. [repo-fix](../../cli/repo-tools) leaves a worktree alone while a session is busy there, so it never commits, rebases or merges under Claude's feet. |
| `PreToolUse` on `Bash` | before each shell command | Refuses a `git worktree remove` that would lose work: commits on no branch, which git doesn't check for, or, with `--force`, uncommitted changes. It's the check `worktree-env rm` makes, for a removal that skips it. |

Claude Code's own `ExitWorktree` already refuses to remove a worktree with uncommitted files or unmerged commits, so it needs no hook.

## What's recorded

One file per session, `<git-dir>/claude-sessions/<session id>.json`, where `<git-dir>` is the worktree's own (`.git/worktrees/<name>/` for a linked worktree):

```json
{"pid": 4242, "state": "busy"}
```

The pid is Claude Code's own, from `CLAUDE_PID`, so a reader can ignore the file of a session that crashed without ending. A reader should also ignore the session it runs in, named by `CLAUDE_CODE_SESSION_ID`: repo-fix run by Claude would otherwise leave its own worktree alone.

Two limits: a turn you interrupt may not fire `Stop`, so the session stays busy until its next turn ends; and a session that moves to another worktree mid-session leaves its record in the first until it ends. Both err on the side of leaving a worktree alone.

## Install

Point hooks in `~/.claude/settings.json` at the scripts in a clone, as `hooks/hooks.json` lists them, with `$HOME/projects/claude/worktree-hooks` for `${CLAUDE_PLUGIN_ROOT}`. Changes to the scripts then apply at once. Run `devbox install` in the clone and replace `python3` with `"$HOME/projects/claude/worktree-hooks/.devbox/nix/profile/default/bin/python3"`, so the hooks run on the devbox's Python 3.13 without `devbox run`'s startup time on every call.

Or install it as a plugin:

```
/plugin marketplace add ~/projects/claude/worktree-hooks
/plugin install worktree-hooks@worktree-hooks
```

Claude Code runs a cached copy, so after changing a hook bump `version` in `.claude-plugin/plugin.json`, then run `/plugin marketplace update worktree-hooks` and `/plugin update worktree-hooks@worktree-hooks`.

As a plugin, it needs `git` and a `python3` of 3.13 or later on `PATH`; the macOS system one is too old. The scripts use only the standard library and never stop a session: a failure records nothing.

## Development

```sh
devbox run check   # ruff, then pytest
```

## License

MIT
