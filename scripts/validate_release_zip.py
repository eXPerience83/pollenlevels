"""Validate the release ZIP before it is uploaded."""

import argparse
import json
import ntpath
import os
import zipfile
from pathlib import Path

REQUIRED_FILES: frozenset[str] = frozenset(
    {
        "manifest.json",
        "__init__.py",
        "config_flow.py",
        "client.py",
        "coordinator.py",
        "sensor.py",
        "button.py",
        "diagnostics.py",
        "services.yaml",
        "translations/en.json",
    }
)
CACHE_DIRECTORIES: frozenset[str] = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache"}
)


def validate_zip(zip_path: Path, expected_release_tag: str | None) -> None:
    """Validate the structure and manifest of a release ZIP archive."""
    with zipfile.ZipFile(zip_path) as zf:
        all_names: list[str] = zf.namelist()
        if not all_names:
            raise SystemExit("ZIP is empty")

        for name in all_names:
            if "\\" in name:
                raise SystemExit(f"Unsafe member path (backslash): {name}")
            if os.path.isabs(name) or ntpath.isabs(name):
                raise SystemExit(f"Unsafe member path (absolute): {name}")
            if ".." in name.split("/"):
                raise SystemExit(f"Unsafe member path (.. traversal): {name}")

        bad_prefix: list[str] = [
            name for name in all_names if name.startswith("custom_components/")
        ]
        if bad_prefix:
            raise SystemExit(
                "ZIP contains custom_components/ prefix; "
                "zip must be integration-root only"
            )

        generated: list[str] = []
        for info in zf.infolist():
            name = info.filename
            if any(part in CACHE_DIRECTORIES for part in name.split("/")):
                generated.append(name)
            if not info.is_dir() and name.endswith((".pyc", ".pyo")):
                if name not in generated:
                    generated.append(name)
        if generated:
            raise SystemExit(
                "ZIP contains generated/cache files: " + ", ".join(generated)
            )

        file_names: set[str] = {
            info.filename for info in zf.infolist() if not info.is_dir()
        }

        seen: set[str] = set()
        dupes: set[str] = set()
        for name in all_names:
            if name in seen:
                dupes.add(name)
            seen.add(name)
        if dupes:
            raise SystemExit(
                "ZIP contains duplicate members: " + ", ".join(sorted(dupes))
            )

        missing: list[str] = sorted(REQUIRED_FILES - file_names)
        if missing:
            raise SystemExit("ZIP missing required root files: " + ", ".join(missing))

        print("ZIP structure validated.")

        try:
            manifest_bytes: bytes = zf.read("manifest.json")
        except KeyError:
            raise SystemExit("manifest.json not found in ZIP") from None

        try:
            manifest_text: str = manifest_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SystemExit(f"manifest.json is not valid UTF-8: {error}") from None

        try:
            manifest: object = json.loads(manifest_text)
        except json.JSONDecodeError as error:
            raise SystemExit(f"manifest.json is not valid JSON: {error}") from None

        if not isinstance(manifest, dict):
            raise SystemExit("manifest.json root is not an object")

        domain: object = manifest.get("domain")
        if domain != "pollenlevels":
            raise SystemExit(f"manifest.domain is not 'pollenlevels': {domain!r}")

        version: object = manifest.get("version")
        if not isinstance(version, str):
            raise SystemExit(
                f"manifest.version is not a string: {type(version).__name__}"
            )
        if not version.strip():
            raise SystemExit("manifest.version is empty")

        print("manifest.json validated.")

        if expected_release_tag is not None:
            expected: str = f"v{version}"
            if expected_release_tag != expected:
                raise SystemExit(
                    "Release tag mismatch: "
                    f"tag={expected_release_tag!r} != v{version!r}"
                )
            print(f"Release tag validated: {expected_release_tag} == v{version}")


def main() -> None:
    """Run release ZIP validation from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip_path", type=Path)
    arguments = parser.parse_args()
    validate_zip(arguments.zip_path, os.environ.get("EXPECTED_RELEASE_TAG"))


if __name__ == "__main__":
    main()
