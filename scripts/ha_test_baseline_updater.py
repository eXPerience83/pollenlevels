"""Plan and validate focused Home Assistant test-baseline updates."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

try:
    from scripts.select_ha_harness import (
        HarnessSelection,
        SelectionError,
        fetch_pypi_metadata,
        select_stable_harness,
    )
except ModuleNotFoundError:  # Direct script execution does not add the root package.
    from select_ha_harness import (  # type: ignore[no-redef]
        HarnessSelection,
        SelectionError,
        fetch_pypi_metadata,
        select_stable_harness,
    )

HOMEASSISTANT = "homeassistant"
PHACC = "pytest-homeassistant-custom-component"
LOCAL_PACKAGE = "pollenlevels"
TARGET_PACKAGES = (HOMEASSISTANT, PHACC)
PIN_TEMPLATE = '    "{name}=={version}",'
COOLDOWN_PATTERN = re.compile(r"^(?P<days>[1-9][0-9]*) days$")


class UpdaterError(ValueError):
    """Raised when the updater cannot safely promote a baseline."""


@dataclass(frozen=True)
class BaselinePlan:
    """Machine-readable selected pair and promotion decision."""

    current_homeassistant: str
    current_phacc: str
    selected_homeassistant: str
    selected_phacc: str
    latest_homeassistant: str
    latest_phacc: str
    homeassistant_mature_at: str
    phacc_mature_at: str
    mature_at: str
    cooldown_days: int
    skipped_prerelease_phacc: tuple[str, ...]
    status: str


def _exact_test_pins(project: Mapping[str, object]) -> dict[str, str]:
    groups = project.get("dependency-groups")
    if not isinstance(groups, Mapping) or not isinstance(groups.get("test"), list):
        raise UpdaterError("pyproject.toml has no test dependency group")
    pins: dict[str, str] = {}
    for item in groups["test"]:
        if not isinstance(item, str):
            raise UpdaterError(
                "test dependency group contains a non-string requirement"
            )
        try:
            requirement = Requirement(item)
        except Exception as err:
            raise UpdaterError(
                "test dependency group contains an invalid requirement"
            ) from err
        name = canonicalize_name(requirement.name)
        if name not in TARGET_PACKAGES:
            continue
        specifiers = tuple(requirement.specifier)
        if (
            requirement.url is not None
            or len(specifiers) != 1
            or specifiers[0].operator != "=="
            or specifiers[0].version.endswith(".*")
            or name in pins
        ):
            raise UpdaterError(f"test dependency {name} must have one exact unique pin")
        pins[name] = specifiers[0].version
    if set(pins) != set(TARGET_PACKAGES):
        raise UpdaterError("test dependency group must contain exact HA and PHACC pins")
    return pins


def cooldown_days(project: Mapping[str, object]) -> int:
    """Read the supported whole-day uv supply-chain cooldown."""
    tool = project.get("tool")
    uv = tool.get("uv") if isinstance(tool, Mapping) else None
    value = uv.get("exclude-newer") if isinstance(uv, Mapping) else None
    if (
        not isinstance(value, str)
        or (match := COOLDOWN_PATTERN.fullmatch(value)) is None
    ):
        raise UpdaterError("[tool.uv].exclude-newer must be a positive whole-day value")
    return int(match["days"])


def _parse_upload_time(value: object, package: str, version: str) -> datetime:
    if not isinstance(value, str):
        raise UpdaterError(f"{package} {version} artifact has no upload_time_iso_8601")
    try:
        uploaded = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise UpdaterError(
            f"{package} {version} artifact has an invalid upload_time_iso_8601"
        ) from err
    if uploaded.tzinfo is None or uploaded.utcoffset() is None:
        raise UpdaterError(
            f"{package} {version} artifact upload_time_iso_8601 must be timezone-aware"
        )
    return uploaded.astimezone(UTC)


def release_mature_at(
    metadata: Mapping[str, object], package: str, version: str, days: int
) -> datetime:
    """Return the conservative maturity instant for one PyPI release response."""
    artifacts = metadata.get("urls")
    if not isinstance(artifacts, list) or not artifacts:
        raise UpdaterError(f"{package} {version} has no release artifact list")
    usable: list[datetime] = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise UpdaterError(f"{package} {version} has a malformed artifact object")
        yanked = artifact.get("yanked")
        if not isinstance(yanked, bool):
            raise UpdaterError(f"{package} {version} artifact yanked must be boolean")
        uploaded = _parse_upload_time(
            artifact.get("upload_time_iso_8601"), package, version
        )
        if not yanked:
            usable.append(uploaded)
    if not usable:
        raise UpdaterError(f"{package} {version} has only yanked artifacts")
    return max(usable) + timedelta(days=days)


def make_plan(
    project: Mapping[str, object],
    selection: HarnessSelection,
    homeassistant_release: Mapping[str, object],
    phacc_release: Mapping[str, object],
    now: datetime,
) -> BaselinePlan:
    """Classify a stable selected pair without performing any file mutation."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise UpdaterError("planner time must be timezone-aware")
    pins = _exact_test_pins(project)
    days = cooldown_days(project)
    try:
        current_ha = Version(pins[HOMEASSISTANT])
        current_phacc = Version(pins[PHACC])
        selected_ha = Version(selection.selected_homeassistant)
        selected_phacc = Version(selection.selected_phacc)
    except InvalidVersion as err:
        raise UpdaterError("baseline or selected version is invalid") from err
    if selected_ha < current_ha or selected_phacc < current_phacc:
        raise UpdaterError("selected stable harness pair would downgrade the baseline")

    ha_mature_at = release_mature_at(
        homeassistant_release, HOMEASSISTANT, selection.selected_homeassistant, days
    )
    phacc_mature_at = release_mature_at(
        phacc_release, PHACC, selection.selected_phacc, days
    )
    mature_at = max(ha_mature_at, phacc_mature_at)
    if selected_ha == current_ha and selected_phacc == current_phacc:
        status = "current"
    elif now.astimezone(UTC) < mature_at:
        status = "cooldown"
    else:
        status = "update"
    return BaselinePlan(
        current_homeassistant=pins[HOMEASSISTANT],
        current_phacc=pins[PHACC],
        selected_homeassistant=selection.selected_homeassistant,
        selected_phacc=selection.selected_phacc,
        latest_homeassistant=selection.latest_homeassistant,
        latest_phacc=selection.latest_phacc,
        homeassistant_mature_at=ha_mature_at.isoformat(),
        phacc_mature_at=phacc_mature_at.isoformat(),
        mature_at=mature_at.isoformat(),
        cooldown_days=days,
        skipped_prerelease_phacc=selection.skipped_prerelease_phacc,
        status=status,
    )


