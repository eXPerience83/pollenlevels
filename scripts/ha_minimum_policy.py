"""Enforce the fixed 2026.11.0 support floor for Pollen Levels 5.x CI."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MINIMUM_HOMEASSISTANT = "2026.11.0"
_VERSION_RE = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d+)$")
_PIN_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)==([^;\s]+)$")


class MinimumPolicyError(ValueError):
    """The declared compatibility floor or official pair is inconsistent."""


@dataclass(frozen=True)
class MinimumPlan:
    minimum_homeassistant: str
    current_homeassistant: str
    run_minimum: bool


def _release(version: object) -> tuple[int, int, int]:
    if not isinstance(version, str) or not (match := _VERSION_RE.fullmatch(version)):
        raise MinimumPolicyError(
            f"Expected an exact stable HA release, got {version!r}"
        )
    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def plan_minimum(pyproject: dict[str, Any], hacs: dict[str, Any]) -> MinimumPlan:
    """Fail closed if the static minimum or paired official test pins drift."""
    minimum = hacs.get("homeassistant")
    if minimum != MINIMUM_HOMEASSISTANT:
        raise MinimumPolicyError(
            f"hacs.json must preserve HA floor {MINIMUM_HOMEASSISTANT}; got {minimum!r}"
        )

    groups = pyproject.get("dependency-groups")
    if not isinstance(groups, dict) or not isinstance(groups.get("test"), list):
        raise MinimumPolicyError("Missing [dependency-groups].test pins")

    pins: dict[str, str] = {}
    for requirement in groups["test"]:
        if not isinstance(requirement, str):
            raise MinimumPolicyError("Test requirements must use exact string pins")
        match = _PIN_RE.fullmatch(requirement)
        if match is None:
            raise MinimumPolicyError(f"Non-exact test requirement: {requirement!r}")
        name, version = match.groups()
        normalized = name.lower().replace("_", "-")
        if normalized in pins:
            raise MinimumPolicyError(f"Duplicate test pin: {normalized}")
        pins[normalized] = version

    if "pytest-homeassistant-custom-component" in pins:
        raise MinimumPolicyError("PHACC must not be installed on the v5 line")
    current = pins.get("homeassistant")
    official = pins.get("pytest-homeassistant")
    _release(current)
    _release(official)
    if current != official:
        raise MinimumPolicyError("Official pytest-homeassistant must exactly match HA")
    if _release(current) < _release(MINIMUM_HOMEASSISTANT):
        raise MinimumPolicyError("Locked test baseline cannot be older than HA floor")

    return MinimumPlan(
        minimum_homeassistant=MINIMUM_HOMEASSISTANT,
        current_homeassistant=current,
        run_minimum=current != MINIMUM_HOMEASSISTANT,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()

    with Path("pyproject.toml").open("rb") as file:
        project = tomllib.load(file)
    with Path("hacs.json").open(encoding="utf-8") as file:
        hacs = json.load(file)
    plan = plan_minimum(project, hacs)

    with args.github_output.open("a", encoding="utf-8") as file:
        file.write(f"run_minimum={str(plan.run_minimum).lower()}\n")
        file.write(f"minimum_ha={plan.minimum_homeassistant}\n")
        file.write(f"current_ha={plan.current_homeassistant}\n")
    print(
        f"Home Assistant floor={plan.minimum_homeassistant}, "
        f"current={plan.current_homeassistant}, "
        f"independent minimum suite={plan.run_minimum}"
    )


if __name__ == "__main__":
    main()
