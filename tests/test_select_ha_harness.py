"""Protect selection of official stable pytest-homeassistant releases."""

from __future__ import annotations

import pytest

from scripts.select_ha_harness import (
    HarnessSelection,
    SelectionError,
    exact_homeassistant_requirement,
    is_core_repository_url,
    latest_stable_release,
    select_stable_harness,
)


def _project(*releases: tuple[str, bool]) -> dict[str, object]:
    return {"releases": {version: [{"yanked": yanked}] for version, yanked in releases}}


def _official_release(requirements: list[str], *, official: bool = True) -> dict:
    return {
        "info": {
            "requires_dist": requirements,
            "project_urls": {
                "Repository": (
                    "https://github.com/home-assistant/core"
                    if official
                    else "https://example.invalid/other"
                )
            },
        }
    }


def _select(
    homeassistant_releases: tuple[tuple[str, bool], ...],
    official_releases: tuple[tuple[str, bool], ...],
    requirements: dict[str, list[str]],
) -> HarnessSelection:
    return select_stable_harness(
        _project(*homeassistant_releases),
        _project(*official_releases),
        lambda version: _official_release(requirements[version]),
    )


def test_matching_official_stable_pair_is_selected() -> None:
    selection = _select(
        (("2026.11.0", False), ("2026.11.1", False)),
        (("0.1.3", False), ("2026.11.0", False), ("2026.11.1", False)),
        {"2026.11.1": ["homeassistant==2026.11.1"]},
    )
    assert selection.selected_official == "2026.11.1"
    assert selection.selected_homeassistant == "2026.11.1"
    assert selection.latest_homeassistant == "2026.11.1"


def test_historical_pypi_project_is_not_selected() -> None:
    with pytest.raises(SelectionError, match="No official stable"):
        _select((("2026.11.0", False),), (("0.1.3", False),), {})


def test_prerelease_does_not_qualify_as_stable() -> None:
    with pytest.raises(SelectionError, match="No official stable"):
        _select(
            (("2026.11.0", False),),
            (("0.1.3", False), ("2026.11.0b6", False)),
            {},
        )


def test_latest_ha_ahead_of_official_pair_is_reported() -> None:
    selection = _select(
        (("2026.11.0", False), ("2026.11.1", False)),
        (("2026.11.0", False),),
        {"2026.11.0": ["homeassistant==2026.11.0"]},
    )
    assert selection.latest_homeassistant == "2026.11.1"
    assert selection.selected_homeassistant == "2026.11.0"


def test_yanked_newer_harness_is_ignored() -> None:
    selection = _select(
        (("2026.11.0", False),),
        (("2026.11.0", False), ("2026.11.1", True)),
        {"2026.11.0": ["homeassistant==2026.11.0"]},
    )
    assert selection.selected_official == "2026.11.0"


def test_version_mismatch_fails() -> None:
    with pytest.raises(SelectionError, match="match Home Assistant exactly"):
        _select(
            (("2026.11.0", False), ("2026.11.1", False)),
            (("2026.11.1", False),),
            {"2026.11.1": ["homeassistant==2026.11.0"]},
        )


def test_unofficial_provenance_fails() -> None:
    with pytest.raises(SelectionError, match="lacks canonical Core repository URL metadata"):
        select_stable_harness(
            _project(("2026.11.0", False)),
            _project(("2026.11.0", False)),
            lambda _: _official_release(["homeassistant==2026.11.0"], official=False),
        )


@pytest.mark.parametrize(
    "candidate",
    [
        "https://example.invalid/github.com/home-assistant/core",
        "https://github.com.evil.invalid/home-assistant/core",
        "https://github.com@evil.invalid/home-assistant/core",
        "https://evil.invalid@github.com/home-assistant/core",
        "http://github.com/home-assistant/core",
        "https://github.com/home-assistant/core/other",
        "https://github.com/home-assistant/core?redirect=1",
        "https://github.com/home-assistant/core#anchor",
        "https://github.com:443/home-assistant/core",
        "https://github.com/home-assistant/another",
        "https://github.com/home-assistant/%63ore",
        "not-a-url",
        None,
    ],
)
def test_canonical_core_url_metadata_rejects_misleading_values(
    candidate: object,
) -> None:
    assert is_core_repository_url(candidate) is False


@pytest.mark.parametrize(
    "candidate",
    [
        "https://github.com/home-assistant/core",
        "https://github.com/home-assistant/core/",
        "https://github.com/home-assistant/core.git",
    ],
)
def test_canonical_core_url_metadata_accepts_expected_source(candidate: str) -> None:
    assert is_core_repository_url(candidate) is True


def test_misleading_project_url_is_rejected_by_selector() -> None:
    metadata = _official_release(["homeassistant==2026.11.0"])
    metadata["info"]["project_urls"] = {
        "Source": "https://example.invalid/github.com/home-assistant/core"
    }
    with pytest.raises(SelectionError, match="canonical Core repository"):
        select_stable_harness(
            _project(("2026.11.0", False)),
            _project(("2026.11.0", False)),
            lambda _: metadata,
        )


def test_exact_homeassistant_requirement_is_required() -> None:
    assert exact_homeassistant_requirement(["homeassistant==2026.11.0"]) == "2026.11.0"
    for requirements in (
        ["homeassistant>=2026.11.0"],
        ["homeassistant==2026.11.*"],
        ["homeassistant==not-a-version"],
        ["homeassistant[extra]==2026.11.0"],
        ["homeassistant==2026.11.0; python_version >= '3.14'"],
        ["homeassistant==2026.11.0", "homeassistant==2026.11.1"],
    ):
        with pytest.raises(
            SelectionError, match="invalid dependency|exactly one|exact version"
        ):
            exact_homeassistant_requirement(requirements)


def test_malformed_artifact_is_rejected() -> None:
    with pytest.raises(SelectionError, match="invalid artifact"):
        latest_stable_release(
            {"releases": {"2026.11.0": [{"yanked": False}, "invalid artifact"]}},
            "Home Assistant",
        )


def test_malformed_yanked_field_is_rejected() -> None:
    with pytest.raises(SelectionError, match="invalid artifact yanked value"):
        latest_stable_release(
            {"releases": {"2026.11.0": [{"yanked": "false"}]}},
            "Home Assistant",
        )


def test_malformed_release_entry_is_rejected() -> None:
    with pytest.raises(SelectionError, match="invalid release entry"):
        latest_stable_release(
            {"releases": {"2026.11.0": {"yanked": False}}},
            "Home Assistant",
        )


def test_unavailable_stable_ha_target_fails() -> None:
    with pytest.raises(SelectionError, match="unavailable or yanked"):
        _select(
            (("2026.11.0", False),),
            (("2026.11.1", False),),
            {"2026.11.1": ["homeassistant==2026.11.1"]},
        )
