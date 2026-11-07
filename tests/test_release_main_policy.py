"""Release preparation must not promote an unchecked or unmerged snapshot."""

import pytest

from scripts.release_main_policy import (
    REQUIRED_CHECKS,
    ReleasePolicyError,
    validate_checks,
    validate_draft_asset,
    validate_snapshot,
)

SHA = "a" * 40
OTHER = "b" * 40


def test_other_snapshots_are_rehearsal_only():
    validate_snapshot(OTHER, SHA, "workflow_dispatch", "refs/heads/main", "true")
    with pytest.raises(ReleasePolicyError, match="main commit"):
        validate_snapshot(OTHER, SHA, "workflow_dispatch", "refs/heads/main", "false")
    validate_snapshot(SHA, SHA, "workflow_dispatch", "refs/heads/main", "false")


@pytest.mark.parametrize(
    ("event", "ref", "dry"),
    [
        ("release", "refs/tags/v1", "false"),
        ("workflow_dispatch", "refs/heads/candidate", "true"),
        ("workflow_dispatch", "refs/heads/main", ""),
    ],
)
def test_unsafe_context_rejected(event, ref, dry):
    with pytest.raises(ReleasePolicyError):
        validate_snapshot(SHA, SHA, event, ref, dry)


def _checks():
    return [
        {
            "check_runs": [
                {
                    "name": name,
                    "id": i,
                    "app": {"id": 15368},
                    "head_sha": SHA,
                    "status": "completed",
                    "conclusion": "success",
                }
                for i, name in enumerate(sorted(REQUIRED_CHECKS))
            ]
        }
    ]


def test_all_exact_head_checks_required():
    pages = _checks()
    validate_checks(pages, SHA)
    with pytest.raises(ReleasePolicyError):
        validate_checks(pages, OTHER)


@pytest.mark.parametrize(
    "mutation", ["missing", "failure", "pending", "wrong_app", "rerun"]
)
def test_missing_failed_pending_or_spoofed_checks_rejected(mutation):
    pages = _checks()
    check = pages[0]["check_runs"][0]
    if mutation == "missing":
        pages[0]["check_runs"].pop(0)
    elif mutation == "failure":
        check["conclusion"] = "failure"
    elif mutation == "pending":
        check["status"] = "in_progress"
    elif mutation == "wrong_app":
        check["app"]["id"] = 1
    else:
        pages.append({"check_runs": [dict(check, id=100, status="in_progress")]})
    with pytest.raises(ReleasePolicyError):
        validate_checks(pages, SHA)


@pytest.mark.parametrize(
    "mutation",
    ["none", "different", "missing", "duplicate", "published", "channel", "tag"],
)
def test_post_upload_validation_detects_concurrent_changes(mutation):
    asset = {
        "name": "integration.zip",
        "state": "uploaded",
        "digest": "sha256:" + "b" * 64,
    }
    release = {
        "draft": True,
        "tag_name": "v1.0.0b1",
        "prerelease": True,
        "assets": [asset],
    }
    if mutation == "different":
        asset["digest"] = "sha256:" + "c" * 64
    elif mutation == "missing":
        release["assets"] = []
    elif mutation == "duplicate":
        release["assets"].append(asset)
    elif mutation == "published":
        release["draft"] = False
    elif mutation == "channel":
        release["prerelease"] = False
    elif mutation == "tag":
        release["tag_name"] = "v2.0.0"
    if mutation == "none":
        validate_draft_asset(release, "integration.zip", "b" * 64, "v1.0.0b1", "true")
    else:
        with pytest.raises(ReleasePolicyError):
            validate_draft_asset(
                release, "integration.zip", "b" * 64, "v1.0.0b1", "true"
            )
