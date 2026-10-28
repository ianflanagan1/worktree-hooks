"""Behaviour of refusing a `git worktree remove` that would lose work."""

import json
import os
import subprocess
import sys
from pathlib import Path

import guard_worktree_remove
import pytest
from guard_worktree_remove import Removal, removals

SCRIPT = Path(__file__).parent.parent / "scripts" / "guard_worktree_remove.py"

# --- Finding the removals in a command


def test_a_plain_removal_is_found():
    assert removals("git worktree remove ../wt1") == [Removal(None, "../wt1", force=False)]


def test_a_removal_run_in_another_directory_is_found_with_that_directory():
    found = removals("git -C ~/projects/a worktree remove --force wt1")
    assert found == [Removal("~/projects/a", "wt1", force=True)]


def test_removals_among_other_commands_are_all_found():
    found = removals("cd /x && git worktree remove a; echo done || git worktree remove -f b")
    assert found == [Removal(None, "a", False), Removal(None, "b", True)]


def test_git_options_before_the_subcommand_are_skipped():
    found = removals("git -c core.x=y --no-pager worktree remove wt")
    assert found == [Removal(None, "wt", force=False)]


def test_other_worktree_commands_are_not_removals():
    assert removals("git worktree add ../wt1 && git worktree list") == []


def test_a_command_that_cannot_be_parsed_has_no_removals():
    assert removals("git worktree remove 'unterminated") == []


# --- The hook, run as Claude Code runs it


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "home").mkdir()
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }


@pytest.fixture
def repo(tmp_path: Path, env) -> Path:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"],
                   check=True, env=env)  # fmt: skip
    return repo


def worktree(repo: Path, env) -> Path:
    wt = repo.parent / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt)],
                   check=True, env=env)  # fmt: skip
    return wt


def hook(command: str, cwd: Path, env) -> subprocess.CompletedProcess[str]:
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], input=json.dumps(event), capture_output=True,
        text=True, env=env,
    )  # fmt: skip


def test_removing_a_worktree_whose_commits_are_on_a_branch_is_allowed(repo, env):
    worktree(repo, env)
    assert hook("git worktree remove ../wt", repo, env).returncode == 0


def test_removing_a_worktree_with_commits_on_no_branch_is_refused_with_them_listed(repo, env):
    wt = worktree(repo, env)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "Lost work"],
                   check=True, env=env)  # fmt: skip
    result = hook("git worktree remove ../wt", repo, env)
    assert result.returncode == 2
    assert result.stderr.startswith(
        f"Not removing {wt}: it has commits on no branch, which removing it would lose:\n"
    )
    assert "Lost work" in result.stderr


def test_forcing_the_removal_of_a_worktree_with_uncommitted_changes_is_refused(repo, env):
    wt = worktree(repo, env)
    (wt / "draft.txt").write_text("unsaved")
    result = hook(f"git -C {repo} worktree remove --force {wt}", repo.parent, env)
    assert result.returncode == 2
    assert result.stderr.startswith(f"Not removing {wt}: it has uncommitted changes:\n")


def test_a_path_that_is_not_a_worktree_is_left_for_git_to_refuse(repo, env):
    assert hook("git worktree remove ../nowhere", repo, env).returncode == 0


def test_other_commands_are_allowed_without_a_look(repo, env):
    assert hook("ls", repo, env).returncode == 0


def test_the_paths_are_resolved_from_the_commands_directory():
    assert guard_worktree_remove.resolve(Path("/a/b"), Removal("../c", "wt", False)) == Path(
        "/a/c/wt"
    )
