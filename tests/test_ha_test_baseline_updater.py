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

NOW = datetime(2026, 12, 30, tzinfo=UTC)


def _project(cooldown: str = "3 days") -> dict[str, object]:
    return {
        "dependency-groups": {
            "test": [
                "pytest-homeassistant==2026.11.0",
                "homeassistant==2026.11.0",
            ]
        },
        "tool": {"uv": {"exclude-newer": cooldown}},
    }


def _selection(ha: str = "2026.11.0", official: str = "2026.11.0") -> HarnessSelection:
    return HarnessSelection(
        latest_homeassistant=ha,
        latest_official=official,
        selected_homeassistant=ha,
        selected_official=official,
        skipped_prerelease_official=("2026.11.0b1",),
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
    ha: str = "2026.11.0",
    official: str = "2026.11.0",
    ha_uploaded: datetime = NOW - timedelta(days=4),
    official_uploaded: datetime = NOW - timedelta(days=4),
) -> BaselinePlan:
    return make_plan(
        _project(),
        _selection(ha, official),
        _release(ha_uploaded),
        _release(official_uploaded),
        NOW,
    )


def test_baseline_already_current_is_a_noop() -> None:
    """Equal selected versions produce current regardless of release age."""
    assert _plan().status == "current"


def test_mature_newer_stable_pair_is_an_update() -> None:
    """A newer pair becomes eligible only after both release gates mature."""
    plan = _plan(ha="2026.12.0", official="2026.12.0")

    assert plan.status == "update"
    assert plan.mature_at == (NOW - timedelta(days=1)).isoformat()


def test_candidate_younger_than_cooldown_is_not_updated() -> None:
    """A new selected pair stays in cooldown until the common maturity instant."""
    assert (
        _plan(ha="2026.12.0", official="2026.12.0", ha_uploaded=NOW).status
        == "cooldown"
    )


def test_ha_mature_but_official_young_is_cooldown() -> None:
    """OFFICIAL's release timestamp independently protects the pair."""
    assert (
        _plan(ha="2026.12.0", official="2026.12.0", official_uploaded=NOW).status
        == "cooldown"
    )


def test_official_mature_but_ha_young_is_cooldown() -> None:
    """Home Assistant's release timestamp independently protects the pair."""
    assert (
        _plan(ha="2026.12.0", official="2026.12.0", ha_uploaded=NOW).status
        == "cooldown"
    )


def test_manual_override_only_waives_pair_release_age() -> None:
    """Manual waiver promotes a newer pair without skipping its basic safety checks."""
    plan = make_plan(
        _project(),
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
        override_cooldown=True,
    )
    assert plan.status == "update"
    assert plan.cooldown_overridden is True
    assert plan.cooldown_days == 3


def test_manual_override_does_not_republish_current_pair() -> None:
    plan = make_plan(
        _project(),
        _selection(),
        _release(NOW),
        _release(NOW),
        NOW,
        override_cooldown=True,
    )
    assert plan.status == "current"
    assert plan.cooldown_overridden is False


def test_manual_override_rejects_downgrade() -> None:
    with pytest.raises(UpdaterError, match="downgrade"):
        make_plan(
            _project(),
            _selection("2026.10.4", "2026.10.4"),
            _release(NOW),
            _release(NOW),
            NOW,
            override_cooldown=True,
        )


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
        _plan(ha="2026.10.4", official="2026.10.4")


def _update_plan(*, ha: str = "2026.12.0", official: str = "2026.12.0") -> BaselinePlan:
    return _plan(ha=ha, official=official)


def _pyproject() -> str:
    return """# Tooling aligned to the Home Assistant 2026.5 Python floor (>=3.14.2).

[dependency-groups]
test = [
    "pytest-homeassistant==2026.11.0",
    "homeassistant==2026.11.0",
]

[tool.uv]
exclude-newer = "3 days"
# Home Assistant 2026.11.0 requires Python 3.14.2+, while CI itself uses the
# exact patch from .python-version. Keep the lock within the supported 3.14 line.
"""


