"""Shared lightweight Home Assistant stubs for tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def force_module(name: str, module: ModuleType) -> ModuleType:
    """Force a module into ``sys.modules`` and return it."""

    sys.modules[name] = module
    return module


def stub_custom_components_packages(*, root: Path | None = None) -> None:
    """Stub custom_components packages for local integration imports."""

    base = root or ROOT
    custom_components_pkg = ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(base / "custom_components")]
    force_module("custom_components", custom_components_pkg)

    pollenlevels_pkg = ModuleType("custom_components.pollenlevels")
    pollenlevels_pkg.__path__ = [str(base / "custom_components" / "pollenlevels")]
    force_module("custom_components.pollenlevels", pollenlevels_pkg)


def stub_config_entry_class(cls: type[Any]) -> ModuleType:
    module = ModuleType("homeassistant.config_entries")
    module.ConfigEntry = cls
    force_module("homeassistant.config_entries", module)
    return module


def stub_exceptions(**exception_types: type[Exception]) -> ModuleType:
    module = ModuleType("homeassistant.exceptions")
    for name, exc in exception_types.items():
        setattr(module, name, exc)
    force_module("homeassistant.exceptions", module)
    return module


def stub_update_coordinator_module(
    *,
    update_failed: type[Exception],
    data_update_coordinator: type[Any],
    coordinator_entity: type[Any],
) -> ModuleType:
    module = ModuleType("homeassistant.helpers.update_coordinator")
    module.UpdateFailed = update_failed
    module.DataUpdateCoordinator = data_update_coordinator
    module.CoordinatorEntity = coordinator_entity
    force_module("homeassistant.helpers.update_coordinator", module)
    return module
