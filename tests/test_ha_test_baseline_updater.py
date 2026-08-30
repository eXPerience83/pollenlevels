"""Tests for the scheduled normal Home Assistant baseline updater."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.ha_test_baseline_updater import (
    BaselinePlan,
    UpdaterError,
    make_plan,
    release_mature_at,
    update_pyproject,
    validate_lock_delta,
)
from scripts.select_ha_harness import HarnessSelection

NOW = datetime(2026, 8, 30, tzinfo=UTC)


def _project(cooldown: str = "3 days") -> dict[str, object]:
    return {
        "dependency-groups": {
            "test": [
                "packaging==26.3",
                "pytest-homeassistant-custom-component==0.13.357",
                "homeassistant==2026.8.3",
            ]
        },
        "tool": {"uv": {"exclude-newer": cooldown}},
    }


def _selection(ha: str = "2026.8.3", phacc: str = "0.13.357") -> HarnessSelection:
    return HarnessSelection(
        latest_homeassistant=ha,
        latest_phacc=phacc,
        selected_homeassistant=ha,
        selected_phacc=phacc,
        skipped_prerelease_phacc=("0.13.360",),
    )


def _release(uploaded: datetime, *, yanked: bool = False) -> dict[str, object]:
    return {
        "urls": [
            {
                "yanked": yanked,
                "upload_time_iso_8601": uploaded.isoformat().replace("+00:00", "Z"),
            }
        ]
    }


def _plan(
    *,
    ha: str = "2026.8.3",
    phacc: str = "0.13.357",
    ha_uploaded: datetime = NOW - timedelta(days=4),
    phacc_uploaded: datetime = NOW - timedelta(days=4),
) -> BaselinePlan:
    return make_plan(
        _project(),
        _selection(ha, phacc),
        _release(ha_uploaded),
        _release(phacc_uploaded),
        NOW,
    )


def test_baseline_already_current_is_a_noop() -> None:
    """Equal selected versions produce current regardless of release age."""
    assert _plan().status == "current"


def test_mature_newer_stable_pair_is_an_update() -> None:
    """A newer pair becomes eligible only after both release gates mature."""
    plan = _plan(ha="2026.9.0", phacc="0.13.400")

    assert plan.status == "update"
    assert plan.mature_at == (NOW - timedelta(days=1)).isoformat()


def test_candidate_younger_than_cooldown_is_not_updated() -> None:
    """A new selected pair stays in cooldown until the common maturity instant."""
    assert _plan(ha="2026.9.0", phacc="0.13.400", ha_uploaded=NOW).status == "cooldown"


def test_ha_mature_but_phacc_young_is_cooldown() -> None:
    """PHACC's release timestamp independently protects the pair."""
    assert (
        _plan(ha="2026.9.0", phacc="0.13.400", phacc_uploaded=NOW).status == "cooldown"
    )


def test_phacc_mature_but_ha_young_is_cooldown() -> None:
    """Home Assistant's release timestamp independently protects the pair."""
    assert _plan(ha="2026.9.0", phacc="0.13.400", ha_uploaded=NOW).status == "cooldown"


def test_latest_non_yanked_artifact_controls_maturity() -> None:
    """A late usable wheel extends the whole release's maturity window."""
    metadata = {
        "urls": [
            {"yanked": False, "upload_time_iso_8601": "2026-08-20T00:00:00Z"},
            {"yanked": False, "upload_time_iso_8601": "2026-08-29T12:00:00Z"},
        ]
    }

    assert release_mature_at(metadata, "example", "1", 3) == datetime(
        2026, 9, 1, 12, tzinfo=UTC
    )


def test_yanked_artifacts_are_ignored_after_validation() -> None:
    """A yanked late artifact does not extend maturity after its shape is checked."""
    metadata = {
        "urls": [
            {"yanked": False, "upload_time_iso_8601": "2026-08-20T00:00:00Z"},
            {"yanked": True, "upload_time_iso_8601": "2026-08-29T12:00:00Z"},
        ]
    }

    assert release_mature_at(metadata, "example", "1", 3) == datetime(
        2026, 8, 23, tzinfo=UTC
    )


