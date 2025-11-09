# Repository Guidelines

## Tooling
- Target **Python 3.14** for all runtime and type-related considerations.
- Format code with **Black 25.9** (line length 88, target-version `py314`).
- Lint and sort imports with **Ruff** targeting `py314`, matching the configuration in `pyproject.toml`.
- Every change must pass `ruff check --fix --select I` (for import order) and `ruff check` before submission.
- Run `black .` (or the narrowest possible path) to ensure formatting.

## Style and Documentation
- All code comments, README entries, and changelog notes **must be written in English**.
- Keep imports tidy—remove unused symbols and respect the Ruff isort grouping so the Home Assistant package stays first-party under `custom_components/pollenlevels`.

## Integration Architecture
- This repository hosts the custom integration **Pollen Levels for Home Assistant**, distributed through **HACS**.
- Preserve the current coordinator-driven architecture under `custom_components/pollenlevels` when extending functionality. Study the existing setup (`__init__.py`, platform files, and helpers) and mirror their async patterns, error handling, and notification logic.
- When implementing features, align with Home Assistant best practices (ConfigEntry setup, `DataUpdateCoordinator`, platform separation) and avoid introducing blocking I/O in the event loop.

## Verification
- Ensure the integration still loads within Home Assistant with the existing config flows and maintains parity with the current logic paths for entity updates and notifications.
