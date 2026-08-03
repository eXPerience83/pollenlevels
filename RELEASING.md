# Releasing Pollen Levels

## Release model

Pollen Levels releases are prepared as GitHub drafts. A maintainer publishes a
release manually only after all validation and package asset checks have passed.

## 1. Prepare the release pull request

Create a release-only pull request. It should normally modify only:

- `custom_components/pollenlevels/manifest.json`
- `pyproject.toml`
- `CHANGELOG.md`

The manifest and project versions must match exactly. The release tag is
derived automatically: version `3.0.1` maps to tag `v3.0.1`, and version
`3.0.1rc1` maps to tag `v3.0.1rc1`.

Include backup, no-downgrade, migration, and prerelease notes where applicable.

## 2. Merge the release pull request

Before merging, ensure that all required checks are green and all reviews and
conversations are resolved. Use **Squash and merge**, then confirm that the
exact release commit is on `main`.

## 3. Prepare the draft release

Normal stable release:

1. Open **Actions**.
2. Open **Prepare Release**.
3. Select **Run workflow**.
4. Select branch `main`.
5. Leave `release_ref` empty to release the current `main` snapshot.
6. Run the workflow.

Specific snapshot:

Enter a branch, tag, or full commit SHA in `release_ref`. The workflow resolves
it to an exact commit; validation, packaging, tagging, and draft preparation
all use that SHA.

No version or tag needs to be typed. The workflow reads and validates both
version files, validates the selected snapshot, runs tests, builds and validates
the ZIP, and prepares a draft for the derived tag. A dedicated release-only PR
is recommended for normal stable releases but is not technically required.

Validation, ZIP construction, tag creation, draft creation, and the workflow
summary all use the resolved commit. The workflow creates the derived tag
automatically after validation, never moves or force-updates tags, and does not
require manual tag creation. A matching tag can remain after a failed draft
creation attempt; a rerun reuses it safely. Published releases remain immutable
to this workflow. External fork refs are not supported.

RC, alpha, beta, dev, preview, and test snapshots may be prepared from an
unmerged same-repository branch: run the workflow from `main`, enter that
branch or commit in `release_ref`, confirm both version files contain the
intended prerelease version, and verify GitHub marks the draft as a prerelease.

## 4. Review the draft

- Confirm the tag matches the intended version.
- Confirm the tag points to the resolved selected SHA.
- Confirm the selected ref and resolved SHA shown in the workflow summary.
- Confirm the prerelease status is correct.
- For a stable release, review GitHub's latest-release setting before manual
  publication. Prereleases must not be marked latest.
- Review and edit generated notes as needed.
- Confirm backup and downgrade warnings are present for v3 where applicable.
- Confirm `pollenlevels.zip` is attached.
- Confirm no unexpected asset is present.
- Confirm the workflow completed successfully.

## 5. Publish

Publication is always manual. For prereleases, ensure the pre-release option is
enabled. For stable releases, ensure it is disabled.

Do not manually create a tag or an empty release.

## 6. Verify the published package

- Confirm the published release contains `pollenlevels.zip`.
- Confirm HACS installation or Redownload uses the published asset.
- Confirm Home Assistant restarts cleanly.
- Confirm the displayed integration version is correct.
- Complete smoke tests appropriate to the release.

## Recovery and reruns

Rerunning Prepare Release before publication is supported: it replaces the ZIP
asset on an existing draft while preserving manually edited draft notes. No
manual tag creation is required. The workflow refuses to change an already
published release, and a tag or draft target pointing to a different commit is
a hard failure. Failed validation does not create a tag or public release.

Do not manually move or delete a release tag to bypass validation.

Once a version is published, its tag must not be moved. Code changes after a
published version require a new version; documentation-only repository changes
after publication do not necessarily require a new release.

## Release checklist

- [ ] Selected ref and resolved SHA were reviewed.
- [ ] Manifest and project version files match.
- [ ] Changelog is complete.
- [ ] Release PR checks are green.
- [ ] Release PR was squash merged.
- [ ] Prepare Release ran on `main`.
- [ ] Draft review is complete.
- [ ] `pollenlevels.zip` is attached.
- [ ] Prerelease status is correct.
- [ ] The release was published manually.
- [ ] HACS package verification is complete.