def update_pyproject(text: str, plan: BaselinePlan) -> str:
    """Return the narrowly updated project text or fail on ambiguous source pins."""
    if plan.status != "update":
        raise UpdaterError("pyproject mutation requires an update plan")
    replacements = (
        (PHACC, plan.current_phacc, plan.selected_phacc),
        (HOMEASSISTANT, plan.current_homeassistant, plan.selected_homeassistant),
    )
    result = text
    for name, old_version, new_version in replacements:
        old = PIN_TEMPLATE.format(name=name, version=old_version)
        new = PIN_TEMPLATE.format(name=name, version=new_version)
        if result.count(old) != 1:
            raise UpdaterError(f"expected one exact {name} pin in pyproject.toml")
        result = result.replace(old, new, 1)
    if plan.current_homeassistant != plan.selected_homeassistant:
        old_comment = (
            f"# Home Assistant {plan.current_homeassistant} requires Python 3.14.2+, "
            "while CI itself uses the"
        )
        new_comment = (
            f"# Home Assistant {plan.selected_homeassistant} requires Python 3.14.2+, "
            "while CI itself uses the"
        )
        if result.count(old_comment) != 1:
            raise UpdaterError(
                "expected one exact Home Assistant compatibility comment"
            )
        result = result.replace(old_comment, new_comment, 1)
    project = tomllib.loads(result)
    pins = _exact_test_pins(project)
    if pins != {
        HOMEASSISTANT: plan.selected_homeassistant,
        PHACC: plan.selected_phacc,
    }:
        raise UpdaterError("updated pyproject pins do not match the selected pair")
    return result


