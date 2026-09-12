# Contributing

## Home Assistant upstream alignment and project direction

Pollen Levels is maintained in this repository as a Home Assistant custom
integration distributed through HACS. The current Home Assistant developer
documentation and Integration Quality Scale remain useful upstream quality
references when they improve supported HACS behavior:

- [Contributing an integration to Core](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/)
- [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
- [Full config-flow test coverage](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-flow-test-coverage/)
- [Above 95% test coverage](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/test-coverage/)

This repository is **not** a staging tree for a future Home Assistant Core
submission. If a future Google Pollen integration for Home Assistant Core is
pursued, it will be designed in a separate clean project/repository against the
then-current upstream requirements. Knowledge, evidence, behavioral lessons, and
useful test ideas from Pollen Levels may be reused there, but its code, storage
architecture, IDs, migrations, entity contracts, helper layout, or HACS
compatibility should not be assumed to transfer directly.

For this repository:

- `config_flow.py` must reach literal 100% statement coverage, including error
  recovery and all supported user, reauth, reconfigure, subentry, and options
  behavior;
- every non-migration integration module must be strictly above 95% statement
  coverage, measured per module rather than only as a repository-wide total;
- `migration.py` is measured and reported but is not subject to the percentage
  coverage gate; migration tests should be driven by demonstrated behavior and
  identity risk rather than percentage padding;
- tests should protect real behavior, identity, privacy, lifecycle, retry, and
  failure semantics rather than merely execute lines to improve a percentage;
- code proven unreachable on supported Home Assistant should be reviewed for a
  dedicated cleanup/refactor rather than covered by artificial tests or silently
  excluded from the target;
- supported public Home Assistant APIs, async patterns, typing conventions, and
  Home Assistant harness tests are preferred whenever they improve the supported
  HACS integration.

Do not reshape the current HACS runtime architecture, migration behavior, IDs,
compatibility helpers, translations, packaging, public contracts, or API-client
layout solely to satisfy hypothetical future Core submission requirements. Such
changes require an independent benefit or requirement for Pollen Levels itself.
Core-specific findings and upstream conventions remain useful learning material,
but they do not create backlog work for this repository unless a focused issue
explicitly reframes them as HACS work.

## Development environment

- Home Assistant 2026.5 requires Python >=3.14.2. Use the exact patch in
  `.python-version` for local development and CI parity. The project metadata
  remains `requires-python = ">=3.14"`, but the locked Home Assistant test
  environment is constrained to Python 3.14.2+; do not infer runtime support for
  earlier Python 3.14 patch releases.
- Development and test validation are supported on Linux and Linux containers.
  On Windows, use WSL2 and run the Linux commands from within WSL2; native
  Windows Python/pytest is not part of the project validation contract. This
  applies only to repository development and testing, not to the integration's
  Home Assistant runtime compatibility.
- `[tool.uv].required-version` is the sole uv executable source. Bootstrap that
  exact uv, then use the committed lock: `uv lock --check`,
  `uv sync --locked --only-group lint`, and
  `uv sync --locked --only-group test`.
- Ruff handles linting, import ordering, and formatting through the exact `lint`
  dependency group. Run `uv run --locked --no-sync ruff check .` and
  `uv run --locked --no-sync ruff format --check .`.
- Direct validation dependencies are exact and Renovate proposes reviewed
  updates after a 72-hour release age. Home Assistant harness compatibility pins
  (`pytest-homeassistant-custom-component`, `homeassistant`, `pytest`, and
  `pytest-asyncio`) are intentionally owner-managed and excluded from Renovate;
  review and update them together in a dedicated owner-reviewed compatibility
  change. `uv.lock` maintenance is reviewed weekly.
- Required CI is locked and reproducible. The daily latest-Home-Assistant canary
  is intentionally non-reproducible and advisory: it resolves the newest stable
  harness for early warning but never updates committed pins or blocks normal
  release validation.
- Tooling targets Python 3.14 with line length 88, and Ruff preview formatting is
  disabled.
- The translation source of truth is
  `custom_components/pollenlevels/translations/en.json`. Keep every other locale
  file in sync with it.
- Do not add or rely on a `strings.json` file; translation updates should flow
  from `en.json` to the other language files.
- Do not introduce `%key:` translation references in this custom repository.
- Preserve the existing coordinator-driven architecture and avoid introducing
  blocking I/O in the event loop.
- Tests use pytest plus `pytest-homeassistant-custom-component` for scenarios
  that exercise Home Assistant's real integration surface, such as config flows,
  subentries, setup/unload, platform registration, services, diagnostics,
  Repairs, registries, and migrations. Prefer focused unit tests for pure
  parsing, API client behavior, redaction helpers, malformed payloads, and
  targeted failure injection.
- Before submitting changes, run:
  - `uv lock --check`
  - `uv sync --locked --only-group lint`
  - `uv run --locked --no-sync ruff check .`
  - `uv run --locked --no-sync ruff format --check .`
  - `uv sync --locked --only-group test`
  - `PYTHONPATH=. uv run --locked --no-sync python -m pytest -q`

## Releases

Release preparation is restricted to maintainers. See
[`RELEASING.md`](RELEASING.md) for the version, validation, draft-release,
publication, and post-release verification process. Contributors must not
manually create tags or releases as part of a normal pull request.
