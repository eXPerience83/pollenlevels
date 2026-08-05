"""Project metadata consistency tests."""

from __future__ import annotations

import json
import os
import re
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT / "pyproject.toml"
MANIFEST_PATH = ROOT / "custom_components" / "pollenlevels" / "manifest.json"
README_PATH = ROOT / "README.md"
FAQ_PATH = ROOT / "FAQ.md"
TERMS_PATH = ROOT / "TERMS.md"
PRIVACY_PATH = ROOT / "PRIVACY.md"
PYTHON_VERSION_PATH = ROOT / ".python-version"
LOCK_PATH = ROOT / "uv.lock"
RENOVATE_PATH = ROOT / "renovate.json"
WORKFLOWS_PATH = ROOT / ".github" / "workflows"


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


def _exact_group_requirements(group: str) -> dict[str, Requirement]:
    """Return exact PEP 735 requirements keyed by normalized package name."""
    groups = _load_pyproject().get("dependency-groups", {})
    requirements = groups.get(group)
    assert isinstance(requirements, list), f"{group} dependency group is missing"
    parsed = [
        Requirement(requirement)
        for requirement in requirements
        if isinstance(requirement, str)
    ]
    return {requirement.name.lower(): requirement for requirement in parsed}


def _locked_version(package: str) -> str:
    """Read one exact package version from the committed uv lock."""
    lock = _read_text(LOCK_PATH)
    match = re.search(
        rf'\[\[package\]\]\nname = "{re.escape(package)}"\nversion = "([^"]+)"',
        lock,
    )
    assert match, f"{package} is missing from uv.lock"
    return match.group(1)


def test_exact_python_source_and_python_policy_are_retained() -> None:
    """Keep routine tooling validation on one approved Python 3.14 patch."""
    assert PYTHON_VERSION_PATH.read_text(encoding="utf-8") == "3.14.6\n"
    assert _load_pyproject()["project"]["requires-python"] == ">=3.14"
    assert _load_pyproject()["tool"]["ruff"]["target-version"] == "py314"


def test_exact_uv_and_dependency_groups_are_declared() -> None:
    """Keep modern validation dependencies exact and source-of-truth driven."""
    project = _load_pyproject()
    assert project["tool"]["uv"]["required-version"] == "==0.12.1"
    assert "required-version" not in project["tool"]["ruff"]
    assert project["tool"]["uv"]["default-groups"] == []
    assert project["tool"]["uv"]["environments"] == [
        "python_full_version >= '3.14.2' and python_full_version < '3.15'"
    ]

    lint = _exact_group_requirements("lint")
    test = _exact_group_requirements("test")
    assert str(lint["ruff"].specifier) == "==0.16.1"
    assert {
        name: str(test[name].specifier)
        for name in (
            "pytest",
            "pytest-asyncio",
            "aiointercept",
            "packaging",
            "pytest-homeassistant-custom-component",
            "homeassistant",
        )
    } == {
        "pytest": "==9.0.3",
        "pytest-asyncio": "==1.4.0",
        "aiointercept": "==0.1.9",
        "packaging": "==26.2",
        "pytest-homeassistant-custom-component": "==0.13.351",
        "homeassistant": "==2026.8.0b3",
    }
    release = project["dependency-groups"]["release"]
    assert release == [{"include-group": "lint"}, {"include-group": "test"}]


def test_harness_metadata_direct_pins_installed_packages_and_lock_agree() -> None:
    """Require direct compatibility pins to match the selected HA harness."""
    test = _exact_group_requirements("test")
    harness_name = "pytest-homeassistant-custom-component"
    harness = metadata.distribution(harness_name)
    if os.environ.get("HA_COMPATIBILITY_CANARY") == "1":
        # The advisory canary deliberately installs the newest harness instead
        # of the committed locked environment. Its resolver result is reported
        # by the workflow, while the direct declarations and lock remain static.
        return
    assert harness.version == "0.13.351"
    harness_requirements = {
        requirement.name.lower(): requirement
        for requirement_text in harness.requires or []
        if (requirement := Requirement(requirement_text)).name.lower()
        in {"homeassistant", "pytest", "pytest-asyncio"}
    }
    for name in ("homeassistant", "pytest", "pytest-asyncio"):
        assert str(harness_requirements[name].specifier) == str(test[name].specifier)
        assert metadata.version(name) == _locked_version(name)
    for name in (harness_name, "aiointercept", "packaging"):
        assert metadata.version(name) == _locked_version(name)

    lock = _read_text(LOCK_PATH)
    assert "override-dependencies" not in _load_pyproject().get("tool", {}).get(
        "uv", {}
    )
    prereleases = {
        name: version
        for name, version in re.findall(
            r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', lock
        )
        if Version(version).is_prerelease
    }
    assert prereleases == {"homeassistant": "2026.8.0b3"}


def test_modern_workflows_use_locked_central_tooling() -> None:
    """Keep required workflows on the committed Python, uv, and lock sources."""
    lint = _read_text(WORKFLOWS_PATH / "lint.yml")
    tests = _read_text(WORKFLOWS_PATH / "tests.yml")
    package = _read_text(WORKFLOWS_PATH / "package-test.yml")
    release = _read_text(WORKFLOWS_PATH / "release.yml")
    security = _read_text(WORKFLOWS_PATH / "workflow-security.yml")

    for workflow in (lint, tests, package):
        assert "python-version-file: .python-version" in workflow
    for workflow, group in ((lint, "lint"), (tests, "test")):
        assert "version-file: pyproject.toml" in workflow
        assert "uv lock --check" in workflow
        assert f"uv sync --locked --only-group {group}" in workflow
        assert "uv run --locked --no-sync" in workflow
    assert "setup-uv" not in package
    assert "uv sync" not in package
    assert "version-file: pyproject.toml" in security
    assert "UV_VERSION" not in security
    assert "pull_request" not in release
    assert "scripts/classify_release_validation.py" in release
    assert release.index("scripts/classify_release_validation.py") < release.index(
        "git checkout --detach"
    )
    assert "python-version-file: .python-version" in release
    assert "uv sync --locked --only-group release" in release
    assert "legacy, non-lock-reproducible validation" in release
    assert not (ROOT / "requirements_test.txt").exists()


