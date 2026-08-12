# Repository Guidelines

These instructions apply to the entire repository unless a more specific nested
`AGENTS.md` is added later.

## Sources of truth and scope

- Treat the current repository code, tests, configuration, and workflows as the
  source of truth. Old PR descriptions, release notes, prompts, and historical
  architecture notes can be stale.
- Before changing runtime architecture, migration, entity identity, diagnostics,
  translations, or release behavior, inspect the current implementation and the
  focused regression tests that protect it.
- If a requested change conflicts with current code or tests, report the
  discrepancy before expanding the scope.
- Keep one focused objective per PR. Do not mix runtime, migration, release,
  documentation, dependency/tooling, and cosmetic refactors unless they are
  inseparable for correctness.
- Prefer minimal diffs. Do not rename, reorder, move, or reformat unrelated code.

## Project structure

Pollen Levels is a Home Assistant custom integration distributed through HACS.

- Integration code lives in `custom_components/pollenlevels/`.
- Home Assistant integration-surface tests and focused unit tests live in
  `tests/`; reusable API payloads belong in `tests/fixtures/`.
- Release/validation helpers live in `scripts/`.
- GitHub Actions workflows live in `.github/workflows/`.
- The translation source of truth is
  `custom_components/pollenlevels/translations/en.json`.

Keep platform-specific behavior in its existing modules and preserve the
coordinator-driven async design.

## v3 architecture invariants

The current storage/runtime model is deliberate and must not be flattened back
into the legacy one-entry-per-location design.

- One parent config entry represents one Google Pollen API key.
- Each configured location is a Home Assistant config subentry of type
  `location` under that parent.
- The API key remains parent-scoped. Shared options such as update interval and
  language remain parent-scoped.
- Location title/name, latitude, longitude, and any migration-only legacy
  identity belong to the location subentry.
- Runtime state is per location: each loaded location has its own coordinator.
- Sensors and the `Update now` button are location-scoped and must be registered
  against the correct `config_subentry_id`.
- Setup, unload, and reload behavior must keep both the `sensor` and `button`
  platforms consistent with the configured subentries.
- A local setup failure must not unnecessarily prevent healthy sibling locations
  under the same parent from operating.
- Use supported public Home Assistant APIs. Do not invent private hooks to work
  around config-subentry lifecycle behavior.

## Migration and identity safety

Migration and registry identity are high-risk compatibility surfaces.

- Do not modify v2-to-v3 migration logic unless the task fixes a demonstrated
  migration bug or explicitly requires a migration change.
- Preserve existing `entity_id`, `unique_id`, device associations, dashboards,
  automations, and Recorder history across migration and reloads.
- Do not change legacy entry IDs, location identity semantics, device
  identifiers, `coordinator_identity_id()` / `coordinator_device_id()` behavior,
  or registry reassociation logic without focused regression coverage.
- Never delete or recreate registry objects merely to make a migration simpler
  when they can be safely preserved or reassociated.
- Migration changes require Home Assistant harness coverage for the affected
  scenarios. At minimum consider: one legacy location; multiple locations
  sharing one API key; locations using different API keys; merging a residual
  legacy entry into an existing clean v3 parent; registry reassociation; and
  retry/idempotency behavior.
- Treat migration failures conservatively. If identity cannot be moved safely,
  preserving the legacy state and allowing a retry is preferable to silent
  history or registry loss.
- User-facing migration/release documentation must continue to make backup and
  downgrade implications explicit when relevant.

## Runtime lifecycle and manual refresh

- `pollenlevels.force_update` is a global service. It may refresh loaded active
  locations, but it must not refresh runtime coordinators whose location
  subentry has already been removed.
- The per-location `Update now` button refreshes only its own coordinator.
- Home Assistant may clean registry associations before in-memory runtime state
  has been reloaded after a subentry deletion. Treat that temporary stale state
  as an expected lifecycle condition rather than forcing unsupported hooks.
- Sensor and button setup must skip stale runtime locations consistently.
- Keep parent-level API requests serialized through the existing
  `GooglePollenApiClient`; do not bypass its request lock, quota cooldown, retry,
  or redaction behavior with ad-hoc HTTP calls.
- Use Home Assistant's shared aiohttp session when creating the client. Keep
  network I/O asynchronous, bounded by timeouts, and off the event-loop blocking
  path.
- Preserve cancellation semantics. Do not swallow `asyncio.CancelledError`.

## Forecast and entity contracts

- The Google Pollen forecast horizon is currently fixed to five days. Do not
  reintroduce obsolete configurable forecast-day or legacy per-day `_d1` / `_d2`
  entity modes as an unrelated change.
- Forecast information stays on the base entities. Preserve the public forecast
  attributes and semantics, including `forecast`, `tomorrow_*`, `d2_*`, `trend`,
  and `expected_peak`, unless the task explicitly changes that contract.
- Do not add/remove forecast entities, alter offsets, change state types, or
  change stable unique-ID patterns as collateral cleanup.
- Do not impose a hardcoded universal plant catalogue or a strict plant-code
  whitelist. The API can expose region-specific plant codes, and the current
  runtime must remain tolerant of supported upstream codes.
- Keep defensive parsing proportional to the upstream API contract and observed
  behavior. Do not add broad schema machinery for purely hypothetical payloads.

## Diagnostics, privacy, and logging

Privacy and support diagnostics are part of the public maintenance contract.

- API keys must always be redacted from diagnostics, logs, exceptions, Repairs,
  test fixtures, and PR/issue text.
- Never log complete credential-bearing request URLs or precise coordinates.
- Diagnostics may expose only deliberately reduced location information; current
  coordinate examples are rounded to one decimal place.
- Preserve `registry_summary` and `runtime_summary` unless an explicit diagnostic
  contract change is requested.
