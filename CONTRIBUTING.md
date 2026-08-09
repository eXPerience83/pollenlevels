# Contributing

- The integration targets Python 3.14+, matching the Home Assistant 2026.3 runtime baseline. Use the exact patch in `.python-version` for local development and CI parity.
- Development and test validation are supported on Linux and Linux containers. On Windows, use WSL2 and run the Linux commands from within WSL2; native Windows Python/pytest is not part of the project validation contract. This applies only to repository development and testing, not to the integration's Home Assistant runtime compatibility.
- `[tool.uv].required-version` is the sole uv executable source. Bootstrap that exact uv, then use the committed lock: `uv lock --check`, `uv sync --locked --only-group lint`, and `uv sync --locked --only-group test`.
- Ruff handles linting, import ordering, and formatting through the exact `lint` dependency group. Run `uv run --locked --no-sync ruff check .` and `uv run --locked --no-sync ruff format --check .`.
- Direct validation dependencies are exact and Renovate proposes reviewed updates after a 72-hour release age. The Home Assistant harness lane updates its paired Home Assistant, pytest, and pytest-asyncio pins only when its published metadata requires it; `uv.lock` maintenance is reviewed weekly.
- Required CI is locked and reproducible. The daily latest-Home-Assistant canary is intentionally non-reproducible and advisory: it resolves the newest stable harness for early warning but never updates committed pins or blocks normal release validation.
- Tooling targets Python 3.14 with line length 88, and Ruff preview formatting is disabled.
- The translation source of truth is `custom_components/pollenlevels/translations/en.json`. Keep every other locale file in
  sync with it.
- Do not add or rely on a `strings.json` file; translation updates should flow from `en.json` to the other language files.
- Do not introduce `%key:` translation references in this custom repository.
- Preserve the existing coordinator-driven architecture and avoid introducing blocking I/O in the event loop.
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
