"""Home resolution must find the MAIN repo's wiki from inside a linked worktree."""

from __future__ import annotations

from pathlib import Path

from wikiforge.paths import git_main_root, resolve_capture_home


def test_git_main_root_returns_parent_of_common_dir(tmp_path: Path) -> None:
    main = tmp_path / "repo"
    (main / ".git").mkdir(parents=True)

    def runner(argv: list[str]) -> str:
        assert argv == ["git", "rev-parse", "--git-common-dir"]
        return f"{main / '.git'}\n"

    assert git_main_root(runner) == main


def test_git_main_root_none_outside_git(tmp_path: Path) -> None:
    def runner(argv: list[str]) -> str:
        raise RuntimeError("not a git repository")

    assert git_main_root(runner) is None


def test_resolve_capture_home_prefers_main_repo_wiki(tmp_path: Path, monkeypatch) -> None:
    main = tmp_path / "repo"
    (main / ".git").mkdir(parents=True)
    (main / ".wikiforge").mkdir()
    worktree = tmp_path / "repo" / ".claude" / "worktrees" / "agent-1"
    worktree.mkdir(parents=True)
    monkeypatch.chdir(worktree)

    import wikiforge.paths as paths

    monkeypatch.setattr(paths, "git_main_root", lambda runner=None: main)
    # From inside the worktree, capture must still target the MAIN repo's wiki.
    assert resolve_capture_home() == main / ".wikiforge"


def test_resolve_capture_home_falls_back_to_cwd_outside_git(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "plain"
    (project / ".wikiforge").mkdir(parents=True)
    monkeypatch.chdir(project)

    import wikiforge.paths as paths

    monkeypatch.setattr(paths, "git_main_root", lambda runner=None: None)
    assert resolve_capture_home() == project / ".wikiforge"
