"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def wiki_home(tmp_path: Path) -> Path:
    """A throwaway wiki-home directory for a single test."""
    home = tmp_path / "wiki"
    home.mkdir()
    return home
