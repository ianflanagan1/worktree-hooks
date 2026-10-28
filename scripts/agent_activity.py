"""Records whether a Claude Code session is busy in a worktree, for tools such as repo-fix that
must not change files under it.

Claude Code runs it on SessionStart (idle), UserPromptSubmit (busy), Stop (idle) and SessionEnd
(end), with the event as JSON on stdin. It keeps one file per session in the git directory of
the worktree the session is in, `<git-dir>/claude-sessions/<session id>.json`:

    {"pid": 4242, "state": "busy"}

The pid is Claude Code's own, from CLAUDE_PID, so a reader can tell a session that crashed
without ending. It never stops the session: any failure leaves nothing recorded.

Usage: python3 -I agent_activity.py busy|idle|end
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# COUPLED:claude-sessions. = repo-tools:src/repo_list/agents.py SESSIONS and its JSON fields
SESSIONS = "claude-sessions"
STATES = ("busy", "idle")
END = "end"


def record(state: str, pid: int) -> dict:
    """What a session's file holds."""
    return {"pid": pid, "state": state}


def file_name(session: str) -> str | None:
    """The file a session's record goes in, or None for an id unsafe as a file name."""
    return f"{session}.json" if re.fullmatch(r"[A-Za-z0-9_-]+", session) else None


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in (*STATES, END):
        print("Usage: agent_activity.py busy|idle|end", file=sys.stderr)
        return 0
    state = argv[1]
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict):
        return 0
    name = file_name(str(event.get("session_id", "")))
    git_dir = _git_dir(Path(str(event.get("cwd", "."))))
    if name is None or git_dir is None:
        return 0

    file = git_dir / SESSIONS / name
    if state == END:
        file.unlink(missing_ok=True)
        return 0
    pid = os.environ.get("CLAUDE_PID", "")
    try:
        file.parent.mkdir(exist_ok=True)
        partial = file.with_suffix(".tmp")
        partial.write_text(json.dumps(record(state, int(pid) if pid.isdigit() else os.getppid())))
        partial.replace(file)
    except OSError:
        pass
    return 0


def _git_dir(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--absolute-git-dir"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
    except OSError:
        return None
    return Path(result.stdout.strip()) if result.returncode == 0 else None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
