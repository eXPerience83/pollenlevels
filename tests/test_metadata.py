"""Project metadata consistency tests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT / "pyproject.toml"
MANIFEST_PATH = ROOT / "custom_components" / "pollenlevels" / "manifest.json"


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as file:
        return tomllib.load(file)


def _load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_pyproject_declares_name_and_version() -> None:
    """Ensure pyproject defines package metadata required for installs."""
    project = _load_pyproject().get("project")
    assert project, "[project] section missing in pyproject.toml"

    assert project.get("name"), "Project name must be defined for packaging"
    assert project.get("version"), "Project version must be defined for packaging"


def test_manifest_version_matches_pyproject() -> None:
    """Manifest version should stay aligned with the package metadata."""
    project = _load_pyproject().get("project", {})
    manifest = _load_manifest()

    assert manifest.get("version") == project.get(
        "version"
    ), "Manifest version must match pyproject version"
