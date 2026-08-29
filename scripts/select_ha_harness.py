"""Select the newest compatible stable Home Assistant test harness pair."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

PYPI_URL = "https://pypi.org/pypi/{package}{version}/json"
USER_AGENT = "pollenlevels-ha-harness-selector"


class SelectionError(ValueError):
    """Raised when PyPI metadata cannot safely produce a stable harness pair."""


@dataclass(frozen=True)
class HarnessSelection:
    """The stable Home Assistant harness versions selected from PyPI metadata."""

    latest_homeassistant: str
    latest_phacc: str
    selected_phacc: str
    selected_homeassistant: str
    skipped_prerelease_phacc: tuple[str, ...]


def _stable_releases(
    metadata: Mapping[str, object], package: str
) -> list[tuple[Version, str]]:
    """Return non-yanked, stable releases from one PyPI project response."""
    releases = metadata.get("releases")
    if not isinstance(releases, Mapping):
        raise SelectionError(f"PyPI metadata for {package} has no releases mapping")

    stable_releases: list[tuple[Version, str]] = []
    for release, artifacts in releases.items():
        if not isinstance(release, str) or not isinstance(artifacts, list):
            raise SelectionError(
                f"PyPI metadata for {package} has an invalid release entry"
            )
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                raise SelectionError(
                    f"PyPI metadata for {package} has an invalid artifact"
                )
            if not isinstance(artifact.get("yanked"), bool):
                raise SelectionError(
                    f"PyPI metadata for {package} has an invalid artifact yanked value"
                )
        try:
            version = Version(release)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        if any(artifact["yanked"] is False for artifact in artifacts):
            stable_releases.append((version, release))
    return stable_releases


def latest_stable_release(metadata: Mapping[str, object], package: str) -> str:
    """Return the newest stable non-yanked release from PyPI project metadata."""
    stable_releases = _stable_releases(metadata, package)
    if not stable_releases:
        raise SelectionError(f"PyPI returned no stable non-yanked {package} releases")
    return max(stable_releases)[1]


def exact_homeassistant_requirement(requires_dist: object) -> str:
    """Return PHACC's exact unconditional Home Assistant requirement."""
    if not isinstance(requires_dist, Sequence) or isinstance(requires_dist, str):
        raise SelectionError("PHACC metadata has no requires_dist list")

    requirements: list[Requirement] = []
    for requirement_text in requires_dist:
        if not isinstance(requirement_text, str):
            raise SelectionError("PHACC metadata has an invalid dependency requirement")
        try:
            requirement = Requirement(requirement_text)
        except InvalidRequirement as err:
            raise SelectionError(
                "PHACC metadata has an invalid dependency requirement"
            ) from err
        if canonicalize_name(requirement.name) == "homeassistant":
            requirements.append(requirement)

    if len(requirements) != 1:
        raise SelectionError(
            "PHACC must declare exactly one Home Assistant requirement"
        )
    requirement = requirements[0]
    specifiers = list(requirement.specifier)
    if (
        requirement.extras
        or requirement.marker is not None
        or len(specifiers) != 1
        or specifiers[0].operator != "=="
        or specifiers[0].version.endswith(".*")
    ):
        raise SelectionError(
            "PHACC Home Assistant requirement must be one exact version"
        )
    return specifiers[0].version


def select_stable_harness(
    homeassistant_metadata: Mapping[str, object],
    phacc_metadata: Mapping[str, object],
    phacc_release_metadata: Callable[[str], Mapping[str, object]],
) -> HarnessSelection:
    """Select the newest PHACC release that targets a usable stable HA release."""
    latest_homeassistant = latest_stable_release(
        homeassistant_metadata, "Home Assistant"
    )
    latest_phacc = latest_stable_release(
        phacc_metadata, "pytest-homeassistant-custom-component"
    )
    stable_homeassistant = {
        release
        for _, release in _stable_releases(homeassistant_metadata, "Home Assistant")
    }
    phacc_releases = sorted(
        _stable_releases(phacc_metadata, "pytest-homeassistant-custom-component"),
        reverse=True,
    )
    skipped_prerelease_phacc: list[str] = []

    for _, phacc_version in phacc_releases:
        metadata = phacc_release_metadata(phacc_version)
        info = metadata.get("info")
        if not isinstance(info, Mapping):
            raise SelectionError(f"PHACC {phacc_version} metadata has no info mapping")
        homeassistant_version = exact_homeassistant_requirement(
            info.get("requires_dist")
        )
        try:
            parsed_homeassistant = Version(homeassistant_version)
        except InvalidVersion as err:
            raise SelectionError(
                f"PHACC {phacc_version} targets an invalid Home Assistant version"
            ) from err
        if parsed_homeassistant.is_prerelease or parsed_homeassistant.is_devrelease:
            skipped_prerelease_phacc.append(phacc_version)
            continue
        if homeassistant_version not in stable_homeassistant:
            raise SelectionError(
                f"PHACC {phacc_version} targets unavailable or yanked Home Assistant "
                f"{homeassistant_version}"
            )
        return HarnessSelection(
            latest_homeassistant=latest_homeassistant,
            latest_phacc=latest_phacc,
            selected_phacc=phacc_version,
            selected_homeassistant=homeassistant_version,
            skipped_prerelease_phacc=tuple(skipped_prerelease_phacc),
        )

    raise SelectionError("PyPI returned no eligible stable PHACC/Home Assistant pair")


def fetch_pypi_metadata(
    package: str, version: str | None = None
) -> Mapping[str, object]:
    """Fetch one PyPI JSON response with bounded retries and a timeout."""
    version_path = f"/{version}" if version is not None else ""
    url = PYPI_URL.format(package=package, version=version_path)
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=15) as response:
                payload: Any = json.load(response)
            if not isinstance(payload, Mapping):
                raise SelectionError(f"PyPI metadata for {package} is not a mapping")
            return payload
        except (
            OSError,
            TimeoutError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as err:
            if attempt == 3:
                raise SelectionError(
                    f"Unable to fetch PyPI metadata for {package}"
                ) from err
            time.sleep(5)
    raise AssertionError("unreachable")


def main() -> None:
    """Print the selected stable harness pair as JSON for CI consumers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    homeassistant_metadata = fetch_pypi_metadata("homeassistant")
    phacc_metadata = fetch_pypi_metadata("pytest-homeassistant-custom-component")
    selection = select_stable_harness(
        homeassistant_metadata,
        phacc_metadata,
        lambda version: fetch_pypi_metadata(
            "pytest-homeassistant-custom-component", version
        ),
    )
    sys.stdout.write(json.dumps(asdict(selection), sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
