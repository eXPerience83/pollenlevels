# Repository Guidelines

## Tooling
- Tooling (CI, lint, format) runs on **Python 3.14**; keep runtime compatibility with Home Assistant's floor (Python 3.13), so avoid 3.14-only syntax.
- Format code with Black (line length 88, target-version `py314`) pinned at `black==25.*`.
- Lint and sort imports with Ruff targeting `py314`, pinned at `ruff==0.14.*`, matching the configuration in `pyproject.toml`.
- Every change must pass `ruff check --fix --select I` (for import order) and `ruff check` before submission.
- Run `black .` (or the narrowest possible path) to ensure formatting.

## Release & API boundaries
- Do not change the integration version or changelog entries unless explicitly requested.
- Do not rename entities, alter `unique_id` patterns, or modify translation keys unless explicitly requested.
- Prefer minimal, focused diffs; avoid cosmetic refactors or large code moves.

## Changelog
- `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html); keep the header/preamble intact and always include an `[Unreleased]` section at the top.
- When updates are requested, add new entries under `## [Unreleased]` using standard category headings (e.g., Added, Changed, Fixed) and retain reverse-chronological ordering.
- Do not remove historical entries or alter past release notes unless explicitly instructed.

## Style and Documentation
- All code comments, README entries, and changelog notes **must be written in English**.
- Keep imports tidy—remove unused symbols and respect the Ruff isort grouping so the Home Assistant package stays first-party under `custom_components/pollenlevels`.

## Integration Architecture
- This repository hosts the custom integration **Pollen Levels for Home Assistant**, distributed through **HACS**.
- Preserve the current coordinator-driven architecture under `custom_components/pollenlevels` when extending functionality. Study the existing setup (`__init__.py`, platform files, and helpers) and mirror their async patterns, error handling, and notification logic.
- When implementing features, align with Home Assistant best practices (ConfigEntry setup, `DataUpdateCoordinator`, platform separation) and avoid introducing blocking I/O in the event loop.

## Verification
- Ensure the integration still loads within Home Assistant with the existing config flows and maintains parity with the current logic paths for entity updates and notifications.
