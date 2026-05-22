"""Shared lightweight Home Assistant stubs for tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def force_module(name: str, module: ModuleType) -> ModuleType:
    """Force a module into ``sys.modules`` and return it."""

    sys.modules[name] = module
    return module


def _set_module(
    name: str, module: ModuleType, *, monkeypatch: pytest.MonkeyPatch | None = None
) -> ModuleType:
    # Intentionally replace target modules to keep stubs deterministic and avoid
    # import-order coupling across suites. Fixtures can pass monkeypatch so
    # teardown restores previous state automatically.
    if monkeypatch is not None:
        monkeypatch.setitem(sys.modules, name, module)
        return module
    return force_module(name, module)


def stub_custom_components_packages(
    *, root: Path | None = None, monkeypatch: pytest.MonkeyPatch | None = None
) -> None:
    """Stub custom_components packages for local integration imports."""

    base = root or ROOT
    custom_components_pkg = ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(base / "custom_components")]
    _set_module("custom_components", custom_components_pkg, monkeypatch=monkeypatch)

    pollenlevels_pkg = ModuleType("custom_components.pollenlevels")
    pollenlevels_pkg.__path__ = [str(base / "custom_components" / "pollenlevels")]
    _set_module(
        "custom_components.pollenlevels",
        pollenlevels_pkg,
        monkeypatch=monkeypatch,
    )


def stub_config_entry_class(
    cls: type[object], *, monkeypatch: pytest.MonkeyPatch | None = None
) -> ModuleType:
    module = ModuleType("homeassistant.config_entries")
    module.ConfigEntry = cls
    _set_module("homeassistant.config_entries", module, monkeypatch=monkeypatch)
    return module


def stub_exceptions(
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
    **exception_types: type[Exception],
) -> ModuleType:
    module = ModuleType("homeassistant.exceptions")
    for name, exc in exception_types.items():
        setattr(module, name, exc)
    _set_module("homeassistant.exceptions", module, monkeypatch=monkeypatch)
    return module


def stub_update_coordinator_module(
    *,
    update_failed: type[Exception],
    data_update_coordinator: type[object],
    coordinator_entity: type[object],
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> ModuleType:
    module = ModuleType("homeassistant.helpers.update_coordinator")
    module.UpdateFailed = update_failed
    module.DataUpdateCoordinator = data_update_coordinator
    module.CoordinatorEntity = coordinator_entity
    _set_module(
        "homeassistant.helpers.update_coordinator", module, monkeypatch=monkeypatch
    )
    return module


def clear_integration_modules(
    package_name: str = "custom_components.pollenlevels",
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> None:
    """Remove cached integration modules so tests import them with local stubs."""

    module_names = [
        name
        for name in sys.modules
        if name == package_name or name.startswith(f"{package_name}.")
    ]
    for name in module_names:
        if monkeypatch is not None:
            monkeypatch.delitem(sys.modules, name, raising=False)
        else:
            sys.modules.pop(name, None)
