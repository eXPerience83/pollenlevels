# Contributing

- The integration targets Python 3.14+, matching the Home Assistant 2026.3 runtime baseline.
  Use Python 3.14 for local development and CI parity.
- Format code with Black (line length 88, target-version `py314`) and sort/lint imports with Ruff (`ruff check --fix --select I` followed
  by `ruff check`).
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
  - `ruff check --fix --select I && ruff check` — lint and import ordering.
  - `black .` — code formatting.
  - `pytest tests/` — unit and Home Assistant harness tests.
