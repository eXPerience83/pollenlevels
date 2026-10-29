# Future 5.0 preparation branch

`prep/5.0-ha-2026.10.4` is an unpublished integration branch for #452 / #226.
Its interim engineering floor is Home Assistant 2026.10.4 with
pytest-homeassistant-custom-component 0.13.375, matching the normal locked tests.
The minimum test requirements are exported from the existing `uv.lock`, without
resolving newer dependencies. Both lanes use this provisional pair.

Public release metadata remains 4.0.3 and its historical HA 2026.5.0 support is
unchanged on main and published tags. The retained HACS/README minimum on this
branch describes that published release, not support for this unpublished code.
Do not install or publish this branch as 4.0.3.

Device Registry PRs target this preparation branch, not main. Keep baseline
commits separate from runtime changes. Do not merge this branch into main or
publish without explicit authorization. The final 5.0 floor must be a validated,
mature stable HA 2026.11.x / PHACC pair, with consistent public declarations and
passing persisted-upgrade, Recorder and Marketplace gates. Historical Pollen
Levels 2.x / 4.0.3 migration fixtures remain required.
