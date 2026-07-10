"""Project metadata consistency tests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT / "pyproject.toml"
MANIFEST_PATH = ROOT / "custom_components" / "pollenlevels" / "manifest.json"
README_PATH = ROOT / "README.md"
FAQ_PATH = ROOT / "FAQ.md"
TERMS_PATH = ROOT / "TERMS.md"
PRIVACY_PATH = ROOT / "PRIVACY.md"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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

    assert manifest.get("version") == project.get("version"), (
        "Manifest version must match pyproject version"
    )


def test_pyproject_requires_python_is_314_plus() -> None:
    """Ensure pyproject enforces Python 3.14+ for tooling."""
    project = _load_pyproject().get("project", {})
    requires = project.get("requires-python")

    assert isinstance(requires, str) and requires.startswith(">=3.14"), (
        "requires-python must stay aligned with the 3.14+ tooling story"
    )


def test_google_maps_legal_documents_are_publicly_linked() -> None:
    """Ensure public Google Maps legal notices stay linked and attributed."""
    assert TERMS_PATH.exists()
    assert PRIVACY_PATH.exists()

    readme = _read_text(README_PATH)
    terms = _read_text(TERMS_PATH)
    privacy = _read_text(PRIVACY_PATH)

    assert "TERMS.md" in readme
    assert "PRIVACY.md" in readme
    assert "https://maps.google.com/help/terms_maps/" in terms
    assert "https://policies.google.com/privacy" in terms
    assert "https://developers.google.com/maps/documentation/pollen/policies" in terms
    assert "https://policies.google.com/privacy" in privacy
    assert (
        "Google Maps — Source: Includes pollen data from Google" in readme
        or "Google Maps — Source: Includes pollen data from Google" in terms
    )


def test_google_maps_retention_limits_are_documented() -> None:
    """Ensure Google Maps Pollen retention limits remain documented."""
    docs = "\n".join(
        _read_text(path) for path in (README_PATH, TERMS_PATH, PRIVACY_PATH, FAQ_PATH)
    )

    assert "24 hours" in docs
    assert "365" in docs
