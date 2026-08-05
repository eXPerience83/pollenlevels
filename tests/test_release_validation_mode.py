"""Tests for the history-bounded Release validation classifier."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.classify_release_validation import (
    ValidationClassificationError,
    classify,
)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write(repository: Path, path: str, content: str) -> None:
    target = repository / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(repository: Path, message: str) -> str:
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", message)
    return _git(repository, "rev-parse", "HEAD")


def _legacy_snapshot(repository: Path) -> None:
    _write(
        repository,
        ".github/workflows/release.yml",
        """name: Release
jobs:
  validate:
    steps:
      - uses: actions/setup-python@0123456789012345678901234567890123456789
        with:
          python-version: "3.14"
      - run: python -m pip install --upgrade "ruff>=0.15" "pytest>=9"
""",
    )
    _write(repository, "pyproject.toml", '[project]\nrequires-python = ">=3.14"\n')
    _write(repository, "requirements_test.txt", "pytest>=9\n")
    _write(repository, "scripts/validate_release_zip.py", "print('validate')\n")


def _modern_snapshot(repository: Path, *, keep_legacy_inputs: bool = False) -> None:
    _write(repository, ".python-version", "3.14.6\n")
    _write(repository, "uv.lock", "version = 1\n")
    _write(
        repository,
        "pyproject.toml",
        """[project]
requires-python = ">=3.14"

[dependency-groups]
lint = ["ruff==0.16.1"]
test = ["pytest==9.0.3"]
release = [{ include-group = "lint" }, { include-group = "test" }]

[tool.uv]
required-version = "==0.12.1"
""",
    )
    if not keep_legacy_inputs:
        (repository / "requirements_test.txt").unlink(missing_ok=True)


@pytest.fixture
def release_history(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a boundary commit with complete historical validation inputs."""
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.email", "tests@example.invalid")
    _git(repository, "config", "user.name", "Release tests")
    _legacy_snapshot(repository)
    ancestor = _commit(repository, "legacy ancestor")
    _write(repository, "legacy-note.txt", "boundary\n")
    boundary = _commit(repository, "legacy boundary")
    return repository, ancestor, boundary


def test_equal_and_ancestor_boundary_snapshots_are_legacy_eligible(
    release_history: tuple[Path, str, str],
) -> None:
    """Historical snapshots use only their selected legacy inputs."""
    repository, ancestor, boundary = release_history

    for selected in (ancestor, boundary):
        result = classify(repository, selected, boundary)
        assert result.mode == "legacy"
        assert result.python_version == "3.14"
        assert result.ruff_requirement == "ruff>=0.15"


def test_descendant_with_complete_modern_tooling_is_modern(
    release_history: tuple[Path, str, str],
) -> None:
    """A boundary descendant must use locked modern validation."""
    repository, _, boundary = release_history
    _modern_snapshot(repository)
    selected = _commit(repository, "adopt modern validation")

    assert classify(repository, selected, boundary).mode == "modern"


def test_descendant_deleting_modern_tooling_fails_instead_of_downgrading(
    release_history: tuple[Path, str, str],
) -> None:
    """A modern descendant cannot become legacy by deleting a marker."""
    repository, _, boundary = release_history
    _modern_snapshot(repository)
    _commit(repository, "adopt modern validation")
    (repository / ".python-version").unlink()
    selected = _commit(repository, "delete modern Python marker")

    with pytest.raises(ValidationClassificationError, match="Modern release snapshot"):
        classify(repository, selected, boundary)


def test_divergent_complete_modern_snapshot_is_modern(
    release_history: tuple[Path, str, str],
) -> None:
    """A divergent branch with all modern markers is safely modern."""
    repository, ancestor, boundary = release_history
    _git(repository, "checkout", "--quiet", "-b", "divergent-modern", ancestor)
    _modern_snapshot(repository)
    selected = _commit(repository, "divergent modern validation")

    assert classify(repository, selected, boundary).mode == "modern"


def test_divergent_complete_legacy_snapshot_is_legacy_eligible(
    release_history: tuple[Path, str, str],
) -> None:
    """A divergent pre-adoption branch can retain its own legacy inputs."""
    repository, ancestor, boundary = release_history
    _git(repository, "checkout", "--quiet", "-b", "divergent-legacy", ancestor)
    _write(repository, "legacy-note.txt", "divergent legacy\n")
    selected = _commit(repository, "divergent legacy validation")

    assert classify(repository, selected, boundary).mode == "legacy"


def test_divergent_partial_modern_snapshot_fails_closed(
    release_history: tuple[Path, str, str],
) -> None:
    """Mixed modern and legacy shapes are not safe to classify."""
    repository, ancestor, boundary = release_history
    _git(repository, "checkout", "--quiet", "-b", "divergent-partial", ancestor)
    _write(repository, ".python-version", "3.14.6\n")
    selected = _commit(repository, "partial modern markers")

    with pytest.raises(
        ValidationClassificationError, match="partial, mixed, or incomplete"
    ):
        classify(repository, selected, boundary)


def test_divergent_incomplete_legacy_snapshot_fails_closed(
    release_history: tuple[Path, str, str],
) -> None:
    """Divergent historical branches require every selected legacy input."""
    repository, ancestor, boundary = release_history
    _git(repository, "checkout", "--quiet", "-b", "divergent-incomplete", ancestor)
    (repository / "requirements_test.txt").unlink()
    selected = _commit(repository, "missing historical requirements")

    with pytest.raises(
        ValidationClassificationError, match="partial, mixed, or incomplete"
    ):
        classify(repository, selected, boundary)


def test_divergent_ambiguous_snapshot_fails_closed(
    release_history: tuple[Path, str, str],
) -> None:
    """A divergent snapshot that contains both complete shapes is rejected."""
    repository, ancestor, boundary = release_history
    _git(repository, "checkout", "--quiet", "-b", "divergent-ambiguous", ancestor)
    _modern_snapshot(repository, keep_legacy_inputs=True)
    selected = _commit(repository, "both validation shapes")

    with pytest.raises(ValidationClassificationError, match="ambiguous"):
        classify(repository, selected, boundary)


def test_classifier_reads_selected_git_tree_not_worktree(
    release_history: tuple[Path, str, str],
) -> None:
    """Selected legacy validation never borrows a changed current worktree file."""
    repository, ancestor, boundary = release_history
    _write(repository, "requirements_test.txt", "not the selected snapshot\n")

    result = classify(repository, ancestor, boundary)

    assert result.mode == "legacy"
