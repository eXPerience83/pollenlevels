# Effective Actions protection policy

Verified and activated on 2026-11-07 in both DKN Cloud and Pollen Levels.
Pollen's [main ruleset](https://github.com/eXPerience83/pollenlevels/rules/20281037)
is active; the [importable blueprint](./protect-main-ruleset.json) now includes
CodeQL, after successful hosted Python and Actions analyses. A JSON file alone
never applies GitHub settings. Recheck the live API after any settings change.

- Main requires a PR, squash merge, linear history, no deletion/force push, and
  an up-to-date branch with eight GitHub Actions checks (app ID 15368):
  `actionlint`, `lint`, `tests`, `validate`, `validate-hacs`, `zizmor`, `package`,
  `minimum-compatibility`.
- CodeQL blocks errors and high-or-higher security alerts. Default Setup scans
  Python and Actions; no duplicate CodeQL workflow is needed.
- The existing maintainer model has zero mandatory approving reviews and an
  administrator bypass restricted to PRs. This is not an independent-review
  guarantee. Maintainers must review the exact checked HEAD and must not use
  bypass to merge failed or incomplete CI. No workflow may merge its own PR.
- Default `GITHUB_TOKEN` permission is read; workflow PR approvals are disabled;
  full action SHA pinning is required by the repository setting. Only draft
  finalization and the reviewed updater publisher receive explicit write scope.
- [Release tag rules](./protect-release-tags-ruleset.json) forbid updating or
  deleting `v*` tags, with no bypass actors. Tag creation remains available only
  through the reviewed release procedure; the ruleset does not itself restrict
  who can create a new tag.
- Native release immutability is enabled for future publications. Existing
  releases are not retroactively made immutable. Finish draft preparation
  before manually publishing; no workflow repairs a published asset.

## Shared workflow responsibilities

Lint and Tests validate the committed lock; Package Test validates the ZIP
without repeating the full suite. Workflow Security blocks actionlint/ShellCheck
and high-severity, medium-or-higher-confidence zizmor findings. hassfest and
Marketplace validation remain separate required checks. Their SHA-pinned
wrappers still consume upstream container images; wrapper pinning alone is not
an immutable transitive image guarantee.

Minimum Compatibility always installs its frozen SHA-256 graph and tests the
2026.11.0 support floor independently. The latest-HA canary fresh-resolves in an
isolated read-only environment and is advisory. The updater proposes reviewed
PRs with exact official HA/pytest pairs, a global 72-hour cutoff, narrowly
bounded early exceptions and package-preserving normalization after maturity.
A writer closes/reopens token-created updater PRs to trigger normal required CI.

Release runs from main. Other selected snapshots are dry-run rehearsals only;
draft preparation requires the exact main workflow SHA and successful required
checks. It validates the release group, Ruff, full coverage, ZIP and digest in
read scope, then separately finalizes with write scope. Existing draft assets
are reused by equal digest, never overwritten. Publication remains manual.

Keep Python/uv pins, coverage floors, integration ZIP names and manifest/tooling
version contracts project-specific. Review equivalent security behavior across
both repositories when changing shared helpers; do not introduce a floating
cross-repository reusable workflow or routine minimum-graph updates.

See [GitHub immutable-release documentation](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
and [RELEASING.md](../RELEASING.md).
