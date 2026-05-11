"""Repository secret hygiene tests."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "venv",
}
GOOGLE_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{20,}")
PLACEHOLDER_MARKERS = ("EXAMPLE", "FAKE", "PLACEHOLDER", "REDACTED")


def _is_ignored(path: Path) -> bool:
    """Return whether any part of a repository-relative path is ignored."""
    return any(part in IGNORED_DIRS for part in path.parts)


def _is_allowed_placeholder(candidate: str) -> bool:
    """Allow obviously fictitious or redacted API key examples."""
    return any(marker in candidate.upper() for marker in PLACEHOLDER_MARKERS)


def test_repository_does_not_contain_google_api_keys() -> None:
    """Prevent real-looking Google API keys from being committed."""
    findings: list[str] = []

    for path in sorted(ROOT.rglob("*")):
        relative_path = path.relative_to(ROOT)
        if (
            not path.is_file()
            or _is_ignored(relative_path)
            or path.suffix not in TEXT_SUFFIXES
        ):
            continue

        content = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(content.splitlines(), start=1):
            for match in GOOGLE_API_KEY_RE.finditer(line):
                candidate = match.group(0)
                if _is_allowed_placeholder(candidate):
                    continue
                findings.append(f"{relative_path}:{line_number}: {candidate}")

    assert not findings, "Real-looking Google API keys found:\n" + "\n".join(findings)
