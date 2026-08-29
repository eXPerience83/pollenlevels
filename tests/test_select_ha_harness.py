"""Tests for stable Home Assistant harness selection."""

from __future__ import annotations

import pytest

from scripts.select_ha_harness import (
    HarnessSelection,
    SelectionError,
    exact_homeassistant_requirement,
    latest_stable_release,
    select_stable_harness,
)


def _project(*releases: tuple[str, bool]) -> dict[str, object]:
    return {"releases": {version: [{"yanked": yanked}] for version, yanked in releases}}


def _phacc_release(requirements: list[str]) -> dict[str, object]:
    return {"info": {"requires_dist": requirements}}


def _select(
    homeassistant_releases: tuple[tuple[str, bool], ...],
    phacc_releases: tuple[tuple[str, bool], ...],
    requirements: dict[str, list[str]],
) -> HarnessSelection:
    return select_stable_harness(
        _project(*homeassistant_releases),
        _project(*phacc_releases),
        lambda version: _phacc_release(requirements[version]),
    )


def test_latest_phacc_targeting_latest_stable_ha_is_selected() -> None:
    """The current stable PHACC/HA pair is selected."""
    selection = _select(
        (("2026.8.2", False), ("2026.8.3", False)),
        (("0.13.356", False), ("0.13.357", False)),
        {
            "0.13.357": ["homeassistant==2026.8.3"],
        },
    )

    assert selection.selected_phacc == "0.13.357"
    assert selection.selected_homeassistant == "2026.8.3"
    assert selection.latest_homeassistant == "2026.8.3"
    assert selection.latest_phacc == "0.13.357"


@pytest.mark.parametrize("target", ["2026.9.0b1", "2026.9.0rc1", "2026.9.0.dev0"])
def test_prerelease_ha_target_is_skipped(target: str) -> None:
    """PHACC packages targeting beta, RC, and dev Home Assistant are skipped."""
    selection = _select(
        (("2026.8.3", False), (target, False)),
        (("0.13.357", False), ("0.13.359", False)),
        {
            "0.13.359": [f"homeassistant=={target}"],
            "0.13.357": ["homeassistant==2026.8.3"],
        },
    )

    assert selection.selected_phacc == "0.13.357"
    assert selection.selected_homeassistant == "2026.8.3"
    assert selection.skipped_prerelease_phacc == ("0.13.359",)


def test_latest_ha_ahead_of_selected_pair_is_preserved() -> None:
    """Selection exposes genuine upstream harness lag to the workflow."""
    selection = _select(
        (("2026.8.3", False), ("2026.9.0", False)),
        (("0.13.357", False),),
        {"0.13.357": ["homeassistant==2026.8.3"]},
    )

    assert selection.latest_homeassistant == "2026.9.0"
    assert selection.selected_homeassistant == "2026.8.3"


def test_exact_homeassistant_requirement_is_required() -> None:
    """Only one exact, unconditional Home Assistant requirement is accepted."""
    assert exact_homeassistant_requirement(["homeassistant==2026.8.3"]) == "2026.8.3"

    for requirements in (
        ["homeassistant>=2026.8.3"],
        ["homeassistant==2026.8.*"],
        ["homeassistant==not-a-version"],
        ["homeassistant[extra]==2026.8.3"],
        ["homeassistant==2026.8.3; python_version >= '3.14'"],
        ["homeassistant==2026.8.3", "homeassistant==2026.8.2"],
    ):
        with pytest.raises(
            SelectionError, match="invalid dependency|exactly one|exact version"
        ):
            exact_homeassistant_requirement(requirements)


def test_yanked_phacc_release_is_ignored() -> None:
    """A yanked newer PHACC package cannot be selected."""
    selection = _select(
        (("2026.8.3", False),),
        (("0.13.357", False), ("0.13.358", True)),
        {"0.13.357": ["homeassistant==2026.8.3"]},
    )

    assert selection.latest_phacc == "0.13.357"
    assert selection.selected_phacc == "0.13.357"


def test_mixed_valid_and_malformed_artifacts_fail() -> None:
    """One malformed artifact invalidates an otherwise usable release."""
    with pytest.raises(SelectionError, match="invalid artifact"):
        latest_stable_release(
            {"releases": {"2026.8.3": [{"yanked": False}, "invalid artifact"]}},
            "Home Assistant",
        )


def test_non_boolean_artifact_yanked_value_fails() -> None:
    """PyPI artifact yanked values must be booleans."""
    with pytest.raises(SelectionError, match="invalid artifact yanked value"):
        latest_stable_release(
            {"releases": {"2026.8.3": [{"yanked": "false"}]}},
            "Home Assistant",
        )


def test_non_list_artifacts_collection_fails() -> None:
    """PyPI release artifact collections must be lists."""
    with pytest.raises(SelectionError, match="invalid release entry"):
        latest_stable_release(
            {"releases": {"2026.8.3": {"yanked": False}}},
            "Home Assistant",
        )


@pytest.mark.parametrize("homeassistant_releases", [(), (("2026.8.3", True),)])
def test_unavailable_or_yanked_stable_ha_target_fails(
    homeassistant_releases: tuple[tuple[str, bool], ...],
) -> None:
    """PHACC cannot select a Home Assistant release without usable artifacts."""
    with pytest.raises(SelectionError, match="no stable|unavailable or yanked"):
        _select(
            homeassistant_releases,
            (("0.13.357", False),),
            {"0.13.357": ["homeassistant==2026.8.3"]},
        )


def test_missing_stable_ha_target_fails() -> None:
    """PHACC cannot select a stable HA version absent from PyPI metadata."""
    with pytest.raises(SelectionError, match="unavailable or yanked"):
        _select(
            (("2026.8.2", False),),
            (("0.13.357", False),),
            {"0.13.357": ["homeassistant==2026.8.3"]},
        )


def test_yanked_stable_ha_target_fails() -> None:
    """PHACC cannot select a yanked stable HA release when another one exists."""
    with pytest.raises(SelectionError, match="unavailable or yanked"):
        _select(
            (("2026.8.2", False), ("2026.8.3", True)),
            (("0.13.357", False),),
            {"0.13.357": ["homeassistant==2026.8.3"]},
        )


def test_no_eligible_stable_pair_fails_clearly() -> None:
    """A PHACC catalog with only prerelease HA targets fails safely."""
    with pytest.raises(SelectionError, match="no eligible stable"):
        _select(
            (("2026.8.3", False), ("2026.9.0b1", False)),
            (("0.13.359", False),),
            {"0.13.359": ["homeassistant==2026.9.0b1"]},
        )
