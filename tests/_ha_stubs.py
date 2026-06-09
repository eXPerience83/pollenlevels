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


def force_module(
    name: str, module: ModuleType, *, monkeypatch: pytest.MonkeyPatch | None = None
) -> ModuleType:
    """Install ``module`` into ``sys.modules`` and return it.

    Prefer passing ``monkeypatch`` from fixtures so pytest restores any previous
    module after the test. Omitting it intentionally performs a direct install.
    """

    if monkeypatch is not None:
        monkeypatch.setitem(sys.modules, name, module)
        return module
    sys.modules[name] = module
    return module


def _set_module(
    name: str, module: ModuleType, *, monkeypatch: pytest.MonkeyPatch | None = None
) -> ModuleType:
    # Intentionally replace target modules to keep stubs deterministic and avoid
    # import-order coupling across suites. Fixtures can pass monkeypatch so
    # teardown restores previous state automatically.
    return force_module(name, module, monkeypatch=monkeypatch)


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


def stub_util_dt_module(*, monkeypatch: pytest.MonkeyPatch | None = None) -> ModuleType:
    """Install lightweight ``homeassistant.util`` and ``homeassistant.util.dt`` stubs."""

    util_mod = ModuleType("homeassistant.util")
    dt_mod = ModuleType("homeassistant.util.dt")

    def _stub_utcnow():
        from datetime import UTC, datetime

        return datetime.now(UTC)

    def _stub_parse_http_date(value: str | None):  # pragma: no cover - stub only
        from datetime import UTC, datetime
        from email.utils import parsedate_to_datetime

        try:
            parsed = parsedate_to_datetime(value) if value is not None else None
        except TypeError, ValueError, IndexError, OverflowError:
            return None

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)

        if isinstance(parsed, datetime):
            return parsed

        return None

    dt_mod.utcnow = _stub_utcnow
    dt_mod.parse_http_date = _stub_parse_http_date
    util_mod.dt = dt_mod
    _set_module("homeassistant.util", util_mod, monkeypatch=monkeypatch)
    return _set_module("homeassistant.util.dt", dt_mod, monkeypatch=monkeypatch)


def stub_config_entry_class(
    cls: type[object], *, monkeypatch: pytest.MonkeyPatch | None = None
) -> ModuleType:
    """Install a minimal ``homeassistant.config_entries`` module."""

    module = ModuleType("homeassistant.config_entries")
    module.ConfigEntry = cls
    _set_module("homeassistant.config_entries", module, monkeypatch=monkeypatch)
    return module


def stub_exceptions(
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
    **exception_types: type[Exception],
) -> ModuleType:
    """Install a minimal ``homeassistant.exceptions`` module."""

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
    """Install a minimal update coordinator module with caller-provided types."""

    module = ModuleType("homeassistant.helpers.update_coordinator")
    module.UpdateFailed = update_failed
    module.DataUpdateCoordinator = data_update_coordinator
    module.CoordinatorEntity = coordinator_entity
    _set_module(
        "homeassistant.helpers.update_coordinator", module, monkeypatch=monkeypatch
    )
    return module


class StubIssueRegistry:
    """Minimal issue registry stub for inspecting Repair calls."""

    def __init__(self):
        self.issues: dict[str, dict] = {}
        self.deleted: list[tuple[object, str, str]] = []

    def async_create_issue(self, hass, domain, issue_id, **kwargs):
        self.issues[issue_id] = {"hass": hass, "domain": domain, **kwargs}

    def async_delete_issue(self, hass, domain, issue_id):
        self.deleted.append((hass, domain, issue_id))
        self.issues.pop(issue_id, None)


class StubIssueSeverity:
    ERROR = "error"


def stub_issue_registry_module(
    *, monkeypatch: pytest.MonkeyPatch | None = None
) -> ModuleType:
    """Install a lightweight homeassistant.helpers.issue_registry stub."""
    module = ModuleType("homeassistant.helpers.issue_registry")
    registry = StubIssueRegistry()
    module.registry = registry
    module.async_create_issue = registry.async_create_issue
    module.async_delete_issue = registry.async_delete_issue
    module.IssueSeverity = StubIssueSeverity
    return _set_module(
        "homeassistant.helpers.issue_registry", module, monkeypatch=monkeypatch
    )


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
