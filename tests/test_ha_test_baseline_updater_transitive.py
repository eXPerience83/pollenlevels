"""Regression tests for target-derived Home Assistant baseline lock movement."""

from __future__ import annotations

import pytest

from scripts.ha_test_baseline_updater import UpdaterError, validate_lock_delta


def _package(name: str, version: str, *dependencies: str) -> str:
    dependency_block = ""
    if dependencies:
        items = ", ".join(f'{{ name = "{dependency}" }}' for dependency in dependencies)
        dependency_block = f"\ndependencies = [{items}]"
    return f'''[[package]]
name = "{name}"
version = "{version}"
source = {{ registry = "https://pypi.org/simple" }}{dependency_block}
'''


def _lock(
    *,
    ha: str,
    phacc: str,
    ha_dependencies: tuple[str, ...],
    phacc_dependencies: tuple[str, ...],
    packages: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> str:
    records = [
        _package("homeassistant", ha, *ha_dependencies),
        _package("pytest-homeassistant-custom-component", phacc, *phacc_dependencies),
    ]
    records.extend(
        _package(name, version, *dependencies)
        for name, version, dependencies in packages
    )
    records.append(
        f'''[[package]]
name = "pollenlevels"
version = "4.0.3"
source = {{ virtual = "." }}

[package.dev-dependencies]
release = [
    {{ name = "homeassistant" }},
    {{ name = "pytest-homeassistant-custom-component" }},
]
test = [
    {{ name = "homeassistant" }},
    {{ name = "pytest-homeassistant-custom-component" }},
]

[package.metadata]

[package.metadata.requires-dev]
release = [
    {{ name = "homeassistant", specifier = "=={ha}" }},
    {{ name = "pytest-homeassistant-custom-component", specifier = "=={phacc}" }},
]
test = [
    {{ name = "homeassistant", specifier = "=={ha}" }},
    {{ name = "pytest-homeassistant-custom-component", specifier = "=={phacc}" }},
]
'''
    )
    header = '''version = 1
revision = 1
requires-python = ">=3.14"

'''
    return header + "\n".join(records)


def _monthly_pair() -> tuple[str, str]:
    before = _lock(
        ha="2026.8.3",
        phacc="0.13.357",
        ha_dependencies=("shared", "removed"),
        phacc_dependencies=("homeassistant", "coverage"),
        packages=(
            ("shared", "1.0", ("nested",)),
            ("nested", "1.0", ()),
            ("removed", "1.0", ()),
            ("coverage", "7.15.2", ()),
            ("unrelated", "1.0", ()),
        ),
    )
    after = _lock(
        ha="2026.9.3",
        phacc="0.13.366",
        ha_dependencies=("shared", "added"),
        phacc_dependencies=("homeassistant", "coverage"),
        packages=(
            ("shared", "2.0", ("nested",)),
            ("nested", "2.0", ()),
            ("added", "1.0", ()),
            ("coverage", "7.15.4", ()),
            ("unrelated", "1.0", ()),
        ),
    )
    return before, after


def test_target_derived_monthly_graph_movement_passes() -> None:
    """Target descendants may update, appear, disappear, and change recursively."""
    before, after = _monthly_pair()

    validate_lock_delta(before, after, "2026.9.3", "0.13.366")


def test_unrelated_package_addition_still_fails() -> None:
    """An unreferenced package addition remains unexplained lock churn."""
    before, after = _monthly_pair()
    after += "\n" + _package("unrelated-added", "1.0")

    with pytest.raises(UpdaterError, match="package set changed"):
        validate_lock_delta(before, after, "2026.9.3", "0.13.366")


def test_unrelated_existing_package_movement_still_fails() -> None:
    """Existing packages outside the target graph must remain byte-for-byte stable."""
    before, after = _monthly_pair()
    after = after.replace(
        'name = "unrelated"\nversion = "1.0"',
        'name = "unrelated"\nversion = "2.0"',
        1,
    )

    with pytest.raises(UpdaterError, match="unrelated"):
        validate_lock_delta(before, after, "2026.9.3", "0.13.366")
