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

No version or tag needs to be typed. The workflow reads and validates both
version files, validates the selected snapshot, runs tests, builds and validates
the ZIP, and prepares a draft for the derived tag. A dedicated release-only PR
is recommended for normal stable releases but is not technically required.

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
- Confirm the selected ref and resolved SHA shown in the workflow summary.
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
- Confirm HACS installation or Redownload uses the published asset.
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
- [ ] Manifest and project version files match.
- [ ] Changelog is complete.
- [ ] For normal stable releases, release PR checks are green.
- [ ] For normal stable releases, the release PR was squash merged.
- [ ] Release completed through either the draft-first or emergency fallback route.
- [ ] For draft-first releases, draft review is complete.
- [ ] `pollenlevels.zip` is attached before HACS verification.
- [ ] Prerelease status is correct.
- [ ] The release was published manually.
- [ ] HACS package verification is complete.
