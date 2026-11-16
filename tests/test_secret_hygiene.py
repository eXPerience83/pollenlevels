"""Repository secret hygiene tests."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".http",
    ".curl",
    ".har",
}
IGNORED_DIRS = {
    ".git",
    ".local",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
GOOGLE_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{20,}")
PLACEHOLDER_MARKERS = ("EXAMPLE", "FAKE", "PLACEHOLDER", "REDACTED")


def _is_allowed_placeholder(candidate: str) -> bool:
    """Allow obviously fictitious or redacted API key examples."""
    return any(marker in candidate.upper() for marker in PLACEHOLDER_MARKERS)


def _is_scanned_text_file(path: Path) -> bool:
    """Return whether a file should be scanned as repository text."""
    return (
        path.suffix in TEXT_SUFFIXES
        or path.name == ".env"
        or path.name.startswith(".env.")
    )


def test_repository_does_not_contain_google_api_keys() -> None:
    """Prevent real-looking Google API keys from being committed."""
    findings: list[str] = []

    for directory, subdirectories, filenames in os.walk(ROOT):
        # Prune generated/virtualenv trees before entering them, not afterward.
        subdirectories[:] = sorted(
            name for name in subdirectories if name not in IGNORED_DIRS
        )
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if not path.is_file() or not _is_scanned_text_file(path):
                continue

            relative_path = path.relative_to(ROOT)
            with path.open(encoding="utf-8", errors="ignore") as file_obj:
                for line_number, line in enumerate(file_obj, start=1):
                    for match in GOOGLE_API_KEY_RE.finditer(line):
                        candidate = match.group(0)
                        if _is_allowed_placeholder(candidate):
                            continue
                        findings.append(
                            f"{relative_path}:{line_number}: real-looking Google API key"
                        )

    assert not findings, "Real-looking Google API keys found:\n" + "\n".join(findings)


def test_secret_scan_detects_nested_env_but_skips_ignored_trees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep scanning nested/untracked secrets while excluding virtualenv files."""
    synthetic_key = "AI" + "za" + "q" * 32
    included = tmp_path / "nested" / ".env.local"
    included.parent.mkdir()
    included.write_text(f"GOOGLE_API_KEY={synthetic_key}\n", encoding="utf-8")
    ignored = tmp_path / ".venv" / "lib" / "secret.py"
    ignored.parent.mkdir(parents=True)
    ignored.write_text(f"GOOGLE_API_KEY={synthetic_key}\n", encoding="utf-8")

    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    with pytest.raises(AssertionError, match=r"nested/\.env\.local:1"):
        test_repository_does_not_contain_google_api_keys()

    included.unlink()
    test_repository_does_not_contain_google_api_keys()
