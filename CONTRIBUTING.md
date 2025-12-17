# Contributing

- Follow Home Assistant's current Python floor for integration code (Python 3.13). Tooling is pinned to Python 3.14, but
  integration logic must stay compatible with 3.13 syntax and standard library features.
- Format code with Black (line length 88, target-version `py314`) and sort/lint imports with Ruff (`ruff check --fix --select I` followed
  by `ruff check`).
- The translation source of truth is `custom_components/pollenlevels/translations/en.json`. Keep every other locale file in
  sync with it.
- Do not add or rely on a `strings.json` file; translation updates should flow from `en.json` to the other language files.
- Preserve the existing coordinator-driven architecture and avoid introducing blocking I/O in the event loop.
