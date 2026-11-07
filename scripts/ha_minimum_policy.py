"""Enforce the fixed 2026.11.0 support floor for Pollen Levels CI."""

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
        # The hash-locked minimum has independent transitive versions: same HA
        # and pytest pins do not imply equivalence to uv.lock.
        run_minimum=True,
    )


def verify_frozen_minimum_inputs() -> None:
    """Require the committed hash-locked minimum fixture to remain unchanged."""
    path = Path(".github/requirements/minimum-ha.in")
    lines = path.read_text(encoding="utf-8").splitlines()
    expected = {
        "homeassistant": MINIMUM_HOMEASSISTANT,
        "pytest-homeassistant": MINIMUM_HOMEASSISTANT,
        "pytest": "9.0.3",
        "pytest-cov": "7.1.0",
        "aiointercept": "0.1.12",
        "packaging": "26.3",
    }
    pins: dict[str, str] = {}
    for raw in lines:
        if not raw or raw.startswith("#"):
            continue
        match = _PIN_RE.fullmatch(raw)
        if match is None:
            raise MinimumPolicyError(f"Invalid fixed minimum input: {raw!r}")
        name, version = match.groups()
        name = name.lower().replace("_", "-")
        if name in pins:
            raise MinimumPolicyError(f"Duplicate fixed minimum input: {name}")
        pins[name] = version
    if pins != expected:
        raise MinimumPolicyError(
            "Minimum input pins must match the audited 2026.11.0 SHA-256 lock"
        )
    compiled = Path(".github/requirements/minimum-ha.txt").read_text(encoding="utf-8")
    for name, version in expected.items():
        # Match the actual package line, never a suffix inside another package
        # (e.g. "homeassistant" inside "pytest-homeassistant"), and require
        # an adjacent SHA-256 hash in the uv-compiled record.
        pattern = (
            rf"(?m)^{re.escape(name)}=={re.escape(version)}"
            r"(?: ; python_full_version >= '3\.14\.2' and python_full_version < '3\.15')?"
            r"[ \t]+\\[ \t]*\r?\n"
            r"[ \t]+--hash=sha256:[0-9a-f]{64}(?:[ \t]+\\)?[ \t]*$"
        )
        if re.search(pattern, compiled) is None:
            raise MinimumPolicyError(
                f"Missing frozen minimum lock record or SHA-256 hash: {name}"
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
    verify_frozen_minimum_inputs()

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
