"""Regression tests for Home Assistant baseline PR publication."""

from __future__ import annotations

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
