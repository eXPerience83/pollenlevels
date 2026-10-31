# Pollen Levels 5.0 preparation and experimental alpha

The development branch `prep/5.0-ha-2026.10.4` tracks #452 / #226.
Its provisional, locked test pair is Home Assistant **2026.10.4** with
pytest-homeassistant-custom-component **0.13.375**. The initial development
baseline kept version metadata at 4.0.3, but was **not the published 4.0.3**
and must never be installed or released under that version.

The experimental `5.0.0a1` metadata, changelog and documentation were
squash-merged into this preparation branch in
[PR #462](https://github.com/eXPerience83/pollenlevels/pull/462) on
2026-10-31. This branch now carries version `5.0.0a1` and the
**alpha-only** `hacs.json` minimum Home Assistant **2026.10.4**.
The `release/5.0.0a1-ha-2026.10.4` branch was a short-lived PR branch,
not a parallel development line; it can be deleted after merge.

The trusted Release workflow must be dispatched from `main` with
`release_ref` set to the **exact prepared commit on the preparation branch**,
creating a draft prerelease without merging 5.0 code into `main`. Review the
ZIP and release metadata before any manual publication. The published stable
4.0.3 stays on `main` with HA 2026.5.0 support unchanged.

This alpha is **not production-ready** and must not be interpreted as
certification of historical HA OS on-disk upgrades, Recorder/statistics
continuity, automated HACS-to-Marketplace takeover, or rollback. Volunteers
using an existing HA instance must first save a complete off-device backup
including persistent `.storage`, config and the Recorder database. On HAOS,
use a full backup and retain its encryption recovery key; on Home Assistant
Container / TrueNAS, stop the container for an offline ZFS snapshot/copy of
its persistent configuration and SQLite database, record image/volume mounts,
and store a second restore-capable copy outside the NAS. External Recorder
databases require their own consistent backups. Restore the matching config,
Registry and history together on failure. **Installing old integration files
over a migrated instance is not a supported rollback.**

The final 5.0 minimum remains a **stable, supported and mature HA 2026.11.x**
paired with matching PHACC, independently validated by tests, dependency
security audit, authentic migrated-install tests, Recorder, Marketplace, and
CodeQL. That later decision must not be silently inferred from the alpha's
temporary HA 2026.10.4 floor.

Development PRs continue to target preparation, not `main`. Merging
the alpha metadata into preparation **does not authorize** a tag, draft,
publication or production installation. Those actions require explicit owner
approval. For alpha installation and manual test cautions see
[README.md](README.md); for the publication procedure see
[RELEASING.md](RELEASING.md).
