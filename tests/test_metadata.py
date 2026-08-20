"""Project metadata consistency tests."""

from __future__ import annotations

import json
import os
import re
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = ROOT / "pyproject.toml"
MANIFEST_PATH = ROOT / "custom_components" / "pollenlevels" / "manifest.json"
HACS_PATH = ROOT / "hacs.json"
README_PATH = ROOT / "README.md"
FAQ_PATH = ROOT / "FAQ.md"
TERMS_PATH = ROOT / "TERMS.md"
PRIVACY_PATH = ROOT / "PRIVACY.md"
PYTHON_VERSION_PATH = ROOT / ".python-version"
LOCK_PATH = ROOT / "uv.lock"
RENOVATE_PATH = ROOT / "renovate.json"
WORKFLOWS_PATH = ROOT / ".github" / "workflows"
MINIMUM_HA_REQUIREMENTS_PATH = ROOT / ".github" / "requirements" / "minimum-ha.in"
MINIMUM_HA_WORKFLOW_PATH = WORKFLOWS_PATH / "ha-minimum-compatibility.yml"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as file:
        return tomllib.load(file)


def _load_manifest() -> dict:
    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_hacs() -> dict:
    with HACS_PATH.open("r", encoding="utf-8") as file:
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

    assert requires == ">=3.14", (
        "requires-python must stay aligned with the 3.14+ tooling story"
    )


def _exact_requirement_version(requirement: Requirement) -> Version:
    """Return the single non-wildcard version from an exact requirement."""
    assert requirement.url is None, f"{requirement.name} must not use a URL"
    specifiers = tuple(requirement.specifier)
    assert len(specifiers) == 1, f"{requirement.name} must have one specifier"
    specifier = specifiers[0]
    assert specifier.operator == "==", f"{requirement.name} must use =="
    assert not specifier.version.endswith(".*"), (
        f"{requirement.name} must not use a wildcard pin"
    )
    return Version(specifier.version)


def _exact_group_requirements(group: str) -> dict[str, Requirement]:
    """Return exact PEP 735 requirements keyed by normalized package name."""
    groups = _load_pyproject().get("dependency-groups", {})
    requirements = groups.get(group)
    assert isinstance(requirements, list), f"{group} dependency group is missing"
    parsed: dict[str, Requirement] = {}
    for requirement_text in requirements:
        assert isinstance(requirement_text, str), (
            f"{group} must contain only direct string requirements"
        )
        requirement = Requirement(requirement_text)
        name = canonicalize_name(requirement.name)
        assert name not in parsed, f"{group} duplicates {name}"
        _exact_requirement_version(requirement)
        parsed[name] = requirement
    return parsed


def _exact_requirements_file(path: Path) -> dict[str, Requirement]:
    """Return exact requirements from a line-oriented input file."""
    parsed: dict[str, Requirement] = {}
    for line in _read_text(path).splitlines():
        requirement_text = line.strip()
        if not requirement_text or requirement_text.startswith("#"):
            continue
        requirement = Requirement(requirement_text)
        name = canonicalize_name(requirement.name)
        assert name not in parsed, f"{path.name} duplicates {name}"
        _exact_requirement_version(requirement)
        parsed[name] = requirement
    return parsed


def _load_lock_packages() -> dict[str, set[Version]]:
    """Return normalized package names and versions from the committed uv lock."""
    with LOCK_PATH.open("rb") as file:
        lock = tomllib.load(file)
    packages = lock.get("package")
    assert isinstance(packages, list), "uv.lock must contain package entries"

    result: dict[str, set[Version]] = {}
    for package in packages:
        assert isinstance(package, dict), "uv.lock package entries must be tables"
        name = package.get("name")
        version = package.get("version")
        assert isinstance(name, str) and isinstance(version, str), (
            "uv.lock package entries need a name and version"
        )
        result.setdefault(canonicalize_name(name), set()).add(Version(version))
    return result


def _approved_python_version() -> Version:
    """Read and validate the one exact approved CPython patch declaration."""
    python_text = PYTHON_VERSION_PATH.read_text(encoding="utf-8")
    assert python_text.endswith("\n")
    assert python_text.count("\n") == 1
    python_value = python_text.removesuffix("\n")
    assert re.fullmatch(r"3\.14\.\d+", python_value)

    python_version = Version(python_value)
    assert python_version.release[:2] == (3, 14)
    assert not python_version.is_prerelease
    assert not python_version.is_devrelease
    assert python_version.local is None
    return python_version


def _declared_direct_versions() -> dict[str, Version]:
    """Return all exact direct validation versions from the maintained groups."""
    requirements = {
        **_exact_group_requirements("lint"),
        **_exact_group_requirements("test"),
    }
    return {
        name: _exact_requirement_version(requirement)
        for name, requirement in requirements.items()
    }


