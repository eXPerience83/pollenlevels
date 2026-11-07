"""Exercise the real draft preflight against published and conflicting assets."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ZIP_NAME = "pollenlevels.zip"
SHA = "a" * 40
DIGEST = "b" * 64


def _workflow():
    return yaml.load(
        Path(".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("empty", "update"),
        ("same", "reuse"),
        ("different", None),
        ("unhashed", None),
        ("duplicate", None),
        ("published", None),
    ],
)
def test_preflight_rejects_published_or_conflicting_assets(tmp_path, state, expected):
    jobs = _workflow()["jobs"]
    step = next(
        s
        for s in jobs["finalize-release"]["steps"]
        if s["name"] == "Preflight release state"
    )
    source = (
        step["run"]
        .split("python - <<'PY' >> \"$GITHUB_OUTPUT\"\n", 1)[1]
        .rsplit("\nPY", 1)[0]
    )
    asset = {"name": ZIP_NAME, "state": "uploaded", "digest": "sha256:" + DIGEST}
    if state == "different":
        asset["digest"] = "sha256:" + "c" * 64
    elif state == "unhashed":
        asset.pop("digest")
    release = {
        "tag_name": "v1.0.0b1",
        "draft": state != "published",
        "html_url": "https://example.invalid/draft",
        "target_commitish": SHA,
        "assets": [] if state == "empty" else [asset],
    }
    if state == "duplicate":
        release["assets"].append(asset)
    response = tmp_path / "releases.json"
    response.write_text(json.dumps([[release]]))
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        env={
            "RELEASES_RESPONSE": str(response),
            "TAG_EXISTS": "false",
            "TAG_COMMIT": "",
            "VALIDATED_COMMIT": SHA,
            "RELEASE_TAG": "v1.0.0b1",
            "ZIP_SHA256": DIGEST,
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert (result.returncode == 0) == (expected is not None), result.stderr
    if expected:
        assert "release_mode=" + expected in result.stdout


def test_finalization_is_manual_trusted_main_only():
    jobs = _workflow()["jobs"]
    finalize = jobs["finalize-release"]
    assert (
        finalize["if"]
        == "github.event_name == 'workflow_dispatch' && inputs.dry_run != true && needs.validate-release.outputs.skip_release != 'true'"
    )
    assert finalize["steps"][0]["with"]["ref"] == "${{ github.workflow_sha }}"
    names = [s["name"] for s in finalize["steps"]]
    assert names.index("Recheck main and required checks before writes") < names.index(
        "Create and verify release tag"
    )
    for step in finalize["steps"]:
        assert "gh release upload" not in step.get("run", "")
        if step.get("uses", "").startswith("softprops/"):
            assert step["with"]["overwrite_files"] == "false"
    validation = jobs["validate-release"]["steps"]
    names = [s["name"] for s in validation]
    assert names.index("Enforce reviewed main preparation policy") < names.index(
        "Check out selected snapshot"
    )
