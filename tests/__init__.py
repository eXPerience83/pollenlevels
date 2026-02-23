"""Test package marker.

This file ensures that imports like `import tests.test_config_flow` resolve to the
repository's local `tests` package instead of an unrelated third-party package
named `tests` that may be present in site-packages.
"""
