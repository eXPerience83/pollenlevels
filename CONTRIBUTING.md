# Contributing

## Home Assistant Core readiness

Pollen Levels is currently a custom integration distributed through HACS, but the
long-term project goal is to prepare it for a future contribution to Home
Assistant Core.

Development in this repository should therefore improve **Core readiness** while
preserving the complete and stable HACS integration that users run today. The
current Home Assistant developer documentation and Integration Quality Scale are
the upstream reference for that work:

- [Contributing an integration to Core](https://developers.home-assistant.io/docs/core/integration/contributing_to_core/)
- [Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
- [Full config-flow test coverage](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-flow-test-coverage/)
- [Above 95% test coverage for all integration modules](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/test-coverage/)

New Core integrations currently need to meet the Bronze quality tier. Bronze
already includes full config-flow test coverage, above 95% test coverage for all
integration modules, and dependency transparency. Treat those as baseline
Core-readiness requirements, not as higher-tier extras.

For this repository:

- `config_flow.py` should reach literal 100% statement coverage, including error
  recovery and all supported user, reauth, reconfigure, subentry, and options
  behavior;
- every integration module should exceed 95% statement coverage, measured per
  module rather than only as a repository-wide total;
- tests should protect real behavior, identity, privacy, lifecycle, retry, and
  failure semantics rather than merely execute lines to improve a percentage;
- code proven unreachable on supported Home Assistant should be reviewed for a
  dedicated cleanup/refactor rather than covered by artificial tests or silently
  excluded from the target;
- supported public Home Assistant APIs, async patterns, typing conventions, and
  Home Assistant harness tests are preferred whenever they represent the real
  integration surface.

The project may adopt higher-tier Quality Scale practices when they improve the
current HACS integration or reduce future upstream work, but that must not make a
future initial Core pull request unnecessarily large.

Core readiness does **not** mean reducing the HACS integration to the size of a
future initial Core pull request. Home Assistant recommends that a new Core
integration start with a small, focused contribution, normally one platform and
without non-essential features such as diagnostics, custom actions, reauth, or
reconfigure. Those upstream scoping rules will be applied when a dedicated Core
port is prepared; they are not a reason to remove working HACS functionality now.

Home Assistant Core also expects communication with the external service to live
in a separate Python library. The current in-repository API client remains part
of the HACS architecture until a dedicated, reviewed library-extraction effort
is undertaken. Do not split it out opportunistically as collateral work.

Likewise, this custom repository keeps
`custom_components/pollenlevels/translations/en.json` as its translation source
of truth. A future Core contribution will adapt to Core repository translation
conventions at that boundary; do not introduce `strings.json` here prematurely.

Before any upstream Core submission, perform a dedicated Core-readiness audit
against the then-current Home Assistant requirements, including the Quality
Scale checklist, dependency transparency/library requirements, manifest and
branding requirements, documentation, test coverage, and initial-PR scope.

## Development environment

- The integration targets Python 3.14+, matching the Home Assistant 2026.3
  runtime baseline. Use the exact patch in `.python-version` for local
  development and CI parity.
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
  updates after a 72-hour release age. The Home Assistant harness lane updates
  its paired Home Assistant, pytest, and pytest-asyncio pins only when its
  published metadata requires it; `uv.lock` maintenance is reviewed weekly.
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
