"""Policy regression tests for fixed Home Assistant 2026.11 minimum lane."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha_minimum_policy import (
    MINIMUM_HOMEASSISTANT,
    MinimumPolicyError,
    plan_minimum,
    verify_frozen_minimum_inputs,
)


def _project(ha: str = "2026.11.0", official: str = "2026.11.0") -> dict:
    return {
        "dependency-groups": {
            "test": [
                f"homeassistant=={ha}",
                f"pytest-homeassistant=={official}",
                "aiointercept==0.1.12",
                "packaging==26.3",
            ]
        }
    }


def test_minimum_equal_to_current_still_tests_independent_graph() -> None:
    plan = plan_minimum(_project(), {"homeassistant": MINIMUM_HOMEASSISTANT})
    assert plan.minimum_homeassistant == "2026.11.0"
    assert plan.current_homeassistant == "2026.11.0"
    assert plan.run_minimum is True


def test_minimum_remains_pinned_when_latest_moves_forward() -> None:
    plan = plan_minimum(
        _project("2026.11.1", "2026.11.1"),
        {"homeassistant": "2026.11.0"},
    )
    assert plan.current_homeassistant == "2026.11.1"
    assert plan.run_minimum is True


@pytest.mark.parametrize(
    ("project", "hacs", "error"),
    [
        (_project(), {"homeassistant": "2026.11.1"}, "preserve HA floor"),
        (
            _project("2026.10.4", "2026.10.4"),
            {"homeassistant": "2026.11.0"},
            "older than",
        ),
        (
            _project("2026.11.1", "2026.11.0"),
            {"homeassistant": "2026.11.0"},
            "exactly match",
        ),
        (
            _project("2026.11.0b6", "2026.11.0b6"),
            {"homeassistant": "2026.11.0"},
            "exact stable",
        ),
        (
            _project("2026.11.0", "0.1.3"),
            {"homeassistant": "2026.11.0"},
            "exact stable",
        ),
    ],
)
def test_malformed_or_unsupported_floor_fails_closed(
    project: dict, hacs: dict, error: str
) -> None:
    with pytest.raises(MinimumPolicyError, match=error):
        plan_minimum(project, hacs)


def test_phacc_and_nonexact_requirements_are_rejected() -> None:
    project = _project()
    project["dependency-groups"]["test"].append(
        "pytest-homeassistant-custom-component==0.13.375"
    )
    with pytest.raises(MinimumPolicyError, match="PHACC"):
        plan_minimum(project, {"homeassistant": "2026.11.0"})

    project = _project()
    project["dependency-groups"]["test"].append("pytest>=9")
    with pytest.raises(MinimumPolicyError, match="Non-exact"):
        plan_minimum(project, {"homeassistant": "2026.11.0"})


def test_workflow_never_uses_legacy_plugin_or_mutates_sources() -> None:
    workflow = Path(".github/workflows/ha-minimum-compatibility.yml").read_text(
        encoding="utf-8"
    )
    assert "Minimum Home Assistant Compatibility" in workflow
    assert "2026.11.0" in workflow
    assert "HA_MINIMUM_COMPATIBILITY" in workflow
    assert "scripts/ha_minimum_policy.py --github-output" in workflow
    assert "--require-hashes" in workflow
    assert ".github/requirements/minimum-ha.txt" in workflow
    assert "scripts/check_coverage.py coverage.json" in workflow
    assert '"pytest-homeassistant-custom-component=="' not in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
    assert "gh pr" not in workflow
    assert "continue-on-error" not in workflow


# Use synthetic, offline files: the production hash lock is deliberately not
# rewritten during regression tests.
_FROZEN_PINS = {
    "homeassistant": "2026.11.0",
    "pytest-homeassistant": "2026.11.0",
    "pytest": "9.0.3",
    "pytest-cov": "7.1.0",
    "aiointercept": "0.1.12",
    "packaging": "26.3",
}


def _compiled_record(name: str, version: str) -> str:
    return f"{name}=={version} {chr(92)}\n    --hash=sha256:{'0' * 64}\n"


@pytest.fixture
def frozen_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    requirements = tmp_path / ".github" / "requirements"
    requirements.mkdir(parents=True)
    input_file = requirements / "minimum-ha.in"
    lock_file = requirements / "minimum-ha.txt"
    input_file.write_text(
        "".join(f"{name}=={version}\n" for name, version in _FROZEN_PINS.items()),
        encoding="utf-8",
    )
    lock_file.write_text(
        "".join(
            _compiled_record(name, version) for name, version in _FROZEN_PINS.items()
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return input_file, lock_file


def test_valid_frozen_minimum_inputs(frozen_files: tuple[Path, Path]) -> None:
    verify_frozen_minimum_inputs()


def test_rejects_duplicate_frozen_pin(frozen_files: tuple[Path, Path]) -> None:
    input_file, _ = frozen_files
    input_file.write_text(
        input_file.read_text(encoding="utf-8") + "homeassistant==2026.11.0\n",
        encoding="utf-8",
    )
    with pytest.raises(MinimumPolicyError, match="Duplicate fixed minimum input"):
        verify_frozen_minimum_inputs()


def test_rejects_non_exact_frozen_pin(frozen_files: tuple[Path, Path]) -> None:
    input_file, _ = frozen_files
    input_file.write_text(
        input_file.read_text(encoding="utf-8").replace(
            "pytest==9.0.3", "pytest>=9.0.3"
        ),
        encoding="utf-8",
    )
    with pytest.raises(MinimumPolicyError, match="Invalid fixed minimum input"):
        verify_frozen_minimum_inputs()


def test_rejects_drifted_frozen_pin(frozen_files: tuple[Path, Path]) -> None:
    input_file, _ = frozen_files
    input_file.write_text(
        input_file.read_text(encoding="utf-8").replace(
            "packaging==26.3", "packaging==26.4"
        ),
        encoding="utf-8",
    )
    with pytest.raises(MinimumPolicyError, match="Minimum input pins must match"):
        verify_frozen_minimum_inputs()


def test_rejects_missing_lock_record(frozen_files: tuple[Path, Path]) -> None:
    _, lock_file = frozen_files
    lock_file.write_text(
        lock_file.read_text(encoding="utf-8").replace(
            _compiled_record("pytest", "9.0.3"), ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(MinimumPolicyError, match="Missing frozen minimum lock record"):
        verify_frozen_minimum_inputs()


def test_rejects_homeassistant_suffix_false_positive(
    frozen_files: tuple[Path, Path],
) -> None:
    _, lock_file = frozen_files
    lock_file.write_text(
        lock_file.read_text(encoding="utf-8").replace(
            _compiled_record("homeassistant", "2026.11.0"), "", 1
        ),
        encoding="utf-8",
    )
    assert "pytest-homeassistant==2026.11.0" in lock_file.read_text(encoding="utf-8")
    with pytest.raises(MinimumPolicyError, match="homeassistant"):
        verify_frozen_minimum_inputs()


def test_rejects_hashless_lock(frozen_files: tuple[Path, Path]) -> None:
    _, lock_file = frozen_files
    lock_file.write_text(
        "\n".join(
            line
            for line in lock_file.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("--hash=sha256:")
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MinimumPolicyError, match="SHA-256 hash"):
        verify_frozen_minimum_inputs()


def test_rejects_hash_missing_for_single_pin(frozen_files: tuple[Path, Path]) -> None:
    _, lock_file = frozen_files
    lock_file.write_text(
        lock_file.read_text(encoding="utf-8").replace(
            _compiled_record("homeassistant", "2026.11.0"),
            f"homeassistant==2026.11.0 {chr(92)}\n",
        ),
        encoding="utf-8",
    )
    with pytest.raises(MinimumPolicyError, match="SHA-256 hash"):
        verify_frozen_minimum_inputs()


@pytest.mark.parametrize("valid", [True, False])
def test_exported_python_marker_is_exact(frozen_files, valid):
    _, lock_file = frozen_files
    marker = " ; python_full_version >= '3.14.2' and python_full_version < '3.15'"
    if not valid:
        marker = " ; python_full_version >= '3.15'"
    lock_file.write_text(
        lock_file.read_text().replace(
            "homeassistant==2026.11.0 ", "homeassistant==2026.11.0" + marker + " "
        )
    )
    if valid:
        verify_frozen_minimum_inputs()
    else:
        with pytest.raises(MinimumPolicyError, match="Missing frozen minimum lock"):
            verify_frozen_minimum_inputs()
