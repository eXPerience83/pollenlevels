"""Regression tests for Home Assistant baseline PR publication."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ha-test-baseline-updater.yml"


def _sanitize_ref_function() -> str:
    """Extract the real sanitize_ref shell function from the workflow."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^\s{10}sanitize_ref\(\) \{\n.*?^\s{10}\}\n",
        workflow,
    )
    assert match, "sanitize_ref function is missing from baseline updater workflow"
    return textwrap.dedent(match.group(0))


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("2026.9.3", "2026.9.3"),
        ("0.13.366", "0.13.366"),
        ("bad ref/@#", "bad-ref---"),
    ),
)
def test_baseline_pr_ref_sanitizer_is_portable(value: str, expected: str) -> None:
    """Execute the workflow sanitizer and reject the historical tr range bug."""
    if shutil.which("bash") is None or shutil.which("tr") is None:
        pytest.skip("bash and tr are required to execute the publication sanitizer")

    sanitizer = _sanitize_ref_function()
    assert "LC_ALL=C" in sanitizer
    assert "[:alnum:]_.-" in sanitizer
    assert "[:alnum:]._- " not in sanitizer

    env = os.environ.copy()
    env["VALUE"] = value
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"set -euo pipefail\n{sanitizer}printf '%s' \"$VALUE\" | sanitize_ref\n",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def test_publication_records_validated_commit_identities() -> None:
    """Bind the PR evidence to the validated base and proposed head."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    publication = workflow.split("      - name: Publish validated pull request", 1)[1]
    assert 'test "$(git rev-parse HEAD)" = "$BASE_SHA"' in publication
    assert 'head_sha="$(git rev-parse HEAD)"' in publication
    assert "Validated base commit:" in publication
    assert "Proposed head commit:" in publication
    assert 'if [[ "$remote_status" != 2 || -n "$expected_head" ]]; then' in publication
    assert 'test "$remote_branch" =' in publication
    assert publication.count('test "$remote_main" = "$BASE_SHA"') == 2
    final_check = publication.rindex('test "$remote_main" = "$BASE_SHA"')
    assert final_check < publication.index("git push")


def test_publication_push_only_creates_absent_branch(tmp_path: Path) -> None:
    """An unexpected branch is never overwritten, even by a fast-forward."""
    if shutil.which("git") is None or shutil.which("bash") is None:
        pytest.skip("git and bash are required to exercise publication lease")

    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    push = next(
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith("git push ")
    )
    remote = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "LC_ALL": "C"}
    subprocess.run(["git", "init", "--bare", str(remote)], env=env, check=True)
    subprocess.run(["git", "init", str(checkout)], env=env, check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=checkout,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    git("config", "user.name", "Baseline test")
    git("config", "user.email", "baseline@example.invalid")
    git("remote", "add", "origin", str(remote))
    git("commit", "--allow-empty", "-m", "first")
    first = git("rev-parse", "HEAD")
    branch = "automation/ha-test-baseline"
    push_env = {**env, "branch": branch, "expected_head": ""}
    subprocess.run(["bash", "-c", push], cwd=checkout, env=push_env, check=True)
    git("commit", "--allow-empty", "-m", "concurrent candidate")
    result = subprocess.run(
        ["bash", "-c", push],
        cwd=checkout,
        env=push_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert git("ls-remote", "origin", f"refs/heads/{branch}").split()[0] == first


@pytest.mark.parametrize(
    "scenario",
    [
        "refresh",
        "current",
        "manual",
        "closed",
        "race",
        "current_race",
        "fixed_newer",
        "create",
        "retained",
        "rejected",
        "legacy_rejected",
        "stale_closed",
        "orphan",
        "legacy_other",
    ],
)
def test_existing_pr_publication(tmp_path: Path, scenario: str) -> None:
    """Run the actual publication script with a real remote and scripted PR API."""
    if any(shutil.which(cmd) is None for cmd in ("git", "bash", "jq")):
        pytest.skip("git, bash and jq are required")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    publication = workflow.split("      - name: Publish validated pull request", 1)[1]
    script = textwrap.dedent(publication.split("        run: |\n", 1)[1])
    remote = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    candidate = "automation/ha-test-baseline-2026.11.3-official-2026.11.3"
    previous_candidate = "automation/ha-test-baseline-2026.11.2-official-2026.11.2"
    new_pr = scenario in (
        "create",
        "retained",
        "rejected",
        "legacy_rejected",
        "stale_closed",
        "orphan",
    )
    permanent = "automation/ha-test-baseline"
    branch = permanent if new_pr or scenario == "fixed_newer" else candidate
    if scenario == "legacy_other":
        branch = previous_candidate
    repo = "owner/repo"
    env = {
        "PATH": f"{shim_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "LC_ALL": "C",
        "GITHUB_REPOSITORY": repo,
        "RUNNER_TEMP": str(tmp_path),
        "PLAN_STATUS": "update",
        "HOMEASSISTANT_VERSION": "2026.11.3",
        "OFFICIAL_VERSION": "2026.11.3",
        "FIXTURE_DIR": str(tmp_path),
        "BASELINE_BRANCH": branch,
    }
    subprocess.run(["git", "init", "--bare", str(remote)], env=env, check=True)
    subprocess.run(["git", "init", str(checkout)], env=env, check=True)

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=checkout,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def write_pins(value: str) -> None:
        for name in ("pyproject.toml", "uv.lock"):
            (checkout / name).write_text(value, encoding="utf-8")

    git("config", "user.name", "Baseline test")
    git("config", "user.email", "baseline@example.invalid")
    git("remote", "add", "origin", str(remote))
    write_pins("old")
    git("add", "pyproject.toml", "uv.lock")
    git("commit", "-m", "base")
    old_base = git("rev-parse", "HEAD")
    git("branch", "-M", "main")
    git("checkout", "-b", branch)
    write_pins("new")
    git("commit", "-am", "old proposal")
    old_head = git("rev-parse", "HEAD")
    old_tree = git("rev-parse", "HEAD^{tree}")
    if scenario not in ("create", "legacy_rejected", "stale_closed"):
        git("push", "origin", branch)
    git("checkout", "main")
    if scenario not in ("current", "current_race"):
        git("commit", "--allow-empty", "-m", "main advances")
    base = git("rev-parse", "HEAD")
    git("push", "origin", "main")
    write_pins("new")
    env["BASE_SHA"] = base
    body = (
        "Generated by the Home Assistant test baseline updater.\n"
        f"- Validated base commit: {old_base}\n"
        f"- Proposed head commit: {old_head}\n"
        f"- Baseline candidate: {candidate}\n"
    )
    if scenario in ("fixed_newer", "retained", "stale_closed"):
        body = body.replace(candidate, previous_candidate)
    if scenario == "stale_closed":
        body = body.replace(old_head, old_base)
    pr = {
        "number": 123,
        "state": "open",
        "base": {"ref": "main"},
        "head": {"ref": branch, "sha": old_head, "repo": {"full_name": repo}},
        "user": {"login": "github-actions[bot]"},
        "body": body,
    }
    author = {"login": "github-actions[bot]"}
    commit = {
        "sha": old_head,
        "author": author,
        "committer": author,
        "parents": [{"sha": old_base}],
        "commit": {
            "message": (
                "chore(deps): propose reviewed HA/official "
                "pytest-homeassistant test baseline"
            ),
            "tree": {"sha": old_tree},
        },
        "files": [
            {"filename": name, "status": "modified"}
            for name in ("pyproject.toml", "uv.lock")
        ],
    }
    if scenario == "manual":
        commit["author"] = {"login": "human"}
    current = {**pr, "state": "closed" if scenario == "closed" else "open"}
    for name, data in (
        ("open.json", None if new_pr else pr),
        ("commits.json", [commit]),
        ("commit.json", commit),
        ("current.json", current),
        (
            "history.json",
            {**pr, "state": "closed", "merged_at": None}
            if scenario in ("retained", "rejected", "stale_closed")
            else None,
        ),
        (
            "legacy.json",
            {
                **pr,
                "state": "closed",
                "merged_at": None,
                "head": {**pr["head"], "ref": candidate},
            }
            if scenario == "legacy_rejected"
            else None,
        ),
    ):
        (tmp_path / name).write_text(
            "" if data is None else json.dumps(data), encoding="utf-8"
        )
    (tmp_path / "pr-body-final.md").write_text(
        body.splitlines()[0] + "\n", encoding="utf-8"
    )
    shim = shim_dir / "gh"
    shim.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'case "$*" in\n'
        '  "api --method GET --paginate "*'
        '"-f head=owner:automation/ha-test-baseline "*)\n'
        '    cat "$FIXTURE_DIR/history.json";;\n'
        '  "api --method GET --paginate "*) cat "$FIXTURE_DIR/legacy.json";;\n'
        '  "api --paginate "*) cat "$FIXTURE_DIR/open.json";;\n'
        '  "api "*"/pulls/123/commits") cat "$FIXTURE_DIR/commits.json";;\n'
        '  "api "*"/commits/"*) cat "$FIXTURE_DIR/commit.json";;\n'
        '  "api "*"/pulls/123")\n'
        '    cat "$FIXTURE_DIR/current.json"\n'
        '    if [[ "${RACE:-}" == yes ]]; then\n'
        '      git push --force origin "$BASE_SHA:refs/heads/$BASELINE_BRANCH" >&2\n'
        "    fi;;\n"
        '  "auth setup-git") ;;\n'
        '  "pr edit 123 "*) touch "$FIXTURE_DIR/edited";;\n'
        '  "pr create "*) touch "$FIXTURE_DIR/created";;\n'
        "  *) exit 99;;\n"
        "esac\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    if scenario in ("race", "current_race"):
        env["RACE"] = "yes"
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    remote_ref = git("ls-remote", "origin", f"refs/heads/{branch}")
    actual = remote_ref.split()[0] if remote_ref else ""
    if scenario in ("refresh", "fixed_newer", "create", "retained"):
        assert result.returncode == 0, result.stderr
        assert actual != old_head
        assert git("rev-parse", f"{actual}^") == base
        assert git("rev-parse", f"{actual}^{{tree}}") == old_tree
        assert (tmp_path / ("created" if new_pr else "edited")).exists()
        assert not (tmp_path / ("edited" if new_pr else "created")).exists()
        assert f"Proposed head commit: {actual}" in (
            tmp_path / "pr-body-final.md"
        ).read_text(encoding="utf-8")
    elif scenario in ("current", "rejected", "legacy_rejected"):
        assert result.returncode == 0, result.stderr
        assert actual == ("" if scenario == "legacy_rejected" else old_head)
        assert not (tmp_path / "edited").exists()
        assert not (tmp_path / "created").exists()
    elif scenario == "stale_closed":
        assert result.returncode != 0
        assert "stale head provenance" in result.stderr
        assert actual == ""
        assert not (tmp_path / "edited").exists()
        assert not (tmp_path / "created").exists()
    else:
        assert result.returncode != 0
        assert actual == (base if scenario in ("race", "current_race") else old_head)
        assert not (tmp_path / "edited").exists()
        assert not (tmp_path / "created").exists()
