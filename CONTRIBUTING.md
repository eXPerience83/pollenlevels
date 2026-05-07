# Contributing

- The integration targets Python 3.14+, matching the Home Assistant 2026.3 runtime baseline.
  Use Python 3.14 for local development and CI parity.
- Format code with Black (line length 88, target-version `py314`) and sort/lint imports with Ruff (`ruff check --fix --select I` followed
  by `ruff check`).
- The translation source of truth is `custom_components/pollenlevels/translations/en.json`. Keep every other locale file in
  sync with it.
- Do not add or rely on a `strings.json` file; translation updates should flow from `en.json` to the other language files.
- Preserve the existing coordinator-driven architecture and avoid introducing blocking I/O in the event loop.
