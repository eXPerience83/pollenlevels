"""Shared lightweight Home Assistant stubs for tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


class StubClientError(Exception):
    """Minimal aiohttp ClientError stub."""


class StubClientSession:  # pragma: no cover - structure only
    """Minimal aiohttp ClientSession stub."""


class StubClientTimeout:
    """Minimal aiohttp ClientTimeout stub."""

    def __init__(self, total: float | int | None = None) -> None:
        self.total = total


def stub_aiohttp_module(
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
    install: bool = True,
) -> ModuleType:
    """Build and optionally install a lightweight ``aiohttp`` stub module."""

    module = ModuleType("aiohttp")
    module.ClientError = StubClientError
    module.ClientSession = StubClientSession
    module.ClientTimeout = StubClientTimeout
    module.ContentTypeError = ValueError
    if not install:
        return module
    return _set_module("aiohttp", module, monkeypatch=monkeypatch)


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


def stub_homeassistant_package(
    *,
    as_package: bool = True,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> ModuleType:
    """Install a fresh ``homeassistant`` base module for local stubs."""

    module = ModuleType("homeassistant")
    if as_package:
        module.__path__ = []
    _set_module("homeassistant", module, monkeypatch=monkeypatch)
    return module


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


class StubLocationSelectorConfig:
    """Minimal location selector config stub."""

    def __init__(self, *, radius: bool | None = None) -> None:
        self.radius = radius


class StubLocationSelector:
    """Minimal location selector stub."""

    def __init__(self, config: StubLocationSelectorConfig) -> None:
        self.config = config


class StubNumberSelectorConfig:
    """Minimal number selector config stub."""

    def __init__(
        self,
        *,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        mode: str | None = None,
        unit_of_measurement: str | None = None,
    ) -> None:
        self.min = min
        self.max = max
        self.step = step
        self.mode = mode
        self.unit_of_measurement = unit_of_measurement


class StubNumberSelectorMode:
    """Minimal number selector mode stub."""

    BOX = "BOX"


class StubNumberSelector:
    """Minimal number selector stub."""

    def __init__(self, config: StubNumberSelectorConfig) -> None:
        self.config = config


class StubTextSelectorConfig:
    """Minimal text selector config stub."""

    def __init__(self, *, type: str | None = None) -> None:  # noqa: A003
        self.type = type


class StubTextSelectorType:
    """Minimal text selector type stub."""

    TEXT = "TEXT"
    PASSWORD = "PASSWORD"


class StubTextSelector:
    """Minimal text selector stub."""

    def __init__(self, config: StubTextSelectorConfig) -> None:
        self.config = config


class StubSelectSelectorConfig:
    """Minimal select selector config stub."""

    def __init__(self, *, mode: str | None = None, options: list | None = None) -> None:
        self.mode = mode
        self.options = options


class StubSelectSelectorMode:
    """Minimal select selector mode stub."""

    DROPDOWN = "DROPDOWN"


class StubSelectSelector:
    """Minimal select selector stub."""

    def __init__(self, config: StubSelectSelectorConfig) -> None:
        self.config = config


def stub_selector_module(
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
    include_section: bool = False,
) -> ModuleType:
    """Install a lightweight ``homeassistant.helpers.selector`` stub module."""

    module = ModuleType("homeassistant.helpers.selector")
    module.LocationSelector = StubLocationSelector
    module.LocationSelectorConfig = StubLocationSelectorConfig
    module.NumberSelector = StubNumberSelector
    module.NumberSelectorConfig = StubNumberSelectorConfig
    module.NumberSelectorMode = StubNumberSelectorMode
    module.TextSelector = StubTextSelector
    module.TextSelectorConfig = StubTextSelectorConfig
    module.TextSelectorType = StubTextSelectorType
    module.SelectSelector = StubSelectSelector
    module.SelectSelectorConfig = StubSelectSelectorConfig
    module.SelectSelectorMode = StubSelectSelectorMode
    if include_section:
        module.section = lambda key: key
    return _set_module(
        "homeassistant.helpers.selector", module, monkeypatch=monkeypatch
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
        for name in list(sys.modules)
        if name == package_name or name.startswith(f"{package_name}.")
    ]
    for name in module_names:
        if monkeypatch is not None:
            monkeypatch.delitem(sys.modules, name, raising=False)
        else:
            sys.modules.pop(name, None)
