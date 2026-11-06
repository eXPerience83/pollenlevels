"""Policy regression tests for fixed Home Assistant 2026.11 minimum lane."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ha_minimum_policy import (
    MINIMUM_HOMEASSISTANT,
    MinimumPolicyError,
    plan_minimum,
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


def test_minimum_equal_to_current_needs_no_duplicate_suite() -> None:
    plan = plan_minimum(_project(), {"homeassistant": MINIMUM_HOMEASSISTANT})
    assert plan.minimum_homeassistant == "2026.11.0"
    assert plan.current_homeassistant == "2026.11.0"
    assert plan.run_minimum is False


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
    assert '"pytest-homeassistant==$MINIMUM_HA"' in workflow
    assert '"homeassistant==$MINIMUM_HA"' in workflow
    assert "scripts/check_coverage.py coverage.json" in workflow
    assert '"pytest-homeassistant-custom-component=="' not in workflow
    assert "contents: write" not in workflow
    assert "git push" not in workflow
    assert "gh pr" not in workflow
    assert "continue-on-error" not in workflow
