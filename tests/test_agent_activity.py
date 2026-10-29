"""Behaviour of recording whether a Claude Code session is busy in a worktree."""

import json
import subprocess
import sys
from pathlib import Path

import agent_activity
import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "agent_activity.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    return repo


def hook(state: str, event: dict, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), state],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
    )


def sessions(git_dir: Path) -> dict[str, dict]:
    directory = git_dir / "claude-sessions"
    return {f.stem: json.loads(f.read_text()) for f in sorted(directory.glob("*.json"))}


# --- What is recorded


def test_a_busy_or_idle_session_is_recorded_with_claudes_pid():
    assert agent_activity.record("busy", 123) == {"pid": 123, "state": "busy"}
    assert agent_activity.record("idle", 123) == {"pid": 123, "state": "idle"}


def test_a_session_id_names_its_file_only_when_it_is_safe_as_a_file_name():
    assert agent_activity.file_name("c645eb2c-332b-4405") == "c645eb2c-332b-4405.json"
    assert agent_activity.file_name("../escape") is None
    assert agent_activity.file_name("") is None


# --- The hook, run as Claude Code runs it


def test_each_event_records_the_sessions_state_in_the_worktrees_git_directory(repo):
    event = {"session_id": "s1", "cwd": str(repo)}
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PID": "4242"}
    hook("idle", event, env)
    assert sessions(repo / ".git") == {"s1": {"pid": 4242, "state": "idle"}}
    hook("busy", event, env)
    assert sessions(repo / ".git") == {"s1": {"pid": 4242, "state": "busy"}}


def test_the_session_ending_removes_its_record(repo):
    event = {"session_id": "s1", "cwd": str(repo)}
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PID": "4242"}
    hook("busy", event, env)
    hook("end", event, env)
    assert sessions(repo / ".git") == {}


def test_a_linked_worktree_records_in_its_own_git_directory(repo, tmp_path):
    subprocess.run(["git", "-C", str(repo), "commit", "--quiet", "--allow-empty", "--message", "i"],
                   check=True, env={"PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t",
                   "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
                   "GIT_COMMITTER_EMAIL": "t@e", "HOME": str(tmp_path)})  # fmt: skip
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--quiet", "--detach", str(wt)], check=True
    )
    hook("busy", {"session_id": "s1", "cwd": str(wt)}, {"PATH": "/usr/bin:/bin"})
    assert list(sessions(repo / ".git" / "worktrees" / "wt")) == ["s1"]
    assert sessions(repo / ".git") == {}


def test_outside_a_repository_nothing_is_recorded_and_the_session_goes_on(tmp_path):
    result = hook("busy", {"session_id": "s1", "cwd": str(tmp_path)}, {"PATH": "/usr/bin:/bin"})
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_input_that_is_not_an_event_is_ignored(repo):
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "busy"], input="not json", capture_output=True,
        text=True,
    )  # fmt: skip
    assert result.returncode == 0
