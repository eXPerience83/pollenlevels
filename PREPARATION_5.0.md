# Pollen Levels 5.0 — Home Assistant 2026.11 / Marketplace preparation

> **Alpha development preparation.** This file documents v5 work for the
> next experimental release, not a production-ready 5.0 release. See [roadmap #452](https://github.com/eXPerience83/pollenlevels/issues/452)
> and the [real-upgrade acceptance tracker #226](https://github.com/eXPerience83/pollenlevels/issues/226).

## Branches, versions and historical alpha

- **Until the alpha promotion**, `main` still contains Pollen Levels
  **4.0.3** with a Home Assistant **2026.5.0** minimum. After the approved
  merge, `main` will carry **5.0 alpha development** while the immutable
  **4.0.3 release** remains the latest stable release. Merging into `main`
  does not itself publish a stable integration version.
- **Development line:** `prep/5.0-ha-2026.10.4`. The branch name is historical;
  the **actual declared 5.0 minimum is now Home Assistant 2026.11.0**.
- **Current v5 test pair:** `homeassistant==2026.11.0` and official
  `pytest-homeassistant==2026.11.0` (Python 3.14 as pinned in
  `.python-version`). Old PHACC is removed from v5 test infrastructure.
- The already published `v5.0.0a1` artifact/tag from 2026-10-31 retains
  its **historical** HA 2026.10.4 / PHACC test baseline and its original
  `hacs.json` requirement. The current `prep` branch has commits after that
  tag. Never retag, rebuild, or silently replace the published alpha.
- The new **`5.0.0a2` alpha candidate** has been versioned in release
  preparation PR #470 (manifest, `pyproject.toml`, local `uv.lock` and
  dated changelog). This is **not evidence of publication**: after reviewed
  integration to `main`, validate the selected SHA in Release and publish
  the new draft as a **pre-release**. Never reuse the immutable `v5.0.0a1`
  tag or ZIP.

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
While `main` still contains 4.0.3, its scheduled workflows do **not** run
the unreleased v5 canary/updater. The v5 workflows can be tested via
`workflow_dispatch` where supported, and only become the active schedules
after reviewed merge to `main`. Do not interpret old 4.0.3 schedule results
as v5 compatibility evidence.

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

## Version and merge strategy

- Feature PRs target `prep/5.0-ha-2026.10.4` until promotion. The
  **draft PR #467** to `main` is the review vehicle for **alpha
  development**, not a stable release.
- Run a transversal audit of the complete v5/main diff (recommended first
  pass: **GPT-6 Astra Medium**; escalate focused unresolved migration,
  registry/Recorder/security findings to High). Use
  [AUDIT_5.0_2026.11.md](AUDIT_5.0_2026.11.md) for the complete brief.
- Review and resolve CodeRabbit findings and every required action.
- The release-only **`5.0.0a2` bump** was prepared in PR #470.
  Independently validate the selected lock with normal three-day package
  maturity before publishing; CI's bounded GA bootstrap is **not** Release
  acceptance.
- With alpha-appropriate CI, CodeQL and owner approval, `prep` may be
  merged into `main` as **alpha development**. The release remains
  draft-first and **pre-release**. The real-upgrade gates above apply
  **before beta/stable**, not before the next alpha. Never move published
  tags or overwrite immutable historical artifacts.
