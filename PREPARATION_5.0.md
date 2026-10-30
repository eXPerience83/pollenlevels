# Pollen Levels 5.0 preparation and experimental alpha

The development branch `prep/5.0-ha-2026.10.4` is an **unpublished,
unversioned candidate** for #452 / #226. Its interim engineering floor is
Home Assistant 2026.10.4 with
pytest-homeassistant-custom-component 0.13.375, matching both locked test
lanes. The minimum requirements are exported from the current `uv.lock`.
Its version metadata still reads 4.0.3: **never install or release that
unversioned preparation branch as 4.0.3**.

The independent `release/5.0.0a1-ha-2026.10.4` branch is the **experimental
alpha release candidate**. Only on this versioned branch, manifest/project/lock
metadata use `5.0.0a1`, and `hacs.json` declares the temporary minimum
HA 2026.10.4. The published stable 4.0.3 remains on `main`, with HA 2026.5.0
support unchanged.

This alpha is **not production-ready** and must not be interpreted as
certification of historical HA OS on-disk upgrades, Recorder/statistics
continuity, automated HACS-to-Marketplace takeover, or rollback. Volunteers
using an existing HA instance must first save a complete off-device backup
including the local Recorder database, plus the encryption recovery key, and
restore the matching full system backup if migration is unsuccessful. External
Recorder databases require separate backups. **Installing old integration
files over a migrated instance is not a supported rollback.**

The final 5.0 minimum remains a **stable, supported and mature HA 2026.11.x**
paired with matching PHACC, independently validated by tests, dependency
security audit, authentic migrated-install tests, Recorder, Marketplace, and
CodeQL. That later decision must not be silently inferred from the alpha's
temporary HA 2026.10.4 floor.

Development PRs continue to target preparation; the versioned alpha branch is
a release candidate and must not be merged into `main` or published without
explicit owner approval. For alpha installation and manual test cautions see
[README.md](README.md); for the publication procedure see
[RELEASING.md](RELEASING.md).
