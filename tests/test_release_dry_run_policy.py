"""Verify the release dry-run cannot enter the privileged finalization path."""

from __future__ import annotations

from pathlib import Path


def test_release_dry_run_is_validation_only() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "      dry_run:\n" in workflow
    assert 'description: "Validate and build ZIP only; do not create a tag or draft."' in workflow
    assert "if: github.event_name == 'workflow_dispatch' && inputs.dry_run == true" in workflow
    assert (
        "if: needs.validate-release.outputs.skip_release != 'true' && "
        "(github.event_name != 'workflow_dispatch' || inputs.dry_run != true)"
    ) in workflow
    assert workflow.index("      - name: Upload validated ZIP") < workflow.index(
        "      - name: Report validation-only dry run"
    ) < workflow.index("  finalize-release:")
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
    assert "python \"$RUNNER_TEMP/ha_pair_cooldown_trusted.py\" check --stable-release-guard" in workflow
