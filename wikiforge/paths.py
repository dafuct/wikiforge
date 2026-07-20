"""Resolution of the wiki-home directory."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path


def resolve_home(explicit: str | Path | None = None) -> Path:
    """Return the wiki-home directory.

    Precedence: an explicit path (from ``--home``), then the ``WIKIFORGE_HOME``
    environment variable, then the default ``~/wiki``.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get("WIKIFORGE_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / "wiki"


GitRunner = Callable[[list[str]], str]


def _default_git_runner(argv: list[str]) -> str:
    """Run a git command and return stdout (raises on non-zero/timeout/missing git)."""
    import subprocess

    return subprocess.run(
        argv, capture_output=True, text=True, check=True, timeout=5
    ).stdout


def git_main_root(runner: GitRunner | None = None) -> Path | None:
    """The MAIN repository's root, or ``None`` outside git.

    ``--git-common-dir`` resolves to the main repo's ``.git`` even from inside a
    linked worktree, so a subagent running under ``isolation: worktree`` still
    finds the project's one wiki instead of forking it per worktree.
    """
    run = runner if runner is not None else _default_git_runner
    try:
        common = run(["git", "rev-parse", "--git-common-dir"]).strip()
    except Exception:
        return None
    if not common:
        return None
    return Path(common).expanduser().resolve().parent


def resolve_capture_home(explicit: str | Path | None = None) -> Path:
    """Home for capture: ``--home`` → main-repo ``.wikiforge`` → cwd ``.wikiforge`` → default.

    The main-repo lookup comes first so capture from inside a subagent worktree
    (``.claude/worktrees/<name>/``) still targets the project's single wiki.
    """
    if explicit is not None:
        return resolve_home(explicit)
    root = git_main_root()
    if root is not None:
        candidate = root / ".wikiforge"
        if candidate.exists():
            return candidate
    local = Path.cwd() / ".wikiforge"
    if local.exists():
        return local
    return resolve_home(None)