def test_workflows_do_not_duplicate_python_or_uv_executable_pins() -> None:
    """Keep exact executable versions out of individual workflow files."""
    workflow_text = "\n".join(_read_text(path) for path in WORKFLOWS_PATH.glob("*.yml"))
    assert 'python-version: "3.14"' not in workflow_text
    assert 'python-version: "3.14.6"' not in workflow_text
    assert "UV_VERSION" not in workflow_text
    assert "version: ${{ env.UV_VERSION }}" not in workflow_text
    assert 'version: "0.12.1"' not in workflow_text


def test_canary_is_advisory_fresh_resolution_with_no_mutation_actions() -> None:
    """Protect the latest-HA canary's isolated, non-blocking contract."""
    canary = _read_text(WORKFLOWS_PATH / "ha-compatibility-canary.yml")
    assert 'cron: "17 5 * * *"' in canary
    assert "workflow_dispatch:" in canary
    assert "contents: read" in canary
    assert "group: ha-compatibility-canary" in canary
    assert "cancel-in-progress: true" in canary
    assert "ref: main" in canary
    assert "python-version-file: .python-version" in canary
    assert "version-file: pyproject.toml" in canary
    assert "cache: false" in canary
    assert "enable-cache: false" in canary
    assert 'UV_NO_CACHE: "1"' in canary
    assert "$RUNNER_TEMP/ha-compatibility-canary-venv" in canary
    assert "uv lock" not in canary
    assert "uv sync" not in canary
    assert "pytest-homeassistant-custom-component" in canary
    assert "pytest-homeassistant-custom-component==" not in canary
    assert '"$AIOINTERCEPT_REQUIREMENT"' in canary
    assert '"$PACKAGING_REQUIREMENT"' in canary
    assert "homeassistant==" not in canary
    assert "pytest==" not in canary
    assert "pytest-asyncio==" not in canary
    for name in (
        "pytest-homeassistant-custom-component",
        "homeassistant",
        "pytest-asyncio",
        "aiointercept",
        "packaging",
        "Python",
        "uv",
    ):
        assert name in canary
    assert '"$CANARY_PYTHON" -m pytest -q -p no:cacheprovider' in canary
    assert 'HA_COMPATIBILITY_CANARY: "1"' in canary
    assert "continue-on-error" not in canary
    assert "upload-artifact" not in canary
    assert "action-gh-release" not in canary
    release = _read_text(WORKFLOWS_PATH / "release.yml")
    assert "ha-compatibility-canary" not in release


def test_renovate_has_one_source_for_each_managed_validation_dependency() -> None:
    """Keep direct extraction lanes visible without duplicate declarations."""
    renovate = json.loads(_read_text(RENOVATE_PATH))
    managers = renovate["customManagers"]
    uv_managers = [
        manager
        for manager in managers
        if manager.get("depNameTemplate") == "astral-sh/uv"
    ]
    assert len(uv_managers) == 1
    assert uv_managers[0]["managerFilePatterns"] == ["/^pyproject\\.toml$/"]
    assert renovate["automerge"] is False
    assert renovate["lockFileMaintenance"]["enabled"] is True
    policy = json.dumps(renovate)
    assert "minimumGroupSize" not in policy
    assert "groupSingleUpdates" not in policy
    assert "requirements_test.txt" not in policy


def test_google_maps_legal_documents_are_publicly_linked() -> None:
    """Ensure public Google Maps legal notices stay linked and attributed."""
    assert TERMS_PATH.exists()
    assert PRIVACY_PATH.exists()

    readme = _read_text(README_PATH)
    terms = _read_text(TERMS_PATH)
    privacy = _read_text(PRIVACY_PATH)

    assert "[TERMS.md](TERMS.md)" in readme
    assert "[PRIVACY.md](PRIVACY.md)" in readme
    assert "https://maps.google.com/help/terms_maps/" in terms
    assert "https://policies.google.com/privacy" in terms
    assert "https://developers.google.com/maps/documentation/pollen/policies" in terms
    assert "https://policies.google.com/privacy" in privacy
    attribution = "Google Maps — Source: Includes pollen data from Google"
    assert attribution in readme
    assert attribution in terms


def test_google_maps_retention_limits_are_documented() -> None:
    """Ensure Google Maps Pollen retention limits remain documented."""
    terms = " ".join(_read_text(TERMS_PATH).split())

    assert (
        "future Pollen API forecast values must not be retained for more than 24 hours"
    ) in terms
    assert (
        "today's forecast values must not be retained for more than "
        "365 consecutive calendar days"
    ) in terms


def test_faq_documents_privacy_and_retention_guidance() -> None:
    """Ensure FAQ keeps its privacy and retention guidance."""
    faq = " ".join(_read_text(FAQ_PATH).split())

    assert "[PRIVACY.md](PRIVACY.md)" in faq
    assert (
        "today's forecast values may be cached for up to 365 consecutive calendar days"
    ) in faq
    assert "future forecast values may be cached for no more than 24 hours" in faq
