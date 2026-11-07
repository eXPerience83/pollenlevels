"""Keep draft preparation on the reviewed main snapshot and its completed checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess

REQUIRED_CHECKS = frozenset(
    {
        "actionlint",
        "lint",
        "tests",
        "validate",
        "validate-hacs",
        "zizmor",
        "package",
        "minimum-compatibility",
    }
)


class ReleasePolicyError(ValueError):
    """The selected snapshot cannot prepare a release draft."""


def validate_snapshot(
    selected: str, workflow: str, event: str, ref: str, dry_run: str
) -> None:
    """Unmerged and historical refs may only be rehearsed without write scope."""
    if event != "workflow_dispatch" or ref != "refs/heads/main":
        raise ReleasePolicyError("Release preparation must be dispatched from main")
    if dry_run not in {"true", "false"}:
        raise ReleasePolicyError("dry_run must be an explicit boolean")
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (selected, workflow)):
        raise ReleasePolicyError("Expected exact resolved commit SHAs")
    if dry_run == "false" and selected != workflow:
        raise ReleasePolicyError(
            "Draft preparation requires the workflow's main commit; use dry_run for other snapshots"
        )


def validate_checks(pages: list[dict], commit: str) -> None:
    """Require the latest GitHub Actions result for every blocking workflow."""
    latest = {}
    for page in pages:
        for check in page["check_runs"]:
            name = check.get("name")
            if name not in REQUIRED_CHECKS or check.get("app", {}).get("id") != 15368:
                continue
            if check.get("head_sha") != commit:
                continue
            if name not in latest or check["id"] > latest[name]["id"]:
                latest[name] = check
    for name in sorted(REQUIRED_CHECKS):
        check = latest.get(name, {})
        if check.get("status") != "completed" or check.get("conclusion") != "success":
            raise ReleasePolicyError(
                f"Required check is missing, pending or unsuccessful: {name}"
            )


def _api(endpoint: str, *, paginate: bool = False):
    command = ["gh", "api"]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    command.append(endpoint)
    return json.loads(subprocess.check_output(command, text=True, timeout=60))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    selected = os.environ["SELECTED_COMMIT"]
    validate_snapshot(
        selected,
        os.environ["TRUSTED_WORKFLOW_SHA"],
        os.environ["EVENT_NAME"],
        os.environ["WORKFLOW_REF"],
        os.environ["DRY_RUN"],
    )
    if args.finalize:
        if os.environ["DRY_RUN"] != "false":
            raise ReleasePolicyError("Dry runs cannot finalize")
        repository = os.environ["GITHUB_REPOSITORY"]
        current = _api(f"repos/{repository}/git/ref/heads/main")
        if current["object"]["sha"] != selected:
            raise ReleasePolicyError(
                "main changed during validation; dispatch a fresh run"
            )
        pages = _api(
            f"repos/{repository}/commits/{selected}/check-runs?filter=latest&per_page=100",
            paginate=True,
        )
        validate_checks(pages, selected)


if __name__ == "__main__":
    main()
