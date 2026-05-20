# Repository Guidelines

## Tooling
- Tooling (CI, lint, format) runs on **Python 3.14**. The `pyproject.toml` targets packaging/tooling and also pins `requires-python = ">=3.14"`. All code under `custom_components/pollenlevels/` targets Python 3.14+, matching the Home Assistant 2026.3 runtime baseline.
- Format code with Black (line length 88, target-version `py314`) pinned at `black==25.*`.
- Lint and sort imports with Ruff targeting `py314`, pinned at `ruff==0.14.*`, matching the configuration in `pyproject.toml`.
- Every change must pass `ruff check --fix --select I` (for import order) and `ruff check` before submission.
- Run `black .` (or the narrowest possible path) to ensure formatting.

## Release & API boundaries
- Do not change the integration version or changelog entries unless explicitly requested.
- Do not rename entities, alter `unique_id` patterns, or modify translation keys unless explicitly requested.
- Prefer minimal, focused diffs; avoid cosmetic refactors or large code moves.

## Test and Defensive Coding Policy
- Do not add defensive code or tests only because an arbitrary JSON shape could theoretically exist.
- Add defensive handling or regression tests when they:
  - protect public behavior or user-facing outputs,
  - cover a real bug or previously observed failure,
  - cover a new branch introduced by the change,
  - prevent a likely exception from partially malformed upstream data,
  - or document an intentional compatibility or migration behavior.
- Prefer small, focused tests over large synthetic fixtures.
- Avoid duplicating malformed-payload test cases when the same behavior is already covered by a smaller helper-level test.
- Keep defensive parsing proportional to the upstream API contract; do not add broad schema validators unless the integration has observed real instability in that payload area.
- When a review suggests hardening for a highly unlikely upstream shape, first decide whether the scenario is realistic enough to justify code and test complexity. If not, document the reasoning in the PR instead of expanding the code.

## Changelog / `CHANGELOG.md`
- This section is the single source of truth for the changelog style. Ignore external style guides when they conflict with these rules.
- Do NOT add any new boilerplate, intro text or `## [Unreleased]` section automatically. If such sections already exist, leave them and only edit their content when explicitly requested.
- Version headings must use the pattern `## [version] - YYYY-MM-DD` (ASCII hyphen) and releases must stay in reverse chronological order. Use SemVer identifiers such as `1.8.2`, `1.8.2-rc1`, `1.8.1-alpha1`.
- Inside each version, use only these headings: `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, `### Security`. Prefer `Changed` for documentation-only updates.
- For breaking changes, keep one of the allowed section headings above and
  prefix the bullet with `**Breaking change:**`; do not add a separate
  `### Breaking Changes` heading.
- Each change must be a `- ` bullet. Wrap long bullets around 80–100 characters with indented continuation lines; do NOT insert blank lines inside a bullet and avoid `<br>` or trailing double spaces.
- Keep diffs minimal: never reflow or rewrap unrelated text, and never rename existing headings unless they clearly violate these rules.
- If comparison links exist at the bottom of the changelog, keep the existing style and only extend it for new versions of this repository.

## Style and Documentation
- All code comments, README entries, and changelog notes **must be written in English**.
- Keep imports tidy—remove unused symbols and respect the Ruff isort grouping so the Home Assistant package stays first-party under `custom_components/pollenlevels`.
- Translation source of truth is `custom_components/pollenlevels/translations/en.json`.
- Keep all other locale files synchronized with that keyset.
- Do not add or rely on a `strings.json` file, and do not introduce `%key:` translation references in this custom repository.


## Integration Architecture
- This repository hosts the custom integration **Pollen Levels for Home Assistant**, distributed through **HACS**.
- Preserve the current coordinator-driven architecture under `custom_components/pollenlevels` when extending functionality. Study the existing setup (`__init__.py`, platform files, and helpers) and mirror their async patterns, error handling, and notification logic.
- When implementing features, align with Home Assistant best practices (ConfigEntry setup, `DataUpdateCoordinator`, platform separation) and avoid introducing blocking I/O in the event loop.

## Verification
- Ensure the integration still loads within Home Assistant with the existing config flows and maintains parity with the current logic paths for entity updates and notifications.
