# Releasing Pollen Levels

## Release model

Draft-first preparation is the release path. Publication is always initiated
manually by a maintainer after the workflow completes.

Only trusted maintainers should dispatch Release, using workflow branch `main`.
Draft preparation selects the exact workflow main commit and rechecks its CI.
Other same-repository branches, tags and historical SHAs are supported only for
`dry_run=true`, with read-only validation. Pull-request pseudo-refs and revision
expressions are rejected; full SHAs must be reachable from a repository branch
or tag. A successful unmerged rehearsal does not authorize publication.

## Home Assistant 2026.11 and Marketplace release gate

For any **Pollen Levels 5.0 candidate**, validate the minimum HA
**2026.11.0**, the exact officially paired `homeassistant` /
`pytest-homeassistant` tooling, locked tests/coverage, packaging and security.
The independent fixed-floor lane runs once the normal pinned baseline advances;
the latest-stable canary is advisory.

An **optional beta** may be used to gather real migration evidence before full
manual historical-upgrade acceptance, provided the release notes state the
limitations of synthetic persisted migrations, the risks to Recorder/history
and the need for a recoverable complete backup. Do not present beta validation
as a certified real historical upgrade. A **stable 5.0** release requires a
separate explicit maintainer GO/NO-GO, informed by identity, Recorder and
long-term statistics, HACS → Marketplace continuity, multi-location/key
behavior, recovery and security evidence or a clearly recorded decision on
any residual uncertainty. See [PREPARATION_5.0.md](PREPARATION_5.0.md),
[#452](https://github.com/eXPerience83/pollenlevels/issues/452) and
[#226](https://github.com/eXPerience83/pollenlevels/issues/226).

Marketplace is built into HA 2026.11+. **Keep** `hacs.json`, the existing
HACS catalogue validation action and `pollenlevels.zip`; these are still
the required Marketplace publisher contracts. No standalone HACS install is
needed on HA 2026.11+. The published `v5.0.0a1` and `v5.0.0a2` prerelease tags/assets are
historical and immutable. Prepare a **new version** for any subsequent beta,
release candidate or stable release, never reuse an already published tag.
Publication requires exact-version, lock, CI/CodeQL, review and ZIP checks
and explicit manual maintainer approval.

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

## One-run dependency maturity exceptions

Normal resolution keeps `exclude-newer = "3 days"`. A trusted maintainer may
request an exception through `workflow_dispatch` on `main`, with a non-blank,
printable, single-line reason of 15–200 characters. Reasons are displayed as
literal text in the run summary and, for updater PRs, in the PR body, including
when the selected HA/pytest pair is already mature.

Release has no global cooldown bypass. Prepare an early official pair through
the reviewed baseline updater's two artifact-bounded cutoffs. Every modern
snapshot must pass the trusted source/lock policy and locked validation; stable
releases reject any remaining exception. Historical legacy rehearsal retains
its explicitly reported pip-based limitations and cannot prepare a draft.

For the baseline updater, `override_cooldown` waives maturity only for the
exact official Home Assistant / pytest-homeassistant pair. Absolute UTC cutoffs
include the last published artifact; the rest of the graph retains three days
of maturity. The updater rejects unrelated lock changes and validates the
source/lock policy before and after resolution. Tests, coverage and Ruff remain
mandatory. No automatic merge or publication is enabled.

After the pinned pair matures, the updater proposes a `normalize` PR removing
the exception without changing any package record, including when a newer pair
is still cooling. A later early update must calculate new artifact cutoffs.
Stable releases remain blocked while an exception is present (see #473).

Updater PRs use `GITHUB_TOKEN`, which does not trigger their normal PR workflows.
A repository writer must close and reopen the PR to trigger required CI, then
review the exact checked HEAD before merging. Never bypass required checks.

### Validation-only dry run (recommended before beta/RC publication)

In **Actions → Release → Run workflow**, select workflow branch `main`, set
`dry_run = true`, and provide a reviewed `release_ref` (prefer an exact
40-character commit SHA). The workflow performs the same selected-snapshot
version, locked environment, coverage, security-relevant packaging and ZIP
validation, then uploads `pollenlevels.zip` as a short-lived workflow artifact
and prints its SHA-256. It **does not** create a tag, GitHub Release draft or
published release; it cannot make a beta appear in Marketplace.

A dry run does not waive the 72-hour policy, replace the reviewed normal-policy
lock or establish historical
Registry/Recorder migration acceptance. Review the workflow artifact and all
required checks, then run the actual draft-first Release independently.

The guarantees follow the selected snapshot's validation mode. Legacy snapshots
use their recorded pip environment, not a uv lock, and run pytest without the
modern coverage gate. Historical modern snapshots without a coverage checker
also run pytest without that gate. Review the validation-mode summary; these
historical exceptions do not establish current locked/coverage compliance.

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

Include backup, no-file-only-downgrade and migration notes where applicable.
For a beta, state explicitly whether historical migrations were validated
only with synthetic persisted fixtures, identify relevant unverified real
upgrade paths, and **recommend a full Home Assistant backup before upgrading**.
If Recorder uses an external database, also recommend backing it up separately;
a Home Assistant backup may not include it.
Keep detailed backup instructions in [PREPARATION_5.0.md](PREPARATION_5.0.md). Do not imply
that a lack of reported beta failures proves every migration path.

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

Specific snapshot rehearsal:

Set `dry_run=true` and enter a branch, tag or full SHA in `release_ref`. The
workflow resolves it once and uses that commit for validation and packaging.
No tag, draft or release is created. To prepare an alpha, beta or RC draft,
merge the reviewed version PR, wait for main CI, then dispatch from main with
`dry_run=false` and an empty `release_ref` (or that exact workflow main SHA).

Draft preparation creates the derived tag after validation, never moves tags,
and refuses already published releases. A matching tag left by an interrupted
run may be reused. Published-event observers never add missing assets.

## 4. Review the draft

- Confirm the tag matches the intended version.
- Confirm the tag points to the resolved selected SHA.
- Confirm the resolved SHA shown in the workflow summary matches the intended
  selected ref.
- Confirm the prerelease status is correct.
- For a stable release, review GitHub's latest-release setting before manual
  publication. Prereleases must not be marked latest.
- Review and edit generated notes as needed.
- Confirm backup, migration and no-file-only-downgrade warnings are present for upgrades to v5 and older migrations where applicable.
- If publishing a beta, confirm the notes disclose unverified historical migrations,
  recommend a backup, and warn against a file-only downgrade.
- Confirm `pollenlevels.zip` is attached and was built from the intended
  candidate version and commit. Test its Marketplace install/update after publication.
- Confirm no unexpected asset is present.
- Confirm the workflow completed successfully.

## Published-event observer

The `release: published` event checks that the expected ZIP is present. Missing
or duplicate assets fail for manual investigation; no automatic repair runs.
Older tags retain their historical workflow code and are not retroactively
attested by this policy. Always finish draft preparation before publication.

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

An existing draft ZIP is reused only when GitHub reports the same SHA-256.
Missing assets may be added; different or unverifiable assets fail closed and
are never overwritten. Notes are preserved. An existing tag must point to the
validated commit. Without a tag, the draft target_commitish must equal that SHA.
Published releases are never repaired by this workflow.

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
- [ ] The release PR and exact main commit have successful required checks.
- [ ] The reviewed release PR was squash merged.
- [ ] Draft-first Release completed successfully.
- [ ] Draft review is complete.
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

## Independent minimum compatibility graph

The HA 2026.11.0 floor is tested on every PR and main push and weekly/manual
runs using `.github/requirements/minimum-ha.txt` with `uv pip sync
--require-hashes`. It was exported from the reviewed Pollen lock without
resolving new versions. `.in` records the fixed direct inputs. The temporary
`UV_EXCLUDE_NEWER=false` in this installation step permits only these already
reviewed hashes; it cannot resolve newer packages. `uv pip check`, the full
official harness suite and Pollen's coverage gates remain mandatory.

This graph stays independent of future baseline updates. Renovate must not
refresh it automatically. Any deliberate refresh needs a separate reviewed
change preserving the declared HA floor, exact input pins and complete hashes;
never regenerate it from a newer baseline lock as routine maintenance.

## Reviewed main preparation and immutable retries

Dispatch Release from `main`. A non-dry run must select the exact main commit
that supplied the workflow. Other branch, tag and historical references are
validation-only (`dry_run=true`). A future beta can therefore be rehearsed by
exact SHA without creating a tag, draft or published asset. Merge its reviewed
PR and wait for main CI before preparing its draft.

Immediately before writes, trusted workflow code checks that main has not moved
and that the latest GitHub Actions results for all eight required jobs on that
exact SHA are successful. Missing, pending and failed reruns fail closed.
Release uses no dependency cache. Publication remains a separate manual step;
wait for the entire workflow to finish before publishing or editing the draft.

ZIP timestamps come from the selected commit. An existing draft ZIP is reused
only when GitHub reports the same SHA-256; an unverifiable or different asset
is never overwritten. Published events only check asset presence and cannot
repair or replace assets. Older tags retain their historical workflow code;
this policy does not retroactively attest those releases.

Before reporting success, finalization rereads the remote draft and all assets
and requires the validated SHA-256 and prerelease classification. A concurrent
upload skipped by the action cannot masquerade as a successful validated ZIP.
Lint always checks the triggering SHA; manual runs select their workflow branch
without a separate checkout override that could mislabel another commit's check.
