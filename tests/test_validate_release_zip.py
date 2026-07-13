"""Regression tests for release ZIP validation."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from scripts.validate_release_zip import validate_zip

REQUIRED_FILES = (
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
)
VALID_MANIFEST = {"domain": "pollenlevels", "version": "3.0.0rc3"}


def _valid_members() -> dict[str, bytes]:
    """Return the minimal file members for a valid release ZIP."""
    members = {name: b"" for name in REQUIRED_FILES}
    members["manifest.json"] = json.dumps(VALID_MANIFEST).encode()
    return members


def _write_zip(zip_path: Path, members: dict[str, bytes]) -> None:
    """Write ZIP members without extracting them to disk."""
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def _valid_zip(tmp_path: Path) -> Path:
    """Create a minimal valid integration-root release ZIP."""
    zip_path = tmp_path / "pollenlevels.zip"
    _write_zip(zip_path, _valid_members())
    return zip_path


@pytest.mark.parametrize(
    "expected_release_tag",
    [pytest.param(None, id="without-release-tag"), pytest.param("v3.0.0rc3")],
)
def test_valid_release_zip_is_accepted(
    tmp_path: Path, expected_release_tag: str | None
) -> None:
    """Accept a complete package with an optional matching release tag."""
    validate_zip(_valid_zip(tmp_path), expected_release_tag)


def test_empty_release_zip_is_rejected(tmp_path: Path) -> None:
    """Reject archives that have no integration members."""
    zip_path = tmp_path / "empty.zip"
    _write_zip(zip_path, {})

    with pytest.raises(SystemExit, match="ZIP is empty"):
        validate_zip(zip_path, None)


@pytest.mark.parametrize("missing_file", ["button.py", "translations/en.json"])
def test_missing_required_file_is_rejected(tmp_path: Path, missing_file: str) -> None:
    """Reject packages missing required root or nested integration files."""
    members = _valid_members()
    del members[missing_file]
    zip_path = tmp_path / "missing.zip"
    _write_zip(zip_path, members)

    with pytest.raises(SystemExit, match=re.escape(missing_file)):
        validate_zip(zip_path, None)


@pytest.mark.parametrize(
    ("member_name", "error_fragment"),
    [
        pytest.param("/payload", "absolute", id="posix-absolute"),
        pytest.param("C:/payload", "absolute", id="windows-drive-root"),
        pytest.param("folder\\payload", "backslash", id="backslash"),
        pytest.param("../payload", ".. traversal", id="parent-traversal"),
        pytest.param("directory/../payload", ".. traversal", id="nested-traversal"),
        pytest.param(
            "custom_components/pollenlevels/manifest.json",
            "custom_components/ prefix",
            id="custom-components-prefix",
        ),
    ],
)
def test_unsafe_member_path_is_rejected(
    tmp_path: Path, member_name: str, error_fragment: str
) -> None:
    """Reject ZIP paths that could alter the intended archive root."""
    zip_path = _valid_zip(tmp_path)
    with zipfile.ZipFile(zip_path, "a") as archive:
        archive.writestr(member_name, b"payload")

    with pytest.raises(SystemExit, match=re.escape(error_fragment)):
        validate_zip(zip_path, None)


def test_duplicate_file_member_is_rejected(tmp_path: Path) -> None:
    """Reject duplicate file entries before an uploader can choose one."""
    zip_path = _valid_zip(tmp_path)
    with zipfile.ZipFile(zip_path, "a") as archive:
        with pytest.warns(UserWarning, match="Duplicate name: 'sensor.py'"):
            archive.writestr("sensor.py", b"duplicate")

    with pytest.raises(SystemExit, match="duplicate members: sensor.py"):
        validate_zip(zip_path, None)


def test_duplicate_directory_member_is_rejected(tmp_path: Path) -> None:
    """Reject duplicate directory entries as well as duplicate files."""
    zip_path = _valid_zip(tmp_path)
    with zipfile.ZipFile(zip_path, "a") as archive:
        archive.writestr("translations/", b"")
        with pytest.warns(UserWarning, match="Duplicate name: 'translations/'"):
            archive.writestr("translations/", b"")

    with pytest.raises(SystemExit, match="duplicate members: translations/"):
        validate_zip(zip_path, None)


@pytest.mark.parametrize(
    "member_name",
    [
        pytest.param("__pycache__/payload.py", id="pycache"),
        pytest.param(".pytest_cache/payload", id="pytest-cache"),
        pytest.param(".ruff_cache/payload", id="ruff-cache"),
        pytest.param("payload.pyc", id="pyc"),
        pytest.param("payload.pyo", id="pyo"),
    ],
)
def test_generated_or_cache_member_is_rejected(
    tmp_path: Path, member_name: str
) -> None:
    """Reject generated content that must not be published in a release ZIP."""
    zip_path = _valid_zip(tmp_path)
    with zipfile.ZipFile(zip_path, "a") as archive:
        archive.writestr(member_name, b"generated")

    with pytest.raises(SystemExit, match="generated/cache"):
        validate_zip(zip_path, None)


@pytest.mark.parametrize(
    ("manifest_content", "error_fragment"),
    [
        pytest.param(b"\xff", "not valid UTF-8", id="invalid-utf8"),
        pytest.param(b"{", "not valid JSON", id="invalid-json"),
        pytest.param(b"[]", "root is not an object", id="non-object-root"),
    ],
)
def test_malformed_manifest_is_rejected(
    tmp_path: Path, manifest_content: bytes, error_fragment: str
) -> None:
    """Reject manifests that cannot provide valid integration metadata."""
    members = _valid_members()
    members["manifest.json"] = manifest_content
    zip_path = tmp_path / "malformed-manifest.zip"
    _write_zip(zip_path, members)

    with pytest.raises(SystemExit, match=re.escape(error_fragment)):
        validate_zip(zip_path, None)


def test_wrong_manifest_domain_is_rejected(tmp_path: Path) -> None:
    """Reject packages that do not identify the pollenlevels domain."""
    members = _valid_members()
    members["manifest.json"] = json.dumps(
        {"domain": "other", "version": "3.0.0rc3"}
    ).encode()
    zip_path = tmp_path / "wrong-domain.zip"
    _write_zip(zip_path, members)

    with pytest.raises(SystemExit, match="manifest.domain is not 'pollenlevels'"):
        validate_zip(zip_path, None)


@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param({"domain": "pollenlevels"}, id="missing-version"),
        pytest.param({"domain": "pollenlevels", "version": 3}, id="integer-version"),
    ],
)
def test_missing_or_non_string_manifest_version_is_rejected(
    tmp_path: Path, manifest: dict[str, object]
) -> None:
    """Reject manifests that do not provide a string version for tag validation."""
    members = _valid_members()
    members["manifest.json"] = json.dumps(manifest).encode()
    zip_path = tmp_path / "invalid-version.zip"
    _write_zip(zip_path, members)

    with pytest.raises(SystemExit, match="manifest.version is not a string"):
        validate_zip(zip_path, None)


@pytest.mark.parametrize("version", ["", "   "])
def test_empty_manifest_version_is_rejected(tmp_path: Path, version: str) -> None:
    """Reject empty and whitespace-only manifest versions."""
    members = _valid_members()
    members["manifest.json"] = json.dumps(
        {"domain": "pollenlevels", "version": version}
    ).encode()
    zip_path = tmp_path / "empty-version.zip"
    _write_zip(zip_path, members)

    with pytest.raises(SystemExit, match="manifest.version is empty"):
        validate_zip(zip_path, None)


def test_mismatched_release_tag_reports_actual_and_expected_tags(
    tmp_path: Path,
) -> None:
    """Reject release tags that do not exactly match the packaged version."""
    with pytest.raises(
        SystemExit,
        match=re.escape("tag='v0.0.0' != 'v3.0.0rc3'"),
    ):
        validate_zip(_valid_zip(tmp_path), "v0.0.0")
