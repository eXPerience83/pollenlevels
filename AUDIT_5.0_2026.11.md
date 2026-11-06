# Independent transversal audit — Pollen Levels v5 / HA 2026.11

> **Review plan, not an audit verdict.** Request an independent Codex run
> after the CI and CodeRabbit comments on the completed preparation PR are
> available. Recommended first run: **GPT-6 Astra, Medium**. Escalate only
> concrete unresolved identity, Recorder, Marketplace security or migration
> issues to High. No release, tag, deployment or merge authorization here.

## Exact scope

Repository: `eXPerience83/pollenlevels`.

Compare **stable `main` 4.0.3** to the **entire future 5.0 preparation line**:
the source branch `prep/5.0-ha-2026.10.4` (the name is historical), including
the dedicated 2026.11 Marketplace/CI/docs PR. Do **not** limit the audit to
the latest PR, last commit, or 2026.11 tooling only. Read AGENTS.md,
PREPARATION_5.0.md, issues #452/#226/#465, and the published `v5.0.0a1`
manifest for immutable-artifact history.

**Objective:** decide whether v5 can safely become the new `main` baseline
after a separate version bump and owner approval. Do not automatically merge
or release anything.

## Required audit lenses

1. **Compatibility and dependency graph**
   - Confirm `hacs.json` minimum HA 2026.11.0, exact official
     `homeassistant`/`pytest-homeassistant` version pairing, provenance,
     no PHACC namespace or package in v5, Python 3.14 runtime contract and
     lock graph integrity.
   - Confirm the declared minimum remains 2026.11.0 when the pinned test
     baseline advances to .1+; no duplicated full suite at the same version.
   - Check fresh daily stable canary selects only non-yanked verified official
     releases >=2026.11.0, handles version/publishing lag and has no mutation.
   - Check three-day updater maturity, yanked/rollback rejection, transitive
     lock-delta verification, full coverage gates, PR-only permissions,
     no automerge and no outdated main/PHACC assumptions.
   - Check Renovate action pin/digest updates and security-only Dependabot
     exclusions. Scheduled jobs execute only from the default branch;
     avoid claiming an unreleased prep schedule has actually run.

2. **Marketplace / legacy HACS continuity**
   - Keep `hacs.json`, `hacs/default`, `hacs/action`, ZIP layout, published
     asset name, repository identity, and Marketplace catalog validation.
   - Validate install, existing HACS→Marketplace update continuity, custom
     repository migration and status/update entities.
   - Verify documentation points to Settings → Marketplace on HA 2026.11,
     no standalone HACS prerequisite, correct new My link; historical
     `v5.0.0a1` published content remains unchanged.
   - Separate documentation assertions from real HAOS acceptance evidence.

3. **Runtime identity, upgrades and Recorder**
   - Inspect migration v2→v3, config parent/subentries for multiple keys
     and locations, entity/device/unique IDs, stored legacy associations,
     registry partial/unavailable states, idempotency, rollback-failure
     behavior, concurrent setup/reload, manual updates.
   - Inspect persisted upgrades from v2.3.0 and v4.0.3 with **real**
     Registry and Recorder storage where possible. Verify stable entity IDs,
     user names, locations, old/new states, long-term statistics metadata
     and automations/dashboard compatibility.
   - Do not assume synthetic fixtures or one user's alpha smoke test prove
     real upgrade, multiple location/keys, restored backups or statistics.

4. **Security and reliability**
   - Audit data exposure (API keys, precise coordinates, diagnostics and
     log redaction), network/error boundaries, rate limits, request caching
     and Google Pollen attribution/retention constraints.
   - Triage actual dependencies and upstream pinned advisories without
     inventing overrides that violate Home Assistant constraints.
   - Verify CodeQL (Python/Actions), workflow permissions, SHA pinning,
     shell injection/delimiter risks, artifacts, release workflow trust,
     draft-only publication and no hidden auto-merge path.
   - Verify package/manifest/release version consistency, never relabel or
     overwrite published `v5.0.0a1` assets.

5. **Tests and release readiness**
   - Full Ruff, pytest/coverage, minimum floor, Marketplace catalog,
     hassfest, CodeQL and CodeRabbit. The repo quality gate is literal
     100% config-flow statement coverage and >95% for non-migration modules.
   - Identify gaps that require a supervised HAOS migration/restore test,
     separate from gaps fixable in repository tests.
   - Inspect repository docs/changelog against current code and avoid
     leaving stale minimum/PHACC instructions presented as future contracts.

## Audit output format

Return:
- **GO / NO-GO for merging v5 into `main`** (separately from GO for
  publishing a stable release).
- Findings ordered **P0 critical, P1 high, P2 medium, P3 low** with file and
  line anchors, exact code/test evidence, real repro when available,
  consequence, and smallest safe remedy.
- Distinguish *observed defects*, *test coverage gaps*, *uncertainties*,
  and *historical documentation preserved intentionally*.
- Exact CI checks that passed/failed and HEAD SHAs; do not invent test
  results or claim independent validation when only reviewing CI logs.
- List of merges/releases explicitly **blocked** by unresolved findings
  and whether they can be finished without touching runtime code.
- Minimal proposed focused PR sequence to resolve findings; no sweeping
  refactor, silent migration rewrite, weakening assertions or HACS metadata
  deletion. **Do not merge/publish/deploy**.

## Suggested execution

Use GPT-6 Astra **Medium** for this full transversal audit first; it is
usually enough to identify systemic risk without consuming a High budget
over straightforward docs/CI changes. Reuse the output in a **targeted**
High audit only for complex P1/P0 findings (migration/Recorder/identity,
Marketplace takeover, security trust boundary) after concrete repros.