@pytest.mark.parametrize(
    ("metadata", "match"),
    [
        ({"urls": ["bad"]}, "malformed artifact"),
        (
            {
                "urls": [
                    {"yanked": "false", "upload_time_iso_8601": "2026-08-20T00:00:00Z"}
                ]
            },
            "boolean",
        ),
        ({"urls": [{"yanked": False}]}, "upload_time"),
        (
            {"urls": [{"yanked": False, "upload_time_iso_8601": "not-a-time"}]},
            "invalid",
        ),
        (
            {
                "urls": [
                    {"yanked": False, "upload_time_iso_8601": "2026-08-20T00:00:00"}
                ]
            },
            "timezone-aware",
        ),
        (
            {
                "urls": [
                    {"yanked": True, "upload_time_iso_8601": "2026-08-20T00:00:00Z"}
                ]
            },
            "only yanked",
        ),
    ],
)
def test_malformed_release_artifacts_fail_closed(
    metadata: dict[str, object], match: str
) -> None:
    """Every release artifact must have the strict PyPI shape used by maturity."""
    with pytest.raises(UpdaterError, match=match):
        release_mature_at(metadata, "example", "1", 3)


@pytest.mark.parametrize("cooldown", ["three days", "0 days", "3 hours", 3])
def test_malformed_cooldown_fails(cooldown: object) -> None:
    """The repository policy must not silently fall back to a duration."""
    project = _project()
    project["tool"] = {"uv": {"exclude-newer": cooldown}}
    with pytest.raises(UpdaterError, match="whole-day"):
        make_plan(project, _selection(), _release(NOW), _release(NOW), NOW)


def test_downgrade_candidate_fails() -> None:
    """The normal baseline updater never moves either direct pin backward."""
    with pytest.raises(UpdaterError, match="downgrade"):
        _plan(ha="2026.8.2")


def _update_plan(*, ha: str = "2026.9.0", phacc: str = "0.13.400") -> BaselinePlan:
    return _plan(ha=ha, phacc=phacc)


def _pyproject() -> str:
    return """# Tooling aligned to the Home Assistant 2026.5 Python floor (>=3.14.2).

[dependency-groups]
test = [
    "pytest-homeassistant-custom-component==0.13.357",
    "homeassistant==2026.8.3",
]

[tool.uv]
exclude-newer = "3 days"
# Home Assistant 2026.8.3 requires Python 3.14.2+, while CI itself uses the
# exact patch from .python-version. Keep the lock within the supported 3.14 line.
"""


def test_pyproject_updates_exact_two_pins_and_ha_comment() -> None:
    """The text update keeps unrelated configuration bytes intact."""
    updated = update_pyproject(_pyproject(), _update_plan())

    assert '"homeassistant==2026.9.0"' in updated
    assert '"pytest-homeassistant-custom-component==0.13.400"' in updated
    assert "# Home Assistant 2026.9.0 requires Python 3.14.2+" in updated
    assert "# Tooling aligned to the Home Assistant 2026.5" in updated


def test_pyproject_leaves_ha_comment_when_only_phacc_changes() -> None:
    """A same-HA harness update must not touch the nearby HA compatibility note."""
    plan = _update_plan(ha="2026.8.3", phacc="0.13.400")
    updated = update_pyproject(_pyproject(), plan)

    assert "# Home Assistant 2026.8.3 requires Python 3.14.2+" in updated


@pytest.mark.parametrize(
    "text",
    [
        _pyproject().replace('"homeassistant==2026.8.3",\n', ""),
        _pyproject().replace(
            '    "homeassistant==2026.8.3",\n',
            '    "homeassistant==2026.8.3",\n    "homeassistant==2026.8.3",\n',
        ),
    ],
)
def test_missing_or_ambiguous_pyproject_pin_fails(text: str) -> None:
    """Text replacement requires exactly one direct pin occurrence."""
    with pytest.raises(UpdaterError, match="exact homeassistant pin"):
        update_pyproject(text, _update_plan())


