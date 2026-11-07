"""Regression checks for Pollen Levels' artifact-bounded HA/pytest cooldown exceptions."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from scripts.ha_pair_cooldown import (
    CooldownPolicyError,
    configured_cutoffs,
    cutoff_for_upload,
    validate_policy,
)

NOW = datetime(2026, 11, 7, tzinfo=UTC)
HA_CUTOFF = "2026-11-05T13:03:50Z"
OFFICIAL_CUTOFF = "2026-11-05T13:03:59Z"


def _project(*, scoped: bool = True) -> dict:
    uv: dict = {"exclude-newer": "3 days"}
    if scoped:
        uv["exclude-newer-package"] = {
            "homeassistant": HA_CUTOFF,
            "pytest-homeassistant": OFFICIAL_CUTOFF,
        }
    return {
        "tool": {"uv": uv},
        "dependency-groups": {
            "test": [
                "pytest-homeassistant==2026.11.0",
                "homeassistant==2026.11.0",
            ]
        },
    }


def _lock(*, scoped: bool = True) -> dict:
    options: dict = {
        "exclude-newer": "0001-01-01T00:00:00Z",
        "exclude-newer-span": "P3D",
    }
    if scoped:
        options["exclude-newer-package"] = {
            "homeassistant": HA_CUTOFF,
            "pytest-homeassistant": OFFICIAL_CUTOFF,
        }
    return {
        "options": options,
        "package": [
            {
                "name": "homeassistant",
                "version": "2026.11.0",
                "source": {"registry": "https://pypi.org/simple"},
                "sdist": {
                    "hash": "sha256:" + "a" * 64,
                    "upload-time": "2026-11-05T13:03:49.664Z",
                },
            },
            {
                "name": "pytest-homeassistant",
                "version": "2026.11.0",
                "source": {"registry": "https://pypi.org/simple"},
                "wheels": [
                    {
                        "hash": "sha256:" + "b" * 64,
                        "upload-time": "2026-11-05T13:03:58.983Z",
                    }
                ],
            },
        ],
    }


def test_known_official_pair_cutoffs_are_valid_and_artifact_bounded() -> None:
    assert validate_policy(_project(), _lock(), now=NOW) == {
        "homeassistant": HA_CUTOFF,
        "pytest-homeassistant": OFFICIAL_CUTOFF,
    }


def test_normal_policy_has_no_exempt_packages() -> None:
    assert (
        validate_policy(
            _project(scoped=False), _lock(scoped=False), now=NOW, stable_release=True
        )
        == {}
    )


def test_stable_release_rejects_scoped_maturity_exception() -> None:
    with pytest.raises(CooldownPolicyError, match="stable release"):
        validate_policy(_project(), _lock(), now=NOW, stable_release=True)


@pytest.mark.parametrize(
    ("invalid", "match"),
    [
        (False, "absolute UTC"),
        ("3 days", "absolute UTC"),
        ("2026-11-05", "absolute UTC"),
        ("2026-11-05T13:04:00+00:00", "absolute UTC"),
        ("2026-11-05T13:03:51Z", "artifact bounds"),
        ("2026-11-05T13:10:00Z", "artifact bounds"),
        ("2026-11-05T13:00:00Z", "artifact bounds"),
        ("2026-11-08T13:03:50Z", "artifact bounds"),
    ],
)
def test_rejects_wrong_or_unbounded_package_cutoffs(
    invalid: object, match: str
) -> None:
    project = _project()
    lock = _lock()
    project["tool"]["uv"]["exclude-newer-package"]["homeassistant"] = invalid
    lock["options"]["exclude-newer-package"]["homeassistant"] = invalid
    with pytest.raises(CooldownPolicyError, match=match):
        validate_policy(project, lock, now=NOW)


def test_rejects_extra_package_or_only_one_member_of_pair() -> None:
    project = _project()
    lock = _lock()
    project["tool"]["uv"]["exclude-newer-package"]["multidict"] = HA_CUTOFF
    lock["options"]["exclude-newer-package"]["multidict"] = HA_CUTOFF
    with pytest.raises(CooldownPolicyError, match="exact HA/official"):
        validate_policy(project, lock, now=NOW)
    del project["tool"]["uv"]["exclude-newer-package"]["multidict"]
    del lock["options"]["exclude-newer-package"]["multidict"]
    del project["tool"]["uv"]["exclude-newer-package"]["homeassistant"]
    with pytest.raises(CooldownPolicyError, match="exact HA/official"):
        validate_policy(project, lock, now=NOW)


def test_empty_package_exception_is_rejected() -> None:
    """An empty section must not silently survive an updater transition."""
    project = _project()
    lock = _lock()
    project["tool"]["uv"]["exclude-newer-package"] = {}
    lock["options"]["exclude-newer-package"] = {}
    with pytest.raises(CooldownPolicyError, match="exact HA/official pytest pair"):
        validate_policy(project, lock, now=NOW)


def test_rejects_source_lock_mismatch_and_false_global_override() -> None:
    lock = _lock()
    lock["options"]["exclude-newer-package"]["homeassistant"] = False
    with pytest.raises(CooldownPolicyError, match="differ"):
        validate_policy(_project(), lock, now=NOW)
    lock = _lock()
    lock["options"]["exclude-newer-span"] = "P0D"
    with pytest.raises(CooldownPolicyError, match="global"):
        validate_policy(_project(), lock, now=NOW)


def test_rejects_unauthorized_global_environment_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UV_EXCLUDE_NEWER", "false")
    with pytest.raises(CooldownPolicyError, match="UV_EXCLUDE_NEWER"):
        validate_policy(_project(), _lock(), now=NOW)


def test_rejects_unknown_artifacts_and_mismatched_harness_versions() -> None:
    lock = _lock()
    lock["package"][1]["wheels"][0]["hash"] = "sha256:" + "z" * 64
    with pytest.raises(CooldownPolicyError, match="artifact or hash"):
        validate_policy(_project(), lock, now=NOW)
    lock = _lock()
    lock["package"][1]["version"] = "2026.11.1"
    with pytest.raises(CooldownPolicyError, match="does not match"):
        validate_policy(_project(), lock, now=NOW)


def test_rejects_cutoff_after_current_time() -> None:
    with pytest.raises(CooldownPolicyError, match="artifact bounds"):
        validate_policy(
            _project(),
            _lock(),
            now=datetime(2026, 11, 5, 13, 3, tzinfo=UTC),
        )


def test_ceil_uploaded_artifact_timestamp_is_one_second() -> None:
    assert (
        cutoff_for_upload(datetime.fromisoformat("2026-11-05T13:03:49.664+00:00"))
        == HA_CUTOFF
    )


def test_configured_cutoffs_reject_non_exact_global_policy() -> None:
    project = deepcopy(_project())
    project["tool"]["uv"]["exclude-newer"] = False
    with pytest.raises(CooldownPolicyError, match="three days|3 days"):
        configured_cutoffs(project)


def test_release_guard_uses_trusted_workflow_revision() -> None:
    """Historical release snapshots need not contain the new policy helper."""
    from pathlib import Path

    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert workflow.index("Preserve scoped cooldown guard from trusted workflow revision") < (
        workflow.index("Check out selected snapshot")
    )
    assert 'git show "$TRUSTED_WORKFLOW_SHA:scripts/ha_pair_cooldown.py"' in workflow
    assert (
        'python "$RUNNER_TEMP/ha_pair_cooldown_trusted.py" check --stable-release-guard'
    ) in workflow
