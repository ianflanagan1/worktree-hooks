"""Refuses a `git worktree remove` that would lose work: commits on no branch, which git doesn't
check for, or, when forced, uncommitted changes.

Claude Code runs it before each Bash command, with the call as JSON on stdin. Exit 2 blocks the
command and tells Claude why; anything else lets it run. A path that isn't a worktree is left
for git to refuse. It's the same check `worktree-env rm` makes.

Usage: python3 -I guard_worktree_remove.py
"""

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import final

SEPARATORS = {";", "&&", "||", "|", "&", "(", ")"}
# git's options before the subcommand that take a value as the next word.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


@final
@dataclass(frozen=True)
class Removal:
    directory: str | None
    """The directory git runs in, from -C, or None for the command's own."""
    path: str
    force: bool


def removals(command: str) -> list[Removal]:
    """Each `git worktree remove` in a shell command. A command that can't be parsed has none
    found, as the shell will refuse it too."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return []
    found = []
    segment: list[str] = []
    for word in [*words, ";"]:
        if word in SEPARATORS:
            if removal := _removal(segment):
                found.append(removal)
            segment = []
        else:
            segment.append(word)
    return found


def resolve(cwd: Path, removal: Removal) -> Path:
    """The worktree a removal names, from the directory the command runs in."""
    directory = cwd / os.path.expanduser(removal.directory or ".")
    return Path(os.path.normpath(directory / os.path.expanduser(removal.path)))


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = (event.get("tool_input") or {}).get("command") if isinstance(event, dict) else None
    if not isinstance(command, str):
        return 0
    cwd = Path(str(event.get("cwd", ".")))
    for removal in removals(command):
        worktree = resolve(cwd, removal)
        if reason := _would_lose(worktree, removal.force):
            print(f"Not removing {worktree}: {reason}", file=sys.stderr)
            return 2
    return 0


def _removal(words: list[str]) -> Removal | None:
    if not words or Path(words[0]).name != "git":
        return None
    directory = None
    i = 1
    while i < len(words) and words[i].startswith("-"):
        option = words[i]
        if option in GIT_OPTIONS_WITH_VALUE:
            if option == "-C" and i + 1 < len(words):
                directory = words[i + 1]
            i += 2
        else:
            i += 1
    rest = words[i:]
    if rest[:2] != ["worktree", "remove"]:
        return None
    arguments = rest[2:]
    force = any(a in ("-f", "--force") for a in arguments)
    paths = [a for a in arguments if not a.startswith("-")]
    return Removal(directory, paths[0], force) if paths else None


def _would_lose(worktree: Path, force: bool) -> str | None:
    """What removing worktree would lose, or None when nothing, or when it's no worktree."""
    if not (worktree / ".git").is_file():
        return None
    unreachable = _git(worktree, "log", "--oneline", "HEAD", "--not", "--branches", "--remotes")
    if unreachable:
        lines = "\n".join(f"  {line}" for line in unreachable.splitlines())
        return (
            "it has commits on no branch, which removing it would lose:\n"
            f"{lines}\nLand them, or put them on a branch first: git -C {worktree} branch <name>"
        )
    changes = _git(worktree, "status", "--porcelain")
    if force and changes:
        lines = "\n".join(f"  {line}" for line in changes.splitlines())
        return f"it has uncommitted changes:\n{lines}\nCommit or discard them first."
    return None


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    return result.stdout.strip() if result.returncode == 0 else ""


if __name__ == "__main__":
    raise SystemExit(main())
