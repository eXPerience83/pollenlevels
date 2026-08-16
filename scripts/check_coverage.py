"""Enforce per-module statement coverage floors from coverage.py JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

INTEGRATION_PATH = Path("custom_components/pollenlevels")
CONFIG_FLOW_PATH = INTEGRATION_PATH / "config_flow.py"
MIGRATION_PATH = INTEGRATION_PATH / "migration.py"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path)
    return parser.parse_args()


def main() -> int:
    """Report exact statement counts and enforce the project coverage floors."""
    coverage_path = _parse_args().coverage_json
    report = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = report["files"]
    failures: list[str] = []

    print("Module statement coverage:")
    for module_path in sorted(INTEGRATION_PATH.glob("*.py")):
        module = module_path.as_posix()
        if module not in files:
            failures.append(f"{module}: missing from coverage report")
            continue

        summary = files[module]["summary"]
        statements = summary["num_statements"]
        covered = summary["covered_lines"]
        missing = summary["missing_lines"]
        percentage = 100 * covered / statements if statements else 100.0
        suffix = " (reported only)" if module_path == MIGRATION_PATH else ""
        print(
            f"- {module}: {covered}/{statements} statements "
            f"({percentage:.6f}%); missing={missing}{suffix}"
        )

        if module_path == MIGRATION_PATH:
            continue
        if module_path == CONFIG_FLOW_PATH:
            if covered != statements:
                failures.append(
                    f"{module}: config flow must be 100% ({covered}/{statements})"
                )
        elif statements and covered * 100 <= statements * 95:
            failures.append(
                f"{module}: must be strictly above 95% ({covered}/{statements})"
            )

    if failures:
        print("Coverage gate failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Coverage gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