def _workflow_step(workflow: str, name: str) -> str:
    """Return one named GitHub Actions step block."""
    match = re.search(
        rf"(?ms)^(?P<indent>[ \t]*)- name: {re.escape(name)}\n"
        rf".*?(?=^(?P=indent)- |\Z)",
        workflow,
    )
    assert match, f"Workflow step {name!r} is missing"
    return match.group(0)


def _workflow_paths(directory: Path = WORKFLOWS_PATH) -> list[Path]:
    """Return every workflow definition path in deterministic order."""
    return sorted(
        {path for pattern in ("*.yml", "*.yaml") for path in directory.glob(pattern)}
    )


def test_workflow_step_keeps_nested_name_entries() -> None:
    """Ensure nested list names do not terminate the enclosing step block."""
    workflow = """\
      - name: Parent step
        with:
          entries:
            - name: nested entry
              value: retained
      - name: Sibling step
        run: echo sibling
    """

    step = _workflow_step(workflow, "Parent step")

    assert "- name: nested entry" in step
    assert "- name: Sibling step" not in step


def test_workflow_paths_cover_both_yaml_suffixes(tmp_path: Path) -> None:
    """Ensure executable-pin checks include both valid workflow suffixes."""
    yml = tmp_path / "a.yml"
    yaml = tmp_path / "b.yaml"
    ignored = tmp_path / "ignored.txt"
    for path in (yml, yaml, ignored):
        path.write_text("name: test\n", encoding="utf-8")

    assert _workflow_paths(tmp_path) == [yml, yaml]


def test_exact_python_source_and_python_policy_are_retained() -> None:
    """Keep routine tooling validation on one approved Python 3.14 patch."""
    _approved_python_version()
    assert _load_pyproject()["project"]["requires-python"] == ">=3.14"
    assert _load_pyproject()["tool"]["ruff"]["target-version"] == "py314"


def test_exact_uv_and_dependency_groups_are_declared() -> None:
    """Keep modern validation dependencies exact and source-of-truth driven."""
    project = _load_pyproject()
    uv = project["tool"]["uv"]
    required_version = uv.get("required-version")
    assert isinstance(required_version, str)
    uv_version = _exact_requirement_version(Requirement(f"uv{required_version}"))
    assert not uv_version.is_prerelease
    assert not uv_version.is_devrelease
    assert uv_version.local is None
    assert _read_text(PYPROJECT_PATH).count("required-version") == 1
    assert "required-version" not in project["tool"]["ruff"]
    assert uv["default-groups"] == []

    environments = uv.get("environments")
    assert isinstance(environments, list) and len(environments) == 1
    assert isinstance(environments[0], str)
    marker = Marker(environments[0])
    assert marker.evaluate({"python_full_version": str(_approved_python_version())})
    assert not marker.evaluate({"python_full_version": "3.15.0"})
    assert not marker.evaluate({"python_full_version": "3.13.99"})

    lint = _exact_group_requirements("lint")
    test = _exact_group_requirements("test")
    assert set(lint) == {"ruff"}
    assert set(test) == {
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "aiointercept",
        "packaging",
        "pytest-homeassistant-custom-component",
        "homeassistant",
    }
    release = project["dependency-groups"]["release"]
    assert release == [{"include-group": "lint"}, {"include-group": "test"}]


def test_direct_declarations_and_lock_agree() -> None:
    """Require the generated lock to retain every declared direct version."""
    lock_packages = _load_lock_packages()
    for name, version in _declared_direct_versions().items():
        assert lock_packages.get(name) == {version}, (
            f"{name} must have one locked version matching its direct declaration"
        )


def test_minimum_ha_input_matches_hacs_support_contract() -> None:
    """Keep the minimum compatibility input aligned with HACS metadata."""
    minimum = _exact_requirements_file(MINIMUM_HA_REQUIREMENTS_PATH)
    assert set(minimum) == {
        "pytest-homeassistant-custom-component",
        "homeassistant",
        "aiointercept",
        "packaging",
    }
    assert _exact_requirement_version(minimum["homeassistant"]) == Version(
        _load_hacs()["homeassistant"]
    )


