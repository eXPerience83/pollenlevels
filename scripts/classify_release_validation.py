"""Classify selected release snapshots without reading their worktrees."""

from __future__ import annotations

import argparse
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

LAST_LEGACY_MAIN_SHA = "0e65e38e2830c0485cdc6b3a00c95ad7e65d7427"
MODERN_PATHS = (".python-version", "uv.lock", "pyproject.toml")
LEGACY_PATHS = (
    ".github/workflows/release.yml",
    "pyproject.toml",
    "requirements_test.txt",
    "scripts/validate_release_zip.py",
)
PYTHON_VERSION_PATTERN = re.compile(r"^3\.14\.\d+$")
PYTHON_REQUEST_PATTERN = re.compile(
    r'^\s*python-version:\s*["\']?([^"\'\s#]+)', re.MULTILINE
)
RUFF_REQUIREMENT_PATTERN = re.compile(r'"(ruff(?:[<>=!~].*?)?)"')


class ValidationClassificationError(ValueError):
    """Raised when a selected release snapshot cannot be validated safely."""


@dataclass(frozen=True)
class ValidationMode:
    """The selected snapshot validation mode and legacy-only requirements."""

    mode: str
    python_version: str | None = None
    ruff_requirement: str | None = None


def _git(repository: Path, *args: str) -> str:
    """Run a Git command in the trusted checkout."""
    completed = subprocess.run(
        ("git", *args),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValidationClassificationError(f"git {' '.join(args)} failed: {message}")
    return completed.stdout


def _is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    """Return whether *ancestor* is an ancestor of *descendant*."""
    completed = subprocess.run(
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    message = completed.stderr.strip() or completed.stdout.strip()
    raise ValidationClassificationError(
        f"Unable to compare release ancestry: {message}"
    )


def _snapshot_file(repository: Path, commit: str, path: str) -> str | None:
    """Read one selected-snapshot file directly from its Git tree."""
    completed = subprocess.run(
        ("git", "show", f"{commit}:{path}"),
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        return None
    return completed.stdout


def _modern_markers(
    repository: Path, commit: str
) -> tuple[dict[str, bool], str | None]:
    """Return selected-snapshot modern marker completeness and Python version."""
    python_version = _snapshot_file(repository, commit, ".python-version")
    lock = _snapshot_file(repository, commit, "uv.lock")
    pyproject = _snapshot_file(repository, commit, "pyproject.toml")
    markers = {
        ".python-version": bool(
            python_version and PYTHON_VERSION_PATTERN.fullmatch(python_version.strip())
        ),
        "uv.lock": bool(lock and lock.strip()),
        "[tool.uv].required-version": False,
        "dependency-groups": False,
    }
    if pyproject is not None:
        try:
            data = tomllib.loads(pyproject)
        except tomllib.TOMLDecodeError:
            return markers, None
        tool = data.get("tool")
        uv = tool.get("uv") if isinstance(tool, dict) else None
        required_version = uv.get("required-version") if isinstance(uv, dict) else None
        markers["[tool.uv].required-version"] = bool(
            isinstance(required_version, str)
            and re.fullmatch(r"==\d+\.\d+\.\d+", required_version)
        )
        groups = data.get("dependency-groups")
        markers["dependency-groups"] = bool(
            isinstance(groups, dict)
            and all(
                isinstance(groups.get(name), list) and groups[name]
                for name in ("lint", "test", "release")
            )
        )
    return markers, python_version.strip() if markers[".python-version"] else None


def _legacy_inputs(
    repository: Path, commit: str
) -> tuple[bool, str | None, str | None]:
    """Read parseable legacy inputs from the selected Git tree only."""
    files = {path: _snapshot_file(repository, commit, path) for path in LEGACY_PATHS}
    if any(not content or not content.strip() for content in files.values()):
        return False, None, None

    release_workflow = files[".github/workflows/release.yml"]
    assert release_workflow is not None
    python_match = PYTHON_REQUEST_PATTERN.search(release_workflow)
    ruff_match = RUFF_REQUIREMENT_PATTERN.search(release_workflow)
    if python_match is None or ruff_match is None:
        return False, None, None
    python_version = python_match.group(1)
    ruff_requirement = ruff_match.group(1)
    if not re.fullmatch(r"3\.14(?:\.\d+)?", python_version):
        return False, None, None
    if not re.fullmatch(r"ruff(?:[<>=!~].+)?", ruff_requirement):
        return False, None, None
    try:
        tomllib.loads(files["pyproject.toml"] or "")
    except tomllib.TOMLDecodeError:
        return False, None, None
    return True, python_version, ruff_requirement


def classify(
    repository: Path, selected_commit: str, boundary: str = LAST_LEGACY_MAIN_SHA
) -> ValidationMode:
    """Classify a selected snapshot using the bounded legacy policy."""
    repository = repository.resolve()
    selected = _git(
        repository, "rev-parse", "--verify", f"{selected_commit}^{{commit}}"
    )
    selected = selected.strip()
    _git(repository, "rev-parse", "--verify", f"{boundary}^{{commit}}")

    markers, modern_python = _modern_markers(repository, selected)
    modern_complete = all(markers.values())
    modern_present = any(markers.values())
    legacy_complete, legacy_python, legacy_ruff = _legacy_inputs(repository, selected)

    if selected == boundary or _is_ancestor(repository, selected, boundary):
        if not legacy_complete:
            raise ValidationClassificationError(
                "Legacy release snapshot lacks complete selected-snapshot validation inputs"
            )
        return ValidationMode("legacy", legacy_python, legacy_ruff)

    if _is_ancestor(repository, boundary, selected):
        if not modern_complete:
            raise ValidationClassificationError(
                "Modern release snapshot has incomplete tooling: "
                + ", ".join(name for name, present in markers.items() if not present)
            )
        return ValidationMode("modern", python_version=modern_python)

    if modern_complete and legacy_complete:
        raise ValidationClassificationError(
            "Divergent release snapshot has ambiguous modern and legacy tooling"
        )
    if modern_complete:
        return ValidationMode("modern", python_version=modern_python)
    if not modern_present and legacy_complete:
        return ValidationMode("legacy", legacy_python, legacy_ruff)
    raise ValidationClassificationError(
        "Divergent release snapshot has partial, mixed, or incomplete validation tooling"
    )


def main() -> None:
    """Write Release workflow outputs for the selected snapshot classification."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--boundary", default=LAST_LEGACY_MAIN_SHA)
    parser.add_argument("--github-output", type=Path, required=True)
    arguments = parser.parse_args()
    result = classify(arguments.repository, arguments.commit, arguments.boundary)
    with arguments.github_output.open("a", encoding="utf-8") as output:
        output.write(f"validation_mode={result.mode}\n")
        output.write(f"python_version={result.python_version or ''}\n")
        output.write(f"ruff_requirement={result.ruff_requirement or ''}\n")


if __name__ == "__main__":
    try:
        main()
    except ValidationClassificationError as error:
        raise SystemExit(str(error)) from error