def _lock(
    *,
    ha: str,
    phacc: str,
    local_version: str = "4.0.0",
    source: str = 'virtual = "."',
    other: str = "1.0",
) -> str:
    return f'''version = 1
revision = 1
requires-python = ">=3.14"

[[package]]
name = "homeassistant"
version = "{ha}"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [{{ name = "dependency" }}]

[[package]]
name = "pytest-homeassistant-custom-component"
version = "{phacc}"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [{{ name = "homeassistant" }}]

[[package]]
name = "other"
version = "{other}"
source = {{ registry = "https://pypi.org/simple" }}
sdist = {{ hash = "sha256:one" }}
dependencies = [{{ name = "dependency" }}]

[[package]]
name = "pollenlevels"
version = "{local_version}"
source = {{ {source} }}

[package.dev-dependencies]
release = [{{ name = "homeassistant" }}, {{ name = "pytest-homeassistant-custom-component" }}]
test = [{{ name = "homeassistant" }}, {{ name = "pytest-homeassistant-custom-component" }}]

[package.metadata]

[package.metadata.requires-dev]
release = [
    {{ name = "homeassistant", specifier = "=={ha}" }},
    {{ name = "pytest-homeassistant-custom-component", specifier = "=={phacc}" }},
]
test = [
    {{ name = "homeassistant", specifier = "=={ha}" }},
    {{ name = "pytest-homeassistant-custom-component", specifier = "=={phacc}" }},
]
'''


def _valid_locks() -> tuple[str, str]:
    return _lock(ha="2026.8.3", phacc="0.13.357"), _lock(
        ha="2026.9.0", phacc="0.13.400"
    )


def test_allowed_ha_phacc_and_local_specifier_movement_passes() -> None:
    """The intended direct record and local requirement metadata update is accepted."""
    before, after = _valid_locks()
    validate_lock_delta(before, after, "2026.9.0", "0.13.400")


@pytest.mark.parametrize(
    ("transform", "match"),
    [
        (
            lambda text: text.replace(
                'name = "other"\nversion = "1.0"', 'name = "other"\nversion = "2.0"'
            ),
            "other",
        ),
        (
            lambda text: text.replace('hash = "sha256:one"', 'hash = "sha256:two"'),
            "other",
        ),
        (
            lambda text: text.replace(
                'name = "other"\nversion = "1.0"\nsource = { registry = "https://pypi.org/simple" }\nsdist = { hash = "sha256:one" }\ndependencies = [{ name = "dependency" }]',
                'name = "other"\nversion = "1.0"\nsource = { registry = "https://pypi.org/simple" }\nsdist = { hash = "sha256:one" }\ndependencies = [{ name = "changed" }]',
            ),
            "other",
        ),
        (
            lambda text: text.replace(
                '\n[[package]]\nname = "other"',
                '\n[[package]]\nname = "added"\nversion = "1"\nsource = { registry = "https://pypi.org/simple" }\n\n[[package]]\nname = "other"',
            ),
            "package set",
        ),
    ],
)
def test_unrelated_lock_movement_fails(transform: object, match: str) -> None:
    """No unrelated package record change is acceptable to publication."""
    before, after = _valid_locks()
    with pytest.raises(UpdaterError, match=match):
        validate_lock_delta(before, transform(after), "2026.9.0", "0.13.400")


@pytest.mark.parametrize(
    ("after", "match"),
    [
        (
            _lock(ha="2026.9.0", phacc="0.13.400", local_version="5.0.0"),
            "version or source",
        ),
        (
            _lock(ha="2026.9.0", phacc="0.13.400", source='virtual = "elsewhere"'),
            "version or source",
        ),
        (
            _lock(ha="2026.9.0", phacc="0.13.400").replace(
                'specifier = "==2026.9.0"', 'specifier = ">=2026.9.0"'
            ),
            "target specifier",
        ),
    ],
)
def test_unexpected_local_pollenlevels_movement_fails(after: str, match: str) -> None:
    """Only the two direct local dependency specifiers may change."""
    before, _ = _valid_locks()
    with pytest.raises(UpdaterError, match=match):
        validate_lock_delta(before, after, "2026.9.0", "0.13.400")


def test_wrong_resulting_harness_versions_fail() -> None:
    """Target records must lock exactly to the selected stable pair."""
    before, after = _valid_locks()
    with pytest.raises(UpdaterError, match="homeassistant"):
        validate_lock_delta(before, after, "2026.9.1", "0.13.400")