def test_harness_metadata_direct_pins_installed_packages_and_lock_agree() -> None:
    """Require direct compatibility pins to match the selected HA harness."""
    test = _exact_group_requirements("test")
    declared_versions = _declared_direct_versions()
    lock_packages = _load_lock_packages()
    harness_name = "pytest-homeassistant-custom-component"
    assert "override-dependencies" not in _load_pyproject().get("tool", {}).get(
        "uv", {}
    )
    declared_prereleases = {
        name: version
        for name, version in declared_versions.items()
        if version.is_prerelease
    }
    locked_prereleases = {
        name: versions
        for name, versions in lock_packages.items()
        if any(version.is_prerelease for version in versions)
    }
    assert locked_prereleases == {
        name: {version} for name, version in declared_prereleases.items()
    }

    if os.environ.get("HA_COMPATIBILITY_CANARY") == "1":
        # The advisory canary deliberately installs the newest harness instead
        # of the committed locked environment, so only installed-version
        # comparisons are skipped while static policy checks still run.
        return
    if os.environ.get("HA_MINIMUM_COMPATIBILITY") == "1":
        minimum = _exact_requirements_file(MINIMUM_HA_REQUIREMENTS_PATH)
        assert set(minimum) == {
            harness_name,
            "homeassistant",
            "aiointercept",
            "packaging",
        }
        harness = metadata.distribution(harness_name)
        assert Version(harness.version) == _exact_requirement_version(
            minimum[harness_name]
        )
        harness_requirements = {
            canonicalize_name(requirement.name): requirement
            for requirement_text in harness.requires or []
            if (requirement := Requirement(requirement_text)).name.lower()
            in {"homeassistant", "pytest", "pytest-asyncio"}
        }
        for name in ("homeassistant", "pytest", "pytest-asyncio"):
            harness_version = _exact_requirement_version(harness_requirements[name])
            assert Version(metadata.version(name)) == harness_version
            if name == "homeassistant":
                assert harness_version == _exact_requirement_version(minimum[name])
        for name in (harness_name, "aiointercept", "packaging"):
            assert Version(metadata.version(name)) == _exact_requirement_version(
                minimum[name]
            )
        return
    harness = metadata.distribution(harness_name)
    assert Version(harness.version) == declared_versions[harness_name]
    harness_requirements = {
        canonicalize_name(requirement.name): requirement
        for requirement_text in harness.requires or []
        if (requirement := Requirement(requirement_text)).name.lower()
        in {"homeassistant", "pytest", "pytest-asyncio"}
    }
    for name in ("homeassistant", "pytest", "pytest-asyncio"):
        assert _exact_requirement_version(harness_requirements[name]) == (
            _exact_requirement_version(test[name])
        )
        assert Version(metadata.version(name)) == declared_versions[name]
        assert lock_packages[name] == {declared_versions[name]}
    for name in (harness_name, "aiointercept", "packaging"):
        assert Version(metadata.version(name)) == declared_versions[name]
        assert lock_packages[name] == {declared_versions[name]}


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
    workflow_text = "\n".join(_read_text(path) for path in _workflow_paths())
    python_version = str(_approved_python_version())
    required_version = _load_pyproject()["tool"]["uv"]["required-version"]
    uv_version = str(_exact_requirement_version(Requirement(f"uv{required_version}")))

    assert (
        re.search(
            rf"(?m)^\s*python-version:\s*[\"']?{re.escape(python_version)}"
            rf"(?:[\"']|\s*(?:#|$))",
            workflow_text,
        )
        is None
    )
    assert (
        re.search(
            r"(?m)^\s*python-version:\s*[\"']?3\.14(?:[\"']|\s*(?:#|$))",
            workflow_text,
        )
        is None
    )
    assert "UV_VERSION" not in workflow_text
    assert "version: ${{ env.UV_VERSION }}" not in workflow_text
    assert (
        re.search(
            rf"(?m)^\s*version:\s*[\"']?{re.escape(uv_version)}"
            rf"(?:[\"']|\s*(?:#|$))",
            workflow_text,
        )
        is None
    )


def test_canary_is_advisory_fresh_resolution_with_no_mutation_actions() -> None:
    """Protect the latest-HA canary's isolated, non-blocking contract."""
    canary = _read_text(WORKFLOWS_PATH / "ha-compatibility-canary.yml")
    assert 'cron: "17 5 * * *"' in canary
    assert "workflow_dispatch:" in canary
    assert "contents: read" in canary
    assert "group: ha-compatibility-canary" in canary
    assert "cancel-in-progress: true" in canary
    assert "ref: main" in canary
    setup_python = _workflow_step(canary, "Set up Python")
    assert "python-version-file: .python-version" in setup_python
    assert re.search(r"(?m)^\s+cache\s*:", setup_python) is None
    assert "cache-dependency-path" not in setup_python
    setup_uv = _workflow_step(canary, "Set up uv")
    assert "version-file: pyproject.toml" in setup_uv
    assert "enable-cache: false" in setup_uv
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
        "pytest",
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