def _package_groups(lock: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise UpdaterError("uv.lock has no package records")
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in packages:
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            raise UpdaterError("uv.lock contains an invalid package record")
        grouped[canonicalize_name(record["name"])].append(record)
    return dict(grouped)


def _validate_target_group(
    groups: Mapping[str, list[dict[str, object]]], name: str, expected: str
) -> None:
    records = groups.get(name)
    if not isinstance(records, list) or len(records) != 1:
        raise UpdaterError(f"uv.lock must contain exactly one {name} record")
    if records[0].get("version") != expected:
        raise UpdaterError(f"locked {name} does not match selected version {expected}")


def _validate_local_record(
    before: list[dict[str, object]],
    after: list[dict[str, object]],
    homeassistant: str,
    phacc: str,
) -> None:
    if len(before) != 1 or len(after) != 1:
        raise UpdaterError("uv.lock must contain exactly one local pollenlevels record")
    old, new = deepcopy(before[0]), deepcopy(after[0])
    if old.get("version") != new.get("version") or old.get("source") != new.get(
        "source"
    ):
        raise UpdaterError("local pollenlevels version or source changed")
    old_metadata = old.pop("metadata", None)
    new_metadata = new.pop("metadata", None)
    if (
        old != new
        or not isinstance(old_metadata, dict)
        or not isinstance(new_metadata, dict)
    ):
        raise UpdaterError("unexpected local pollenlevels lock metadata movement")
    old_requires = old_metadata.pop("requires-dev", None)
    new_requires = new_metadata.pop("requires-dev", None)
    if (
        old_metadata != new_metadata
        or not isinstance(old_requires, dict)
        or not isinstance(new_requires, dict)
    ):
        raise UpdaterError("unexpected local pollenlevels lock metadata movement")
    if set(old_requires) != set(new_requires):
        raise UpdaterError("local pollenlevels dependency groups changed")
    expected = {HOMEASSISTANT: homeassistant, PHACC: phacc}
    for group in old_requires:
        old_items = old_requires[group]
        new_items = new_requires[group]
        if not isinstance(old_items, list) or not isinstance(new_items, list):
            raise UpdaterError("local pollenlevels dependency metadata is invalid")
        if len(old_items) != len(new_items):
            raise UpdaterError("local pollenlevels dependency metadata changed")
        for old_item, new_item in zip(old_items, new_items, strict=True):
            if not isinstance(old_item, dict) or not isinstance(new_item, dict):
                raise UpdaterError("local pollenlevels dependency metadata is invalid")
            name = old_item.get("name")
            if name != new_item.get("name"):
                raise UpdaterError("local pollenlevels dependency metadata changed")
            if group in {"test", "release"} and name in expected:
                comparable_old = dict(old_item)
                comparable_new = dict(new_item)
                old_specifier = comparable_old.pop("specifier", None)
                new_specifier = comparable_new.pop("specifier", None)
                if comparable_old != comparable_new or not isinstance(
                    old_specifier, str
                ):
                    raise UpdaterError(
                        "unexpected local pollenlevels dependency metadata"
                    )
                if new_specifier != f"=={expected[name]}":
                    raise UpdaterError(
                        "local pollenlevels target specifier is incorrect"
                    )
            elif old_item != new_item:
                raise UpdaterError(
                    "unexpected local pollenlevels dependency metadata movement"
                )


def validate_lock_delta(
    before_text: str, after_text: str, homeassistant: str, phacc: str
) -> None:
    """Reject all lock movement except the selected harness records and pins."""
    before = tomllib.loads(before_text)
    after = tomllib.loads(after_text)
    before_top = {key: value for key, value in before.items() if key != "package"}
    after_top = {key: value for key, value in after.items() if key != "package"}
    if before_top != after_top:
        raise UpdaterError("uv.lock non-package metadata changed")
    before_groups = _package_groups(before)
    after_groups = _package_groups(after)
    if set(before_groups) != set(after_groups):
        raise UpdaterError("uv.lock package set changed")
    for name in before_groups:
        if (
            name not in {*TARGET_PACKAGES, LOCAL_PACKAGE}
            and before_groups[name] != after_groups[name]
        ):
            raise UpdaterError(f"unexpected uv.lock movement for {name}")
    _validate_target_group(after_groups, HOMEASSISTANT, homeassistant)
    _validate_target_group(after_groups, PHACC, phacc)
    _validate_local_record(
        before_groups.get(LOCAL_PACKAGE, []),
        after_groups.get(LOCAL_PACKAGE, []),
        homeassistant,
        phacc,
    )


def _read_plan(path: Path) -> BaselinePlan:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError
        value["skipped_prerelease_phacc"] = tuple(value["skipped_prerelease_phacc"])
        return BaselinePlan(**value)
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as err:
        raise UpdaterError("plan JSON is invalid") from err


def _cmd_plan(args: argparse.Namespace) -> None:
    project = tomllib.loads(args.pyproject.read_text(encoding="utf-8"))
    selection = select_stable_harness(
        fetch_pypi_metadata(HOMEASSISTANT),
        fetch_pypi_metadata(PHACC),
        lambda version: fetch_pypi_metadata(PHACC, version),
    )
    now = (
        datetime.now(UTC)
        if args.now is None
        else _parse_upload_time(args.now, "planner", "now")
    )
    plan = make_plan(
        project,
        selection,
        fetch_pypi_metadata(HOMEASSISTANT, selection.selected_homeassistant),
        fetch_pypi_metadata(PHACC, selection.selected_phacc),
        now,
    )
    sys.stdout.write(json.dumps(asdict(plan), sort_keys=True) + "\n")


def _cmd_update_pyproject(args: argparse.Namespace) -> None:
    plan = _read_plan(args.plan)
    args.pyproject.write_text(
        update_pyproject(args.pyproject.read_text(encoding="utf-8"), plan),
        encoding="utf-8",
    )


def _cmd_validate_lock(args: argparse.Namespace) -> None:
    validate_lock_delta(
        args.before.read_text(encoding="utf-8"),
        args.after.read_text(encoding="utf-8"),
        args.homeassistant,
        args.phacc,
    )


def main() -> None:
    """Run the updater's small, independently testable command interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    plan.add_argument("--now")
    plan.set_defaults(func=_cmd_plan)
    update = commands.add_parser("update-pyproject")
    update.add_argument("--plan", type=Path, required=True)
    update.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    update.set_defaults(func=_cmd_update_pyproject)
    validate = commands.add_parser("validate-lock")
    validate.add_argument("--before", type=Path, required=True)
    validate.add_argument("--after", type=Path, required=True)
    validate.add_argument("--homeassistant", required=True)
    validate.add_argument("--phacc", required=True)
    validate.set_defaults(func=_cmd_validate_lock)
    args = parser.parse_args()
    try:
        args.func(args)
    except (SelectionError, UpdaterError) as err:
        parser.error(str(err))


if __name__ == "__main__":
    main()
