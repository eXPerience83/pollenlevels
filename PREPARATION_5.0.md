# Pollen Levels 5.0 — upgrade, validation and rollback

> **Release-readiness guide.** The supported 5.0 target is Home Assistant
> **2026.11.0+** and its built-in Marketplace. This describes the intended
> final user-facing contract and the validation required **before stable**
> publication. It does not certify an unpublished version as production-ready.

## Release and compatibility status

- **Current published stable:** Pollen Levels **4.0.3**, supporting Home
  Assistant 2026.5.0 and newer.
- **5.0 development baseline on `main`:** `5.0.0a2`, using
  `homeassistant==2026.11.0` and official
  `pytest-homeassistant==2026.11.0` under the repository's locked Python
  3.14.7 environment. A source merge does not publish a release.
- **Publication state (2026-11-06):** `v5.0.0a2` is a **draft prerelease**,
  not yet published. `v5.0.0a1` remains an immutable published historical
  alpha with HA 2026.10.4 / PHACC baseline; it does not define the 5.0
  compatibility floor.
- **Target final 5.0 minimum:** Home Assistant **2026.11.0**. The supported
  installation path is **Settings → Marketplace**. Do not install the old
  standalone HACS integration on this version.
- **Stable-release blockers:** genuine installed-upgrade and rollback
  verification, persisted Entity/Device Registry and Recorder/statistics
  continuity, HACS-to-Marketplace takeover, security review, and successful
  candidate package validation. Track [#452](https://github.com/eXPerience83/pollenlevels/issues/452)
  and [#226](https://github.com/eXPerience83/pollenlevels/issues/226).

This file is the detailed companion to [README.md](README.md) and
[FAQ.md](FAQ.md), not a substitute for the published release notes.

## Distribution: HACS → built-in Marketplace

Home Assistant Core 2026.11 includes **Settings → Marketplace**; existing
HACS installations and custom repositories migrate into Marketplace on Core
upgrade. The standalone HACS integration is not installed on 2026.11+.
For publishers, `hacs.json`, the `hacs/default` community catalog, the
`hacs/action` validator and the release ZIP contract **remain in use**.
Do not rename or remove these files/actions just because the UI is now
Marketplace. Keep `zip_release: true`, the root integration package layout
and `pollenlevels.zip` contract. The new My link type is
`marketplace_repository`, while historical `hacs_repository` links
continue to redirect correctly.

References:
[Marketplace](https://www.home-assistant.io/integrations/marketplace),
[Publisher guide](https://contributors.home-assistant.io/marketplace/how-it-works/).

## Automatic compatibility and dependency monitoring

| Purpose | Workflow / bot | Scope and behavior |
| --- | --- | --- |
| Locked mandatory test baseline | `tests.yml` + `lint.yml` | Exact committed `uv.lock` and matching official HA/pytest pair; blocking on PRs |
| Fixed supported floor | `ha-minimum-compatibility.yml` | **HA 2026.11.0**, never PHACC; do not duplicate full tests when the normal locked pair is already 2026.11.0; run independent full-suite + coverage when normal baseline advances |
| Latest stable HA canary | `ha-compatibility-canary.yml` | Daily, isolated fresh PyPI resolution of newest non-yanked, official stable matching pair; advisory only; report upstream publishing lag, failures and exact versions; never edit lock or PR |
| HA baseline updater | `ha-test-baseline-updater.yml` | Daily three-day maturity, exact HA + official pytest pairing, narrow lock diff, full tests + coverage; publish reviewable PRs only after validation; no automerge |
| Routine dependency and action updates | `renovate.json` | Weekly grouped nonmajor GH Action pin updates, reviewed major updates, Python/Ruff/uv tooling rules, three-day release maturity, no automerge; **not** independent HA harness pin drift |
| Dependabot | `.github/dependabot.yml` | Security alert visibility; no duplicate routine uv/Actions update PRs |
| Marketplace catalogue + manifest | `validate.yml`, `hassfest.yml` | Marketplace still uses the HACS validation action plus hassfest |

GitHub's scheduled workflows execute from the **repository default branch**.
As `main` now contains the 5.0 alpha-development baseline, the v5 canary and
updater definitions are the active scheduled workflows. Confirm the timestamp,
selected ref and results of actual runs before claiming a particular check
has executed or passed. Previous 4.0.3 runs are not v5 acceptance evidence.

The GA exception in mandatory lint/tests for the newly published 2026.11.0
lock ends automatically **2026-11-10 00:00 UTC**. Keep the normal
`exclude-newer = "3 days"` and the updater's maturity safeguards intact.
Remove the temporary exception after it expires and mandatory CI proves
the committed lock resolves under the normal policy.

## Real-upgrade acceptance before beta/stable (not alpha promotion)

The synthetic tests and one-location alpha smoke test are valuable but
**do not** establish a production-ready stable upgrade. Use the next
experimental alpha to obtain evidence for the following before beta/stable:

1. Existing 2.3.0 and 4.0.3 installations upgraded with genuine persistent
   HAOS/config entry/Registry data, including custom entity IDs and multiple
   API keys/locations; retry and partial-failure identity must be preserved.
2. Recorder state history and long-term statistics metadata continuity
   across the actual upgrade; preserve entity and statistic IDs.
3. Existing HACS installs carried to Marketplace, repository updates and
   update entities retained; compare catalog/default and custom-repository
   cases without assuming silent ownership takeover.
4. Current compatible dashboard cards, automations, options/subentries,
   scheduled updates and manual refresh after a running HA 2026.11 restart.
5. Complete recoverable backup/restore exercises before any real migration.
   Never rely on copying 4.0.3 code over migrated storage as rollback.
   For rollback, restore the matching configuration, .storage registries,
   and Recorder state from the **same pre-upgrade point in time**.
6. All blocking CI, CodeQL (Python and Actions), workflow security, HACS
   validator, hassfest and CodeRabbit findings, dependency security triage,
   a final candidate ZIP, and maintainer GO/NO-GO.

For existing HAOS, take a **full off-device backup** with encryption recovery
key and Recorder. For container installations, stop the container before an
offline snapshot/copy of persistent config, .storage and SQLite. **Retain a
separate, recoverable copy outside the NAS** and verify the restoration
procedure. If Recorder uses an external database, make an independent,
**consistent backup using that database engine's supported backup method**.
A local snapshot alone is not an off-device backup. Restore the configuration,
registries and Recorder data **together** from a consistent pre-upgrade state.
Never upload credentials, raw `.storage` state, or private coordinates.

## Final 5.0 publication gates

1. Finish targeted 5.0 alpha testing on Home Assistant 2026.11+, using the
   **actual published prerelease ZIP** through Marketplace. A draft is not an
   installable published release.
2. Complete the real-upgrade acceptance matrix above with backed-up v2.3.0
   and v4.0.3 installations, single/multiple locations and API keys, and
   existing dashboards and automations.
3. Verify the persisted Entity and Device Registries, historical Recorder
   state, long-term statistics IDs and Marketplace update-entity continuity.
   Record reproducible results and resolve any data-loss or identity issue.
4. Verify restoration from a consistent pre-upgrade backup. Never describe a
   file-only downgrade as a safe rollback.
5. Require green blocking CI/coverage, the Home Assistant compatibility
   floor, Marketplace validation, hassfest, CodeQL, workflow security and
   resolved review findings. The latest-stable HA canary remains advisory.
6. Prepare an independently reviewed final release/version PR only after
   the gates pass. Keep `manifest.json`, `pyproject.toml`, `uv.lock`, and
   `CHANGELOG.md` version and release metadata synchronized; do not
   change them in a documentation-preparation PR.
7. Follow [RELEASING.md](RELEASING.md) to create a draft release, verify
   the exact commit and ZIP, then **publish manually** as stable only with
   explicit maintainer approval.

Use [AUDIT_5.0_2026.11.md](AUDIT_5.0_2026.11.md) as a historical transversal
audit brief, not as an up-to-date approval. Actual tests, reviews, and the
published release asset determine readiness.