def test_minimum_ha_workflow_is_blocking_and_hash_verified() -> None:
    """Protect the minimum compatibility lane's reproducible contract."""
    workflow = _read_text(MINIMUM_HA_WORKFLOW_PATH)
    assert "name: Minimum Home Assistant Compatibility" in workflow
    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "persist-credentials: false" in workflow
    assert "python-version-file: .python-version" in workflow
    assert "version-file: pyproject.toml" in workflow
    assert "$RUNNER_TEMP/ha-minimum-compatibility-venv" in workflow
    assert "uv pip sync" in workflow
    assert "--require-hashes" in workflow
    assert ".github/requirements/minimum-ha.txt" in workflow
    assert "HA_MINIMUM_COMPATIBILITY" in workflow
    assert "PYTHONDONTWRITEBYTECODE" in workflow
    assert '"$MINIMUM_PYTHON" -m pytest -q -ra -p no:cacheprovider' in workflow
    assert "continue-on-error" not in workflow
    assert "uv pip compile" not in workflow


def test_release_binds_trusted_and_default_snapshots_to_event_shas() -> None:
    """Keep Release selection independent from a default-branch race."""
    release = _read_text(WORKFLOWS_PATH / "release.yml")
    trusted_checkout = _workflow_step(release, "Check out trusted workflow definition")
    resolver = _workflow_step(release, "Resolve selected snapshot")

    assert "ref: ${{ github.workflow_sha }}" in trusted_checkout
    assert "github.event.repository.default_branch" not in trusted_checkout
    assert "EVENT_SHA: ${{ github.sha }}" in resolver
    assert '"$EVENT_SHA^{commit}"' in resolver
    assert 'selected_commit="$(git rev-parse HEAD)"' not in resolver
    assert 'if [[ "$EVENT_MODE" == "published-fallback" ]]' in resolver
    assert 'elif [[ "$EVENT_MODE" == "prepare" && -n "$RELEASE_REF" ]]' in resolver
    assert '"refs/remotes/origin/$branch_name^{commit}"' in resolver
    assert '"refs/tags/$tag_name^{commit}"' in resolver
    assert release.index("scripts/classify_release_validation.py") < release.index(
        'git checkout --detach "$RELEASE_COMMIT"'
    )


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
    harness_packages = {
        "pytest-homeassistant-custom-component",
        "homeassistant",
        "pytest",
        "pytest-asyncio",
    }
    harness_rules = [
        rule
        for rule in renovate["packageRules"]
        if harness_packages.intersection(rule.get("matchPackageNames", []))
    ]
    assert len(harness_rules) == 1
    harness_rule = harness_rules[0]
    assert harness_rule["matchManagers"] == ["pep621"]
    assert set(harness_rule["matchPackageNames"]) == harness_packages
    assert harness_rule["enabled"] is False
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


def test_readme_documents_4_0_statistics_restoration_and_runtime_cache() -> None:
    """Keep the README upgrade and runtime-cache guidance current."""
    readme = " ".join(_read_text(README_PATH).split())

    assert "fixed 24-hour runtime cache lifetime" in readme
    assert "Upgrading to 4.0.0: long-term statistics restored" in readme
    assert "same entity and statistic identity" in readme
    assert (
        "Statistics manually deleted after upgrading to 3.1.0 cannot be "
        "reconstructed automatically"
    ) in readme
    assert "Upgrading to 3.1.0: remove obsolete long-term statistics" not in readme


def test_documentation_distinguishes_runtime_cache_and_home_assistant_storage() -> None:
    """Keep runtime cache, Recorder, and derived statistics clearly separated."""
    documents = {
        path.name: " ".join(_read_text(path).split())
        for path in (FAQ_PATH, TERMS_PATH, PRIVACY_PATH)
    }

    for name, document in documents.items():
        assert "fixed 24-hour runtime cache" in document, name
        assert "Recorder" in document, name
        assert "long-term statistics" in document, name
        assert "locally" in document and "derived" in document, name
        assert "not automatically purged by normal Recorder retention" in document, name
        assert "Developer Tools → Statistics" in document, name
        assert (
            "Excluding an entity does not remove statistics already stored" in document
        ), name

    old_blanket_guidance = (
        "Recorder retention beyond 365 days must exclude Pollen Levels entities"
    )
    assert all(old_blanket_guidance not in document for document in documents.values())
    misleading_retention_guidance = "configure Recorder and statistics retention"
    assert all(
        misleading_retention_guidance not in document for document in documents.values()
    )


def test_faq_documents_privacy_and_retention_guidance() -> None:
    """Ensure FAQ keeps its privacy and retention guidance."""
    faq = " ".join(_read_text(FAQ_PATH).split())

    assert "[PRIVACY.md](PRIVACY.md)" in faq
    assert (
        "Today's Forecast Google Maps Content may be cached for up to "
        "365 consecutive calendar days"
    ) in faq
    assert "Forecast values may be cached for no more than 24 hours" in faq
