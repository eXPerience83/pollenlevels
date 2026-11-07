"""Validate temporary artifact-bounded exceptions to the HA test-pair cooldown."""

from __future__ import annotations

import argparse
import json
import os
import re
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
from typing import Any

PAIR = ("homeassistant", "pytest-homeassistant")
CUTOFF_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
PIN_RE = re.compile(r"(homeassistant|pytest-homeassistant)==(\d{4}\.\d{1,2}\.\d+)")


class CooldownPolicyError(ValueError):
    """The configured uv package-specific exception is unsafe."""


def parse_cutoff(value: object) -> datetime:
    """Accept only fixed UTC seconds, not relative ages, dates or false."""
    if not isinstance(value, str) or CUTOFF_RE.fullmatch(value) is None:
        raise CooldownPolicyError("package cutoff must be an absolute UTC timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as err:
        raise CooldownPolicyError("invalid absolute package cutoff") from err


def cutoff_for_upload(uploaded: datetime) -> str:
    """Include the published artifact, but no later uploads by default."""
    if uploaded.tzinfo is None or uploaded.utcoffset() is None:
        raise CooldownPolicyError("artifact upload time must be timezone-aware")
    cutoff = uploaded.astimezone(UTC).replace(microsecond=0) + timedelta(seconds=1)
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")


def configured_cutoffs(project: dict[str, Any]) -> dict[str, str]:
    """Validate that an exception, when present, covers the exact official pair."""
    uv = project.get("tool", {}).get("uv", {})
    if not isinstance(uv, dict) or uv.get("exclude-newer") != "3 days":
        raise CooldownPolicyError("global uv cooldown must remain 3 days")
    configured = uv.get("exclude-newer-package")
    if configured is None:
        return {}
    if not isinstance(configured, dict) or set(configured) != set(PAIR):
        raise CooldownPolicyError(
            "only the exact HA/official pytest pair may be exempted"
        )
    for value in configured.values():
        parse_cutoff(value)
    return configured


def _pinned_pair(project: dict[str, Any]) -> dict[str, str]:
    groups = project.get("dependency-groups", {})
    test = groups.get("test") if isinstance(groups, dict) else None
    if not isinstance(test, list):
        raise CooldownPolicyError("missing test dependency pins")
    result: dict[str, str] = {}
    for requirement in test:
        if not isinstance(requirement, str):
            raise CooldownPolicyError("non-string test dependency")
        match = PIN_RE.fullmatch(requirement)
        if match is not None:
            name, version = match.groups()
            if name in result:
                raise CooldownPolicyError("duplicate official test-pair pin")
            result[name] = version
    if set(result) != set(PAIR) or len(set(result.values())) != 1:
        raise CooldownPolicyError("official HA and pytest versions must match exactly")
    return result


def validate_policy(
    project: dict[str, Any],
    lock: dict[str, Any],
    *,
    now: datetime | None = None,
    stable_release: bool = False,
) -> dict[str, str]:
    """Verify lock/source parity and limit cutoffs to known locked artifacts."""
    if os.getenv("UV_EXCLUDE_NEWER") not in (None, "3 days"):
        raise CooldownPolicyError("global UV_EXCLUDE_NEWER override is forbidden")
    cutoffs = configured_cutoffs(project)
    options = lock.get("options")
    if not isinstance(options, dict) or {
        k: v for k, v in options.items() if k != "exclude-newer-package"
    } != {
        "exclude-newer": "0001-01-01T00:00:00Z",
        "exclude-newer-span": "P3D",
    }:
        raise CooldownPolicyError("unexpected global uv.lock cutoff metadata")
    locked_cutoffs = options.get("exclude-newer-package", {})
    if locked_cutoffs != cutoffs:
        raise CooldownPolicyError("pyproject and uv.lock package cutoffs differ")
    if not cutoffs:
        return {}
    if stable_release:
        raise CooldownPolicyError("stable release requires normalized cooldown")
    pins = _pinned_pair(project)
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise CooldownPolicyError("missing uv.lock package records")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    for name in PAIR:
        records = [
            record
            for record in packages
            if isinstance(record, dict) and record.get("name") == name
        ]
        if len(records) != 1 or records[0].get("version") != pins[name]:
            raise CooldownPolicyError(f"locked {name} version does not match")
        record = records[0]
        source = record.get("source")
        if (
            not isinstance(source, dict)
            or source.get("registry") != "https://pypi.org/simple"
        ):
            raise CooldownPolicyError(f"{name} must be sourced from PyPI")
        distributions = []
        if "sdist" in record:
            distributions.append(record["sdist"])
        wheels = record.get("wheels", [])
        if not isinstance(wheels, list):
            raise CooldownPolicyError(f"malformed {name} wheels")
        distributions.extend(wheels)
        if not distributions:
            raise CooldownPolicyError(f"no locked {name} artifacts")
        uploaded: list[datetime] = []
        for artifact in distributions:
            if (
                not isinstance(artifact, dict)
                or not re.fullmatch(
                    r"sha256:[a-f0-9]{64}", str(artifact.get("hash", ""))
                )
                or not isinstance(artifact.get("upload-time"), str)
            ):
                raise CooldownPolicyError(f"unknown {name} artifact or hash")
            try:
                timestamp = datetime.fromisoformat(
                    artifact["upload-time"].replace("Z", "+00:00")
                )
            except ValueError as err:
                raise CooldownPolicyError(f"invalid {name} upload time") from err
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise CooldownPolicyError(f"unqualified {name} upload time")
            uploaded.append(timestamp.astimezone(UTC))
        cutoff = parse_cutoff(cutoffs[name])
        last = max(uploaded)
        # Exactly the next UTC second after the last locked artifact:
        # a five-minute tolerance could silently authorize an omitted upload.
        if cutoff_for_upload(last) != cutoffs[name] or cutoff > current:
            raise CooldownPolicyError(f"{name} cutoff exceeds known artifact bounds")
    return cutoffs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.add_argument("--stable-release-guard", action="store_true")
    args = parser.parse_args()
    try:
        with Path("pyproject.toml").open("rb") as file:
            project = tomllib.load(file)
        with Path("uv.lock").open("rb") as file:
            lock = tomllib.load(file)
        stable = False
        if args.stable_release_guard:
            manifest = json.loads(
                Path("custom_components/pollenlevels/manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            stable = re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]) is not None
        cutoffs = validate_policy(project, lock, stable_release=stable)
        sys.stdout.write(
            "HA pair cooldown: "
            + (f"artifact-bounded {cutoffs}" if cutoffs else "normal 3 days")
            + "\n"
        )
    except (CooldownPolicyError, OSError, ValueError, KeyError) as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()
