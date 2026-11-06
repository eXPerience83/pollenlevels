# Releasing Pollen Levels

## Release model

Draft-first preparation is the recommended release path. An emergency
post-publication fallback is also supported, while publication itself is always
initiated manually by a maintainer.

Only trusted maintainers with write access should dispatch Release. The workflow
definition runs from `main`, while `release_ref` intentionally permits an
unmerged same-repository branch, tag, or SHA for prerelease, express, and
historical-snapshot releases; branch protection on `main` does not review it.
Pull-request pseudo-refs and Git revision expressions are rejected. A full SHA
must be reachable from a normal repository branch or tag; unmerged
same-repository branches remain supported, and ancestry from `main` is not
required.

## Home Assistant 2026.11 and Marketplace release gate

For an eventual **Pollen Levels 5.0 beta/stable** release, require a validated
minimum HA **2026.11.0**, exact officially paired `homeassistant` /
`pytest-homeassistant` tooling, full locked CI and the independent fixed-floor
lane once the normal baseline advances. The latest-stable canary is advisory;
neither its success nor a green synthetic test suite alone certifies a real
upgrade. Assess identity, Recorder and long-term statistics, existing HACS
installation takeover by built-in Marketplace, multiple API keys/locations,
backup restoration, security/CodeQL, and an explicit owner GO/NO-GO under
[#452](https://github.com/eXPerience83/pollenlevels/issues/452) and
[#226](https://github.com/eXPerience83/pollenlevels/issues/226).

Marketplace is built into HA 2026.11+. **Keep** `hacs.json`, the existing
HACS catalogue validation action and `pollenlevels.zip`; these are still
the required Marketplace publisher contracts. No standalone HACS install is
needed on HA 2026.11+. The already published `v5.0.0a1` tag is immutable;
prepare a **new** release version, never reuse the alpha version.
The next **`5.0.0a2` alpha** can follow a reviewed alpha-development merge
to `main` and be published draft-first as a **prerelease** after exact-version,
lock, CI/CodeQL and ZIP checks. Full real HAOS/Recorder/Marketplace acceptance
comes **after this alpha and before beta/stable**.

## Validation environments

Modern snapshots use the exact Python patch in `.python-version`, the central
`[tool.uv].required-version`, exact PEP 735 dependencies, and committed
`uv.lock`. Release validates modern snapshots with `uv lock --check` and
`uv sync --locked --only-group release`; do not replace this with pip installs
or a fresh resolution. For snapshots with `scripts/check_coverage.py`, the
modern release validation **also runs pytest-cov and the same per-module coverage
gate used by CI, against the exact selected release commit**. A candidate
declaring the HA 2026.11.0 v5 floor is rejected if that checker is missing.
Historical snapshots predating the checker retain their original pytest path.
**New 5.x snapshots** (except immutable historical `v5.0.0a1`) must include
`scripts/check_coverage.py` and declare HA 2026.11.0; this historical
fallback is not a coverage waiver for new v5 releases.

Historical snapshots are classified against immutable boundary
`0e65e38e2830c0485cdc6b3a00c95ad7e65d7427`. A selected commit that is equal
to or older than that boundary may use only its own historical release
workflow, Python request, Ruff requirement, `requirements_test.txt`, and ZIP
validator. Divergent snapshots are modern only with a complete modern toolset,
or legacy only with zero modern markers and complete selected-snapshot legacy
inputs; partial or ambiguous snapshots fail closed. Legacy summaries explicitly
report that validation is non-lock-reproducible.

The scheduled latest-Home-Assistant compatibility canary is advisory and
intentionally fresh-resolving. It is not a Release dependency, does not update
pins or `uv.lock`, and cannot replace the required locked validation lane.

## 1. Prepare a release pull request (recommended)

For normal stable releases, a release-only pull request is recommended. It
should normally modify exactly:

- `CHANGELOG.md`
- `custom_components/pollenlevels/manifest.json`
- `pyproject.toml`
- `uv.lock`

The manifest and project versions must match exactly, and the local
`pollenlevels` package version recorded in `uv.lock` must match that same release
version. Synchronize the lockfile with the repository-pinned uv version and the
existing lock policy; do not use `uv lock --upgrade` as part of release
preparation.

For a release-only version synchronization, the expected `uv.lock` diff is only
the local `pollenlevels` project version. Any unrelated dependency version,
hash, source, resolution marker, or other lock metadata change is unexpected and
must be investigated before merge. `uv lock --check` must pass before the
release pull request is considered ready.

The release tag is derived automatically: version `3.0.1` maps to tag `v3.0.1`,
and version `3.0.1rc1` maps to tag `v3.0.1rc1`.

Include backup, no-downgrade, migration, and prerelease notes where applicable.

## 2. Merge the release pull request (if used)

If a release PR was used, ensure that all required checks are green and all
reviews and conversations are resolved. Use **Squash and merge**, then confirm
that the exact release commit is on `main`.

## 3. Release

Recommended draft-first mode:

1. Open **Actions**.
2. Open **Release**.
3. Select **Run workflow**.
4. Select branch `main`.
5. Leave `release_ref` empty to release the current `main` snapshot.
6. Run the workflow. It validates, builds the ZIP, creates or reuses the tag,
   and prepares a draft.

Review the draft and publish manually. The resulting `release: published` run
detects the existing `pollenlevels.zip` and exits successfully without
replacing it.

Specific snapshot:

Enter a branch, tag, or full commit SHA in `release_ref`. The workflow resolves
it to an exact commit; validation, packaging, tagging, and draft preparation
all use that SHA.

For a specific snapshot, enter only `release_ref`; no separate version or
release-tag field is required. The workflow reads and validates both version
files, validates the selected snapshot, runs tests, builds and validates the
ZIP, and prepares a draft for the derived tag.

Validation, ZIP construction, tag creation, draft creation, and the workflow
summary all use the resolved commit. The workflow creates the derived tag
automatically after validation, never moves or force-updates tags, and does not
require manual tag creation. A matching tag can remain after a failed draft
creation attempt; a rerun reuses it safely. Prepare mode refuses to alter an
already published release; published-fallback mode may attach exactly one
missing ZIP without replacing an existing ZIP, moving a tag, or changing release
metadata. External fork refs are not supported.

RC, alpha, beta, dev, preview, and test snapshots may be prepared from an
unmerged same-repository branch: run the workflow from `main`, enter that
branch or commit in `release_ref`, confirm both version files contain the
intended prerelease version, and verify GitHub marks the draft as a prerelease.

## 4. Review the draft

- Confirm the tag matches the intended version.
- Confirm the tag points to the resolved selected SHA.
- Confirm the resolved SHA shown in the workflow summary matches the intended
  selected ref.
- Confirm the prerelease status is correct.
- For a stable release, review GitHub's latest-release setting before manual
  publication. Prereleases must not be marked latest.
- Review and edit generated notes as needed.
- Confirm backup and downgrade warnings are present for v3 where applicable.
- Confirm `pollenlevels.zip` is attached.
- Confirm no unexpected asset is present.
- Confirm the workflow completed successfully.

## Emergency published fallback

A trusted maintainer may manually create a tag and publish a GitHub release.
The `release: published` event starts the same Release workflow. When
`pollenlevels.zip` is absent, it validates the tagged snapshot, builds and
validates the ZIP, and attaches it. The release is already public while this
runs, so a failure leaves a public release requiring maintainer action.

Prepare mode refuses to alter an already published release. Published-fallback
mode may attach exactly one missing `pollenlevels.zip`, but never moves a tag,
replaces an existing ZIP, or changes release metadata. Draft-first remains the
recommended path; the published fallback is for exceptional use.

## 5. Publish

Publication is always manual. For prereleases, ensure the pre-release option is
enabled. For stable releases, ensure it is disabled.

## 6. Verify the published package

- Confirm the published release contains `pollenlevels.zip`.
- For HA 2026.11+, confirm Marketplace install/update or Redownload uses the
  published ZIP, preserving existing installations and update entities.
- For **historical/maintenance releases supporting HA <2026.11**, also verify
  compatible **HACS** installation or Redownload and the published version
  selection. Do not claim an HACS check applies to HA 2026.11+.
- Confirm Home Assistant restarts cleanly.
- Confirm the displayed integration version is correct.
- Complete smoke tests appropriate to the release.

## Recovery and reruns

Rerunning Release in draft-first mode before publication replaces the ZIP asset
on an existing draft while preserving manually edited notes. Prepare mode
refuses already published releases; a `release: published` fallback run may
attach one missing ZIP. A tag or draft target pointing to another commit remains
a hard failure.

Do not manually move or delete a release tag to bypass validation.

Once a version is published, its tag must not be moved. Code changes after a
published version require a new version; documentation-only repository changes
after publication do not necessarily require a new release.

## Release checklist

- [ ] Selected ref and resolved SHA were reviewed.
- [ ] Manifest version matches project version.
- [ ] `uv.lock` local `pollenlevels` package version matches the release version.
- [ ] `uv lock --check` passes.
- [ ] Release lock synchronization introduced no unrelated dependency, hash,
      source, resolution-marker, or other lock metadata changes.
- [ ] Changelog is complete.
- [ ] If a release PR was used, its checks are green.
- [ ] If a release PR was used, it was squash merged.
- [ ] Release completed through either the draft-first or emergency fallback route.
- [ ] For draft-first releases, draft review is complete.
- [ ] `pollenlevels.zip` is attached before Marketplace verification.
- [ ] Prerelease status is correct.
- [ ] The release was published manually.
- [ ] Marketplace/HACS catalog ZIP validation and existing HACS → Marketplace
      update takeover verification are complete where applicable.
- [ ] For historical or maintenance releases supporting HA <2026.11,
      installation/update through compatible legacy HACS was checked.
- [ ] Stable v5 HA 2026.11.0 floor and official pytest pair were checked.
- [ ] Existing Registry/Recorder/statistics migration and backup recovery are verified.
- [ ] CodeRabbit and full candidate CodeQL/CI/security review are complete.
