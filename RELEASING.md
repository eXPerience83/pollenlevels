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

Normal path:

1. Open **Actions**.
2. Open **Prepare Release**.
3. Select **Run workflow**.
4. Select branch `main`.
5. Leave `release_commit` empty when the release PR squash commit is still the
   tip of `main`.
6. Run the workflow.

Delayed or recovery path:

1. Open the merged release PR and copy its full squash commit SHA.
2. Open **Actions** and select **Prepare Release**.
3. Select branch `main`.
4. Enter the full SHA in `release_commit`.
5. Run the workflow.

No version or tag needs to be typed. The workflow reads and validates both
version files, verifies that the selected commit is a single-parent release
squash commit on `main` that changes exactly the three release files, runs
tests, builds and validates the ZIP, and prepares a draft for the derived tag.
Later unrelated commits are not included in the ZIP or release.

Validation, ZIP construction, tag creation, draft creation, and the workflow
summary all use the selected commit. The workflow creates the derived tag
automatically after validation, never moves or force-updates tags, and does not
require manual tag creation. A matching tag can remain after a failed draft
creation attempt; a rerun reuses it safely. Published releases remain immutable
to this workflow.

## 4. Review the draft

- Confirm the tag matches the intended version.
- Confirm the tag points to the selected release PR squash commit.
- Confirm the selected commit shown in the workflow summary.
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

## Release checklist

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
