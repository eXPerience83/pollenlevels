# Contributing

- The integration targets Python 3.14+, matching the Home Assistant 2026.3 runtime baseline.
  Use Python 3.14 for local development and CI parity.
- Ruff handles linting, import ordering, and formatting. Upgrade Ruff before validating to match CI's rolling minimum policy: `python -m pip install --upgrade "ruff>=0.15"`.
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
  - `ruff check --fix --select I .`
  - `ruff check .`
  - `ruff format .`
  - `ruff format --check .`
  - `python -m pytest -q`
