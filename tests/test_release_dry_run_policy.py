"""Verify the release dry-run cannot enter the privileged finalization path."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_release_dry_run_is_validation_only() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "      dry_run:\n" in workflow
    assert (
        'description: "Validate and build ZIP only; do not create a tag or draft."'
        in workflow
    )
    assert (
        "if: github.event_name == 'workflow_dispatch' && inputs.dry_run == true"
        in workflow
    )
    assert (
        "if: needs.validate-release.outputs.skip_release != 'true' && "
        "(github.event_name != 'workflow_dispatch' || inputs.dry_run != true)"
    ) in workflow
    assert (
        workflow.index("      - name: Upload validated ZIP")
        < workflow.index("      - name: Report validation-only dry run")
        < workflow.index("  finalize-release:")
    )
    assert workflow.index("  finalize-release:") < workflow.index(
        "      - name: Create draft release"
    )
    assert "name: pollenlevels-release-asset" in workflow


def test_release_dry_run_has_unchanged_locked_validation() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "uv lock --check" in workflow
    assert "uv sync --locked --only-group release" in workflow
    assert "scripts/check_coverage.py coverage.json" in workflow
    assert "scripts/validate_release_zip.py" in workflow
    assert 'version="$(python -c' in workflow
    assert (
        'python "$RUNNER_TEMP/ha_pair_cooldown_trusted.py" check --stable-release-guard'
        in workflow
    )


def test_effective_dry_run_guards_keep_validation_and_block_finalization():
    workflow = yaml.load(
        Path(".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    assert jobs["finalize-release"]["if"] == (
        "needs.validate-release.outputs.skip_release != 'true' && "
        "(github.event_name != 'workflow_dispatch' || inputs.dry_run != true)"
    )
    validation = jobs["validate-release"]
    assert validation["permissions"] == {"contents": "read"}
    assert "if" not in validation
    steps = validation["steps"]
    upload = next(i for i, s in enumerate(steps) if s["name"] == "Upload validated ZIP")
    mandatory = {
        "Set up modern locked validation environment",
        "Validate release metadata",
        "Ruff validation",
        "Ruff format validation",
        "Run tests",
        "Build release ZIP (integration root at ZIP root)",
        "Validate ZIP package",
        "Calculate ZIP SHA-256",
    }
    selected = [s for s in steps[:upload] if s["name"] in mandatory]
    assert len(selected) == len(mandatory)
    for step in selected:
        assert "dry_run" not in step.get("if", "")
        assert "continue-on-error" not in step
