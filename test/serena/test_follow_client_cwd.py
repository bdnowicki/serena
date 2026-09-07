"""Tests for following the client's working directory (e.g. to switch between git worktrees at runtime)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from serena.agent import SerenaAgent
from serena.util.file_system import find_project_root, find_project_root_marker


class TestFindProjectRootMarker:
    """Tests for the marker-based project root detection used when following the client's working directory."""

    def test_returns_none_without_marker(self, tmp_path):
        """A directory that is neither a Serena project nor a git repository must not be treated as a project."""
        nested = tmp_path / "just" / "some" / "dir"
        nested.mkdir(parents=True)
        assert find_project_root_marker(start=nested, boundary=tmp_path) is None

    def test_finds_serena_project_from_subdirectory(self, tmp_path):
        (tmp_path / ".serena").mkdir()
        (tmp_path / ".serena" / "project.yml").touch()
        nested = tmp_path / "src" / "nested"
        nested.mkdir(parents=True)

        result = find_project_root_marker(start=nested, boundary=tmp_path)
        assert result is not None
        assert os.path.samefile(result, tmp_path)

    def test_finds_git_directory(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = find_project_root_marker(start=tmp_path, boundary=tmp_path)
        assert result is not None
        assert os.path.samefile(result, tmp_path)

    def test_finds_git_file_of_worktree(self, tmp_path):
        """In a git worktree, `.git` is a file rather than a directory; it must still be recognised."""
        (tmp_path / ".git").write_text("gitdir: /somewhere/.git/worktrees/feature\n", encoding="utf-8")
        result = find_project_root_marker(start=tmp_path, boundary=tmp_path)
        assert result is not None
        assert os.path.samefile(result, tmp_path)

    def test_find_project_root_falls_back_to_start(self, tmp_path):
        """The fallback variant returns the starting directory even when no marker is present."""
        nested = tmp_path / "no" / "marker"
        nested.mkdir(parents=True)
        assert os.path.samefile(find_project_root(start=nested, boundary=tmp_path), nested)


class _AgentStub:
    """Minimal stand-in exercising the real `follow_client_working_directory_if_changed` implementation."""

    follow_client_working_directory_if_changed = SerenaAgent.follow_client_working_directory_if_changed

    def __init__(self, follow_client_cwd: bool, active_project_root: str | None = None):
        class _Config:
            pass

        self.serena_config = _Config()
        self.serena_config.follow_client_cwd = follow_client_cwd  # type: ignore[attr-defined]
        self._last_client_cwd: str | None = None
        self._active_project_root = active_project_root
        self.activated: list[str] = []

    def get_active_project(self):
        if self._active_project_root is None:
            return None

        class _Project:
            project_root = self._active_project_root

        return _Project()

    def activate_project_from_path_or_name(self, project_root_or_name: str):
        self.activated.append(project_root_or_name)
        self._active_project_root = project_root_or_name


@pytest.fixture
def worktree(tmp_path):
    """A directory that looks like a git worktree (`.git` is a file)."""
    path = tmp_path / "worktree"
    path.mkdir()
    (path / ".git").write_text("gitdir: /main/.git/worktrees/wt\n", encoding="utf-8")
    return path


class TestFollowClientWorkingDirectory:
    def test_enabled_by_default(self):
        """The option is enabled by default, so switching worktrees works without extra configuration."""
        from serena.config.serena_config import SerenaConfig

        assert SerenaConfig().follow_client_cwd is True

    def test_can_be_disabled(self, worktree):
        agent = _AgentStub(follow_client_cwd=False)
        with patch("serena.agent.get_client_working_directory", return_value=str(worktree)) as mock_cwd:
            agent.follow_client_working_directory_if_changed()
        mock_cwd.assert_not_called()
        assert agent.activated == []

    def test_startup_directory_does_not_override_active_project(self, worktree):
        """A baseline recorded at startup must prevent the client's initial directory from switching the project."""
        other_project = worktree.parent / "explicit"
        other_project.mkdir()
        (other_project / ".git").mkdir()

        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(other_project))
        agent._last_client_cwd = str(worktree)  # baseline as recorded at startup
        with patch("serena.agent.get_client_working_directory", return_value=str(worktree)):
            agent.follow_client_working_directory_if_changed()
        assert agent.activated == []

    def test_first_observation_does_not_override_active_project(self, worktree):
        """If no baseline could be established at startup, the first observation must not switch the project."""
        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(worktree.parent))
        assert agent._last_client_cwd is None
        with patch("serena.agent.get_client_working_directory", return_value=str(worktree)):
            agent.follow_client_working_directory_if_changed()
        assert agent.activated == []
        assert agent._last_client_cwd == str(worktree)

    def test_first_observation_activates_when_no_project_is_active(self, worktree):
        """Without an active project there is nothing to protect, so the first observation activates it."""
        agent = _AgentStub(follow_client_cwd=True, active_project_root=None)
        with patch("serena.agent.get_client_working_directory", return_value=str(worktree)):
            agent.follow_client_working_directory_if_changed()
        assert len(agent.activated) == 1
        assert os.path.samefile(agent.activated[0], worktree)

    def test_activates_project_of_new_client_cwd(self, worktree):
        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(worktree.parent))
        agent._last_client_cwd = str(worktree.parent)  # baseline established at startup
        with patch("serena.agent.get_client_working_directory", return_value=str(worktree)):
            agent.follow_client_working_directory_if_changed()
        assert len(agent.activated) == 1
        assert os.path.samefile(agent.activated[0], worktree)

    def test_does_not_reactivate_when_unchanged(self, worktree):
        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(worktree))
        with patch("serena.agent.get_client_working_directory", return_value=str(worktree)):
            agent.follow_client_working_directory_if_changed()
            agent.follow_client_working_directory_if_changed()
        assert agent.activated == []

    def test_ignores_directory_without_project_marker(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(tmp_path))
        with patch("serena.agent.get_client_working_directory", return_value=str(plain)):
            agent.follow_client_working_directory_if_changed()
        assert agent.activated == []

    def test_ignores_unavailable_client_cwd(self, worktree):
        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(worktree.parent))
        with patch("serena.agent.get_client_working_directory", return_value=None):
            agent.follow_client_working_directory_if_changed()
        assert agent.activated == []

    def test_never_raises_on_error(self, worktree):
        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(worktree.parent))
        with patch("serena.agent.get_client_working_directory", side_effect=RuntimeError("boom")):
            agent.follow_client_working_directory_if_changed()  # must not raise
        assert agent.activated == []

    def test_switches_between_two_worktrees(self, tmp_path):
        """Switching back and forth between two worktrees activates each of them in turn."""
        roots = []
        for name in ("wt-a", "wt-b"):
            path = tmp_path / name
            path.mkdir()
            (path / ".git").write_text(f"gitdir: /main/.git/worktrees/{name}\n", encoding="utf-8")
            roots.append(path)

        agent = _AgentStub(follow_client_cwd=True, active_project_root=str(roots[0]))
        agent._last_client_cwd = str(roots[0])  # baseline established at startup
        for target in (roots[1], roots[0], roots[1]):
            with patch("serena.agent.get_client_working_directory", return_value=str(target)):
                agent.follow_client_working_directory_if_changed()

        assert [Path(p).name for p in agent.activated] == ["wt-b", "wt-a", "wt-b"]
