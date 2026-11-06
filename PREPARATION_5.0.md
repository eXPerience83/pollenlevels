# Pollen Levels 5.0 — release readiness, upgrade and rollback

> **5.0 release guide.** Pollen Levels 5.0 targets Home Assistant **2026.11.0+**
> and the built-in Marketplace. This is the release checklist and recovery
> reference for the final 5.0 line; any optional beta is a separate, explicit
> release decision. Passing synthetic tests does not establish that every
> historical Home Assistant installation has been migrated successfully.

## Release and compatibility contract

- **Pollen Levels 5.0 minimum:** Home Assistant **2026.11.0**.
- **Distribution:** the built-in **Settings → Marketplace** with the existing
  `hacs.json`, HACS catalogue and `pollenlevels.zip` publisher contract.
- **Older Home Assistant:** use a compatible 4.x release on HA 2026.5–2026.10.
  Upgrading to 5.0 requires first moving Home Assistant to 2026.11 or newer.
- **Current test contract:** use the committed, locked Home Assistant / official
  `pytest-homeassistant` pair with Python 3.14.2+, the repository's exact Python
  and uv versions, per-module coverage gates and normal dependency maturity.
- **Historical compatibility:** v2.3.0 and v4.0.3 integration layouts have
  persisted-registry/Recorder regression coverage. They remain different from
  a replay of an original historical HAOS backup or a full Marketplace takeover.
- **Publication:** GitHub releases and their ZIP assets, rather than this
  document or the current `main` manifest, determine which version users can
  actually install. Never present an unpublished candidate as published stable.

See [README.md](README.md) for the user guide, [FAQ.md](FAQ.md) for historical
migration and data-retention answers, and [RELEASING.md](RELEASING.md) for
publication steps.

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

The initial Home Assistant 2026.11 GA bootstrap was intentionally
time-limited. **Issue [#473](https://github.com/eXPerience83/pollenlevels/issues/473)**
tracks replacing its exceptional lock/CI settings with ordinary
`exclude-newer = "3 days"` validation. Require normal-policy lock and CI
reproducibility before a 5.0 stable release; do not silently extend a temporary
cooldown bypass. See [RELEASING.md](RELEASING.md).

## Optional beta: transparent migration limitations

A beta can be released as an opt-in **test build** before the full manual
historical-upgrade matrix is complete. It is not mandatory to release another
alpha or beta before stable. If a beta is selected:

1. Require a passing candidate CI/coverage/security/Marketplace/ZIP validation
   and a review of outstanding relevant issues.
2. State plainly **in the beta release notes** that migration from historical
   installations has been exercised using synthetic persistent HA 2026.11 test
   fixtures, **not comprehensively verified by installing and upgrading authentic
   historical HAOS backups**. Mention any outstanding Recorder, long-term
   statistics and HACS→Marketplace checks.
3. Strongly advise a complete, restorable pre-upgrade Home Assistant backup,
   including Recorder, and clearly warn that **downgrading just the integration
   is not a safe rollback**. Upgraders must choose the preview with these
   limitations in mind and report reproducible issues.
4. Gather evidence from any reported real upgrades. **No user reports is not
   proof that an untested migration path works.** A beta's observations may
   improve confidence but do not, by themselves, certify a stable release.

Keep these preview-specific warnings in the release notes instead of making the
general [README.md](README.md) a temporary alpha/beta status page.

## Stable 5.0 verification priorities

The next valuable acceptance work is evidence about actual installations,
rather than additional tests added only to increase the coverage percentage:

1. **Upgrade continuity:** for a genuine 4.0.3 installation (and a 2.3.0
   historical source when available), validate existing parents/locations,
   custom entity names and IDs, multiple API keys/locations where practical,
   and retry/partial-failure behavior.
2. **Recorder and statistics:** verify readable pre-upgrade state history,
   new post-upgrade states, `statistics_meta` and long-term statistics IDs for
   representative sensors. The persisted synthetic tests support these checks
   but do not replace observation of the real stored database.
3. **HACS → Marketplace:** test both catalogue/default and custom-repository
   upgrade paths where available, including preservation of update entities
   and normal in-place updates without removing Pollen Levels.
4. **Dashboard compatibility:** verify configured options/subentries, scheduled
   and manual updates, automations and the current compatible dashboard card
   on HA 2026.11 after a restart.
5. **Recovery:** rehearse restoring a consistent pre-upgrade configuration,
   Registry and Recorder backup. File-only code replacement is not rollback.
6. **Security and package:** review actual dependency advisories, CodeQL,
   CodeRabbit findings, workflow permissions, publisher metadata and exact
   candidate ZIP. CI passing alone is not a security-advisory triage.

For existing HAOS, take a **full off-device backup** with the encryption
recovery key and Recorder. For container installations, stop the container
before an offline snapshot/copy of persistent config, `.storage` and SQLite.
Retain an independent recoverable copy and verify the restoration procedure.
For external Recorder databases, create a consistent engine-native backup.
Restore configuration, registries and Recorder together from the same
pre-upgrade point in time. Never publish credentials, raw `.storage` contents
or private coordinates.

A release decision must distinguish what was directly tested from
unverified paths. If the maintainer accepts residual risk in a final release,
record that decision explicitly; do not claim comprehensive manual acceptance
on the strength of fixtures or the absence of bug reports.

## Final 5.0 publication checklist

1. Confirm `main` and the selected candidate SHA, the **normal-policy**
   committed lock, mandatory full CI and coverage, HA 2026.11 floor,
   Marketplace/HACS validator, hassfest, CodeQL and workflow security.
2. Reconcile outstanding issues [#473](https://github.com/eXPerience83/pollenlevels/issues/473),
   [#452](https://github.com/eXPerience83/pollenlevels/issues/452) and
   [#226](https://github.com/eXPerience83/pollenlevels/issues/226), including
   their remaining migration/Recorder/Marketplace evidence or an explicit
   release decision about any residual gaps.
3. Resolve material reviewer findings, including CodeRabbit if required.
   Review the exact candidate `pollenlevels.zip` and verify its installation
   and update path; a draft release is not an installed published release.
4. In a **separate release-only PR**, synchronize `CHANGELOG.md`,
   `manifest.json`, `pyproject.toml` and the local project version in
   `uv.lock`. Choose beta or stable only when explicitly approved.
5. Follow [RELEASING.md](RELEASING.md) for draft creation, exact tag/SHA/ZIP
   inspection and **manual publication**. Do not reuse or modify a published
   alpha/beta asset or tag.

[AUDIT_5.0_2026.11.md](AUDIT_5.0_2026.11.md) preserves an earlier historical
audit brief, not a current stable-release approval.