- `runtime_summary.stale_location_count` and stale location IDs exist to explain
  temporary runtime state after subentry deletion; do not remove or repurpose
  them casually.
- Preserve failed-location diagnostics and their redaction semantics.
- `async_get_config_entry_diagnostics()` must not perform network I/O.

## Tooling and coding style

Use the repository's current locked toolchain rather than remembered versions
from older releases.

- Use the exact Python patch from `.python-version` for local/CI tooling. The
  project runtime floor remains `requires-python = ">=3.14"` unless a dedicated
  compatibility change updates it.
- Use the exact uv version declared in `[tool.uv].required-version`.
- Ruff is the single linter, import sorter, and formatter. Do not add Black back
  unless a dedicated tooling change explicitly reverses that decision.
- Ruff targets Python 3.14, line length 88, double quotes, and stable formatting
  with preview disabled; `pyproject.toml` is authoritative.
- Use modern Python typing: PEP 604 unions and built-in generics where
  applicable. Prefer `collections.abc` for runtime collection protocols.
- Keep imports Ruff/isort-clean. `custom_components.pollenlevels` is first-party.
- All code comments and docstrings must be in English.
- Repository-facing technical documentation, README text, FAQ text, PR text, and
  CHANGELOG entries should be in English unless a task explicitly requests
  another language.
- Do not use `print()`. Use `_LOGGER` without exposing secrets or precise
  location data.

## Translation and public API stability

- `custom_components/pollenlevels/translations/en.json` is the translation source
  of truth. Keep every bundled locale synchronized with its keyset.
- Do not add or rely on `strings.json` in this custom integration.
- Do not introduce `%key:` translation references.
- Do not rename existing translation keys, services/actions, entity IDs, unique
  IDs, device identifiers, or other public keys without an explicit requirement
  and appropriate compatibility tests.
- Keep `services.yaml` and translation/service behavior synchronized when the
  public service contract changes.

## Testing and defensive coding policy

- Write pytest tests named `test_<behavior>` in the matching `tests/test_*.py`
  module.
- Prefer `pytest-homeassistant-custom-component` for Home Assistant integration
  surfaces such as config/subentry flows, setup/unload/reload, platform entity
  registration, services, diagnostics, Repairs, registries, and migration.
- Keep lightweight unit tests for pure parsing, API-client behavior, redaction
  helpers, malformed payload edges, and targeted failure injection.
- Add defensive handling or regression tests when they protect public behavior,
  cover a real or observed failure, cover a new branch, prevent a likely
  exception from partially malformed upstream data, or document intentional
  compatibility/migration behavior.
- Do not add defensive code or tests solely because an arbitrary JSON shape can
  be imagined. Prefer the smallest fixture that demonstrates the contract.
- When touching subentry lifecycle or manual refresh behavior, cover active vs
  stale locations, correct subentry association, sibling isolation, and
  unload/reload behavior.
- When touching diagnostics, cover redaction and registry/runtime summaries.
- When touching identity or migration, use focused Home Assistant harness tests
  and verify registry associations explicitly.

## Build, test, and validation commands

Use the locked commands reflected by the current repository configuration:

- `uv lock --check`
- `uv sync --locked --only-group lint`
- `uv run --locked --no-sync ruff check .`
- `uv run --locked --no-sync ruff format --check .`
- `uv sync --locked --only-group test`
- `PYTHONPATH=. uv run --locked --no-sync python -m pytest -q`

Run the narrowest relevant tests while developing, then the complete required
suite before merge. Use `python -m compileall` as required by the current CI or
release workflow for the files in scope.

Hosted validation currently includes the locked Lint, Tests, Package Test,
Workflow Security, hassfest, HACS validation, and CodeQL gates where configured.
The scheduled latest-Home-Assistant compatibility canary is intentionally
fresh-resolving and advisory; do not treat it as a replacement for locked merge
or Release validation.

## Commit, PR, and release discipline

- Use focused Conventional Commit subjects, for example
  `fix(client): honor quota cooldown` or `test: cover subentry removal`.
- PRs should explain the behavior change, scope, risks, and validation performed;
  link the owning issue when one exists.
- Do not create tags or GitHub releases from a normal implementation PR.
- Do not change `custom_components/pollenlevels/manifest.json`, the project
  version in `pyproject.toml`, or add a release CHANGELOG entry unless the task is
  explicitly a release/version PR.
- Keep release-only PRs limited to release metadata and the exact release notes
  unless a separate fix is required first.
- Do not combine an unrelated runtime fix with migration, tooling, broad docs,
  dependency upgrades, or release preparation.

## Changelog / `CHANGELOG.md`

This section is the repository source of truth for changelog style.

- Do not add boilerplate, intro text, or an `## [Unreleased]` section
  automatically. If such a section already exists, leave it unless the task
  explicitly changes it.
- Version headings use `## [version] - YYYY-MM-DD` with an ASCII hyphen and stay
  in reverse chronological order. Use SemVer identifiers such as `3.0.2`,
  `3.0.0-rc1`, or `3.0.0-alpha1` according to the repository's established
  release naming.
- Inside each version use only: `### Added`, `### Changed`, `### Deprecated`,
  `### Removed`, `### Fixed`, and `### Security`.
- For breaking changes, keep one of those headings and prefix the bullet with
  `**Breaking change:**`; do not add a separate `### Breaking Changes` heading.
- Each change is a `- ` bullet. Wrap long bullets around 80-100 characters with
  indented continuation lines; do not insert blank lines inside a bullet or use
  `<br>`/trailing double spaces.
- Keep diffs minimal: never reflow unrelated historical entries or rename
  existing headings unless they clearly violate these rules.
- If comparison links exist at the bottom of the changelog, preserve the
  existing style and extend it only when required by a release task.