def test_pyproject_updates_exact_two_pins_preserving_other_comments() -> None:
    """The text update keeps unrelated configuration bytes intact."""
    updated = update_pyproject(_pyproject(), _update_plan())

    assert '"homeassistant==2026.12.0"' in updated
    assert '"pytest-homeassistant==2026.12.0"' in updated
    assert "# Home Assistant 2026.12.0 requires Python 3.14.2+" in updated
    assert "# Tooling aligned to the Home Assistant 2026.5" in updated


def test_official_only_version_change_rejected_by_minimum_policy() -> None:
    """The updater must not propose a test baseline that CI will reject."""
    with pytest.raises(UpdaterError, match="exact matching stable release"):
        _update_plan(ha="2026.11.0", official="2026.12.0")


@pytest.mark.parametrize(
    ("ha", "official"),
    [
        ("2026.12.0", "2026.12.0.post1"),
        ("2026.12.0", "2026.12.1"),
        ("2026.12.0b1", "2026.12.0b1"),
    ],
)
def test_unpromotable_selected_harness_pair_rejected(ha: str, official: str) -> None:
    with pytest.raises(UpdaterError, match="exact matching stable release"):
        _plan(ha=ha, official=official)


@pytest.mark.parametrize(
    "text",
    [
        _pyproject().replace('"homeassistant==2026.11.0",\n', ""),
        _pyproject().replace(
            '    "homeassistant==2026.11.0",\n',
            '    "homeassistant==2026.11.0",\n    "homeassistant==2026.11.0",\n',
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
    official: str,
    local_version: str = "4.0.0",
    source: str = 'virtual = "."',
    other: str = "1.0",
) -> str:
    return f"""version = 1
revision = 1
requires-python = ">=3.14"

[[package]]
name = "homeassistant"
version = "{ha}"
source = {{ registry = "https://pypi.org/simple" }}
dependencies = [{{ name = "dependency" }}]

[[package]]
name = "pytest-homeassistant"
version = "{official}"
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
release = [{{ name = "homeassistant" }}, {{ name = "pytest-homeassistant" }}]
test = [{{ name = "homeassistant" }}, {{ name = "pytest-homeassistant" }}]

[package.metadata]

[package.metadata.requires-dev]
release = [
    {{ name = "homeassistant", specifier = "=={ha}" }},
    {{ name = "pytest-homeassistant", specifier = "=={official}" }},
]
test = [
    {{ name = "homeassistant", specifier = "=={ha}" }},
    {{ name = "pytest-homeassistant", specifier = "=={official}" }},
]
"""


def _valid_locks() -> tuple[str, str]:
    return _lock(ha="2026.11.0", official="2026.11.0"), _lock(
        ha="2026.12.0", official="2026.12.0"
    )


def test_allowed_ha_official_and_local_specifier_movement_passes() -> None:
    """The intended direct record and local requirement metadata update is accepted."""
    before, after = _valid_locks()
    validate_lock_delta(before, after, "2026.12.0", "2026.12.0")


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
        validate_lock_delta(before, transform(after), "2026.12.0", "2026.12.0")


@pytest.mark.parametrize(
    ("after", "match"),
    [
        (
            _lock(ha="2026.12.0", official="2026.12.0", local_version="5.0.0"),
            "version or source",
        ),
        (
            _lock(ha="2026.12.0", official="2026.12.0", source='virtual = "elsewhere"'),
            "version or source",
        ),
        (
            _lock(ha="2026.12.0", official="2026.12.0").replace(
                'specifier = "==2026.12.0"', 'specifier = ">=2026.12.0"'
            ),
            "target specifier",
        ),
    ],
)
def test_unexpected_local_pollenlevels_movement_fails(after: str, match: str) -> None:
    """Only the two direct local dependency specifiers may change."""
    before, _ = _valid_locks()
    with pytest.raises(UpdaterError, match=match):
        validate_lock_delta(before, after, "2026.12.0", "2026.12.0")


def test_wrong_resulting_harness_versions_fail() -> None:
    """Target records must lock exactly to the selected stable pair."""
    before, after = _valid_locks()
    with pytest.raises(UpdaterError, match="homeassistant"):
        validate_lock_delta(before, after, "2026.12.1", "2026.12.0")


def _with_standard_options(lock: str) -> str:
    return lock.replace(
        "\n[[package]]",
        '\n[options]\nexclude-newer = "0001-01-01T00:00:00Z"\n'
        'exclude-newer-span = "P3D"\n\n[[package]]',
        1,
    )


def _with_cutoffs(lock: str, homeassistant: str, official: str) -> str:
    options = (
        '\n[options]\nexclude-newer = "0001-01-01T00:00:00Z"\n'
        'exclude-newer-span = "P3D"\n'
        "\n[options.exclude-newer-package]\n"
        f'homeassistant = "{homeassistant}"\n'
        f'pytest-homeassistant = "{official}"\n'
    )
    return lock.replace("\n[[package]]", options + "\n[[package]]", 1)


def test_early_pair_receives_only_two_fixed_artifact_cutoffs() -> None:
    """Manual waiver never sets UV_EXCLUDE_NEWER=false or opens other packages."""
    plan = make_plan(
        _project(),
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
        override_cooldown=True,
    )
    updated = update_pyproject(_pyproject(), plan)
    assert plan.cooldown_overridden is True
    assert 'exclude-newer = "3 days"' in updated
    assert (
        'exclude-newer-package = { homeassistant = "2026-12-30T00:00:01Z", '
        'pytest-homeassistant = "2026-12-30T00:00:01Z" }'
    ) in updated


def test_normal_update_removes_expired_exception() -> None:
    """An ordinary mature-pair promotion clears the former temporary waiver."""
    original = _pyproject().replace(
        'exclude-newer = "3 days"',
        'exclude-newer = "3 days"\n'
        'exclude-newer-package = { homeassistant = "2026-12-25T00:00:01Z", '
        'pytest-homeassistant = "2026-12-25T00:00:01Z" }',
    )
    updated = update_pyproject(original, _update_plan())
    assert "exclude-newer-package" not in updated


def test_current_pair_can_normalize_after_maturity_without_version_change() -> None:
    """A no-bump cleanup is a separate review-only update."""
    project = _project()
    project["tool"]["uv"]["exclude-newer-package"] = {
        "homeassistant": "2026-12-25T00:00:01Z",
        "pytest-homeassistant": "2026-12-25T00:00:01Z",
    }
    plan = make_plan(
        project,
        _selection(),
        _release(NOW - timedelta(days=4)),
        _release(NOW - timedelta(days=4)),
        NOW,
    )
    assert plan.status == "normalize"
    result = update_pyproject(
        _pyproject().replace(
            'exclude-newer = "3 days"',
            'exclude-newer = "3 days"\n'
            'exclude-newer-package = { homeassistant = "2026-12-25T00:00:01Z", '
            'pytest-homeassistant = "2026-12-25T00:00:01Z" }',
        ),
        plan,
    )
    assert "exclude-newer-package" not in result
    assert '"homeassistant==2026.11.0"' in result


def test_lock_cannot_change_scoped_cutoffs_except_as_plan_authorizes() -> None:
    before, after = _valid_locks()
    before = _with_standard_options(before)
    plan = make_plan(
        _project(),
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
        override_cooldown=True,
    )
    good = _with_cutoffs(after, "2026-12-30T00:00:01Z", "2026-12-30T00:00:01Z")
    validate_lock_delta(before, good, "2026.12.0", "2026.12.0", plan=plan)
    with pytest.raises(UpdaterError, match="package-level cutoff"):
        validate_lock_delta(
            before,
            good.replace("2026-12-30T00:00:01Z", "2026-12-31T00:00:00Z"),
            "2026.12.0",
            "2026.12.0",
            plan=plan,
        )


def test_normalization_rejects_any_package_record_movement() -> None:
    before, _ = _valid_locks()
    before = _with_cutoffs(before, "2026-11-05T13:03:50Z", "2026-11-05T13:03:59Z")
    project = _project()
    project["tool"]["uv"]["exclude-newer-package"] = {
        "homeassistant": "2026-11-05T13:03:50Z",
        "pytest-homeassistant": "2026-11-05T13:03:59Z",
    }
    plan = make_plan(
        project,
        _selection(),
        _release(NOW - timedelta(days=4)),
        _release(NOW - timedelta(days=4)),
        NOW,
    )
    after = _with_standard_options(_lock(ha="2026.11.0", official="2026.11.0"))
    validate_lock_delta(before, after, "2026.11.0", "2026.11.0", plan=plan)
    with pytest.raises(UpdaterError, match="preserve all package records"):
        validate_lock_delta(
            before,
            after.replace('version = "2026.11.0"', 'version = "2026.11.1"', 1),
            "2026.11.0",
            "2026.11.0",
            plan=plan,
        )


def test_cleanup_current_pair_while_future_pair_is_cooling() -> None:
    """A newer pair's cooldown must not postpone existing waiver retirement."""
    project = _project()
    project["tool"]["uv"]["exclude-newer-package"] = {
        "homeassistant": "2026-12-25T00:00:01Z",
        "pytest-homeassistant": "2026-12-25T00:00:01Z",
    }
    plan = make_plan(
        project,
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
        current_homeassistant_release=_release(NOW - timedelta(days=4)),
        current_official_release=_release(NOW - timedelta(days=4)),
    )
    assert plan.status == "normalize"
    assert plan.selected_homeassistant == "2026.11.0"
    assert plan.selected_official == "2026.11.0"
    assert plan.latest_homeassistant == "2026.12.0"
    assert plan.cooldown_overridden is False
    assert plan.mature_at == (NOW - timedelta(days=1)).isoformat()


def test_cannot_cleanup_when_current_pair_artifact_is_too_young() -> None:
    """Check actual current releases, not just a historical fixed cutoff."""
    project = _project()
    project["tool"]["uv"]["exclude-newer-package"] = {
        "homeassistant": "2026-12-25T00:00:01Z",
        "pytest-homeassistant": "2026-12-25T00:00:01Z",
    }
    plan = make_plan(
        project,
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
        current_homeassistant_release=_release(NOW - timedelta(days=4)),
        current_official_release=_release(NOW),
    )
    assert plan.status == "cooldown"
    assert plan.selected_homeassistant == "2026.12.0"


def test_future_pair_cleanup_requires_current_release_metadata() -> None:
    """Without current PyPI artifact ages, the updater fails closed."""
    project = _project()
    project["tool"]["uv"]["exclude-newer-package"] = {
        "homeassistant": "2026-12-25T00:00:01Z",
        "pytest-homeassistant": "2026-12-25T00:00:01Z",
    }
    plan = make_plan(
        project,
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
    )
    assert plan.status == "cooldown"


def test_early_manual_promotion_is_not_replaced_with_cleanup() -> None:
    """An explicitly authorized promotion remains a review-only pair update."""
    project = _project()
    project["tool"]["uv"]["exclude-newer-package"] = {
        "homeassistant": "2026-12-25T00:00:01Z",
        "pytest-homeassistant": "2026-12-25T00:00:01Z",
    }
    plan = make_plan(
        project,
        _selection("2026.12.0", "2026.12.0"),
        _release(NOW),
        _release(NOW),
        NOW,
        override_cooldown=True,
        current_homeassistant_release=_release(NOW - timedelta(days=4)),
        current_official_release=_release(NOW - timedelta(days=4)),
    )
    assert plan.status == "update"
    assert plan.cooldown_overridden
    assert plan.selected_homeassistant == "2026.12.0"


def test_pyproject_update_retires_old_pair_package_cutoffs() -> None:
    """The promoted pair must not inherit a cutoff for earlier artifacts."""
    temporary = (
        "\n# One-time artifact-bounded waiver for the already pinned HA 2026.11 GA pair.\n"
        "# Remove after 2026-11-08 13:04 UTC; all other packages retain the 3-day cooldown.\n"
        "[tool.uv.exclude-newer-package]\n"
        'homeassistant = "2026-11-05T13:03:50Z"\n'
        'pytest-homeassistant = "2026-11-05T13:03:59Z"\n'
        "\n[tool.ruff]\nline-length = 88\n"
    )
    updated = update_pyproject(_pyproject() + temporary, _update_plan())
    assert 'exclude-newer = "3 days"' in updated
    assert "exclude-newer-package" not in updated
    assert "One-time artifact-bounded waiver" not in updated
    assert "[tool.ruff]\nline-length = 88" in updated
    assert '"homeassistant==2026.12.0"' in updated
