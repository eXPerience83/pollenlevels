# Changelog

## [1.6.4.4] – 2025-08-17
### Fixed
- **Critical**: restore a corrupted `sensor.py` that mixed class blocks, broke loops,
  and truncated `_normalize_payload()`. Rebuilt the module in correct order,
  re-added `BasePollenEntity`, fixed entity creation loops, and ensured the
  normalized data schema includes `region`, `days`, `types`, `plants`, and
  `last_updated`. HTTP handling now uses `HTTPStatus` consistently.
- **Options validation**: add missing imports `MIN_DAYS_FOR_D1` / `MIN_DAYS_FOR_D12`
  in `config_flow.py` so CFS vs. days checks are effective.

### Notes
- No functional regressions: sensors, attributes and options remain the same.
- CI: **Ruff + Black** and **hassfest/HACS validate** should pass with these changes.

## [1.6.4.3] – 2025-08-17
### Fixed
- **Ruff lint**: resolve remaining `UP038` and `B007` findings in `sensor.py`
  to make the **Auto Format (Black + Ruff)** workflow pass.
  - Replace `isinstance(x, (int, float))` with `isinstance(x, int | float)`.
  - Rename unused loop variables (`tdata`, `pdata`) to `_tdata`, `_pdata`.
### Notes
- No functional changes. API calls, entities, options, and translations unchanged.
- `config_flow.py` continues to perform **online validation** (403 → `invalid_auth`, 429 → `quota_exceeded`, others → `cannot_connect`).

## [1.6.4.2] – 2025-08-17
### Changed
- **Per-day sensors option values** reverted to published style: `none` / `D+1` / `D+1+2`.
  This removes legacy normalization (`d1`/`d12`) introduced in alphas and simplifies validation & configuration paths.
### Notes
- Initial setup validation (403/429/other) is preserved.
- Entity Registry cleanup for per-day sensors remains unchanged.

## [1.6.4.1] – 2025-08-17
### Maintenance
- **Docs alignment**: README options now use the same localized wording as the UI (**“Tomorrow only” / “Tomorrow and the day after”**).
- **Code cleanup**: import `API_URL` from `const.py` in `sensor.py` to avoid duplicating the endpoint definition.

## [1.6.4] – 2025-08-17
### Added
- **PLANTS forecast**: plant sensors now expose `forecast` (with `tomorrow_*`, `d2_*`, `trend`, `expected_peak`), same as TYPES.
- **Initial setup validation**: online check of API key / location (403 → invalid_auth, 429 → quota_exceeded, others → cannot_connect).
- Options UI for forecast & per-day sensors.

### Changed
- Unified forecast parsing for TYPES and PLANTS (1–5 days).
- Proactive cleanup of **stale per-day TYPE sensors** on options reload.

### Fixed (hotfix 1.6.4a)
- **Color robustness**: missing RGB channels default to **0** so `color_hex` is always emitted when a color dict is present.
- **Translated device grouping**: keep three localized device groups (**Types / Plants / Info**).
- **Plant icon** updates dynamically based on the latest `type`.

## [1.6.3] – 2025-08-17
### Fixed
- **Entity cleanup**: remove stale per-day TYPE sensors `(D+1)/(D+2)` from the **Entity Registry** on entry setup when options no longer request them or `forecast_days` is insufficient. This prevents “Unavailable” leftovers after Options → Reload.
### Improved
- **Icons (plants)**: normalize `type` to uppercase to map icons consistently.

## [1.6.2] – 2025-08-14
### Changed
- **Auto Format workflow**:
  - Remove custom branch dropdown; rely on GitHub’s native branch selector (shows only existing branches).
  - Stop creating PRs (avoids “GitHub Actions is not permitted to create or approve pull requests”); now commits are pushed back to the same branch.
  - Comments rewritten in English.
- **Ruff config**: migrate to `tool.ruff.lint` / `tool.ruff.lint.isort` to remove deprecation warnings on 0.5.x.
- Bump manifest version to **1.6.2**.

## [1.6.1] – 2025-08-14
### Changed
- **Options Flow**: unify D+1 / D+2 toggles into a single selector:
  `create_forecast_sensors` with values `none` (default), `D+1`, `D+1+2`.
- Add validation to ensure `forecast_days` covers the selected per-day sensors.
- Update translations (EN/ES/CA/DE/FR/IT/PL/RU/UK) and docs.

## [1.6.0] – 2025-08-14
### Added
- Multi-day forecast for pollen **TYPES** (GRASS/TREE/WEED):
  - `forecast` attribute (list of entries with `offset`, `date`, `has_index`, `value`, `category`, `description`, `color_*`).
  - Convenience attributes: `tomorrow_*`, `d2_*`, plus `trend` and `expected_peak`.
  - Optional per-day TYPE sensors for **(D+1)** and **(D+2)**.
### Notes
- Plants remain current-day only in 1.6.0. Forecast for plants will be considered in the next phase.

## [1.5.5] – 2025-08-11
### Docs
- **button-card example**: fixed JavaScript snippets to access entity state via `states[entity]` and use the correct `color` property for icon tinting.
- Minor wording polish in the README around native vs. custom color handling.
### Maintenance
- Bump `manifest.json` version to **1.5.5**.
### Notes
- No code changes; this release is documentation-only and safe to update.

## [1.5.4] – 2025-08-10
### Fixed
- **Color extraction**: `color_hex` is now produced even when the API omits one or more channels (e.g., only `green`+`blue`). Missing channels default to `0`. Also accepts either `0..1` floats or `0..255` values.
### Added
- New attributes to make colors easier to consume in Lovelace:
  - `color_rgb`: `[R, G, B]` integers (0–255)
  - `color_raw`: original API color dict for traceability
### Docs
- **Corrected UI examples**:
  - Removed the non-existent core card type **`template`** (caused “Unknown type: template”).
  - Clarified that **Markdown** sanitizes HTML and **will not** render inline CSS colors.
  - Added working examples for **Mushroom (mushroom-template-card)** and **button-card** using the `color_hex` attribute.
  - Kept native **Entities**, **Tile + Template Sensor**, and **Gauge** examples (no custom cards required).
### Notes
- No breaking changes: entity states and IDs are unchanged; attributes are additive.

## [1.5.3] – 2025-08-09
### Added
- **Type sensors** now expose `inSeason`, `advice` (health recommendations when available), and `color_hex` derived from `indexInfo.color`. `description` (UPI) remains present.
- **Plant sensors** now expose `advice` (if provided), `color_hex`, `code`, `picture`, and `picture_closeup`.
### Notes
- All additions are **non-breaking**: states and entity IDs are unchanged; attributes are added only when present in the API response.

## [1.5.2] – 2025-08-09
### Added
- **Localized Options Flow strings** for 9 languages (EN, ES, CA, DE, FR, IT, PL, RU, UK). Users now see the Options dialog (title, description, fields) fully translated.
### Maintenance
- Version bump in `manifest.json` to 1.5.2.
- Verified that translations match the Options Flow step id (`init`) and keys (`update_interval`, `language_code`).

## [1.5.1] – 2025-08-08
### Added
- **Index description attribute**: Each pollen **type** and **plant** sensor now exposes the human-readable `description` derived from Google’s `indexInfo.indexDescription` (UPI). This is additive and does not change entity states or IDs.
### Maintenance
- Minor code hygiene in `config_flow.py`: import order clean-up and removal of a redundant manual interval check (schema already enforces `min=1`).

## [1.5.0] – 2025-08-08
### Added
- **Options Flow** to change `update_interval` and `language_code` without reinstalling.
- **Duplicate prevention**: entries are uniquely identified by `(latitude, longitude)` and duplicates are rejected.
### Changed
- Reused the same language-code validation in options to provide consistent, localized error messages.
### Notes
- To apply options immediately, the integration reloads after saving. Make sure the coordinator reads `entry.options` first (fallback to `entry.data`).


## [1.4.2] – 2025-07-09
### Changed
- Updated Readme and minor changes.

## [1.4.1] – 2025-07-07
### Changed
- Reordered keys in `manifest.json` to satisfy Hassfest requirements (domain, name, then the rest alphabetically).
- Added `services.yaml` to document the `pollenlevels.force_update` service.
- Introduced `CONFIG_SCHEMA` in `__init__.py` using `cv.config_entry_only_config_schema(DOMAIN)` to silence the configuration-schema warning.
- Removed unsupported `"domains"` key from `hacs.json`.
- Updated `hacs.json` to include only the necessary fields (`name`, `render_readme`, `content_in_root`).
- Added required GitHub topics (`home-assistant`, `hacs`, `integration`, `sensor`, `pollen`, `allergy`) to pass HACS topic validation.
### Fixed
- Metadata ordering and format corrections to comply with CI validations.

## [1.4] - 2025-06-21
### Changed
- Now the core sensor entities "Region", "Date" and "Last Updated" use `translation_key` and are automatically displayed in the user's language, matching device localization.
- No more hard-coded names: all core fixed entities are now fully internationalized and can be customized in all supported languages via `translations/xx.json`.
- Improved code and translation consistency for entity naming across the entire integration.

## [1.3.8.3] - 2025-06-21
### Added
- Added full multi-language support for device and entity names in all supported languages (en, es, ca, de, fr, it, pl, ru, uk).
- Updated all translations in `translations/xx.json` to include device and entity name keys, with support for dynamic placeholders (latitude, longitude).
### Changed
- All core entities (`Region`, `Date`, `Last Updated`) and device groups (`Pollen Types`, `Plants`, `Pollen Info`) now show in the Home Assistant UI using the active language.

## [1.3.8.2] - 2025-06-21
### Fixed
- Move Last Updated sensor to Diagnostics category.
- Reuse Home Assistant HTTP session in coordinator to reduce resource usage.
- Use `async_refresh()` in force_update service to wait until the update completes.
### Changed
- Clean imports and update docstrings for PEP 257 compliance.

## [1.3.8.1] - 2025-06-17
### Fixed
- Ensure all sensor entities (including `PollenSensor`, `RegionSensor`, `DateSensor` and `LastUpdatedSensor`) subclass `CoordinatorEntity`, so their state updates immediately after calling `pollenlevels.force_update`.
- Correct propagation of the `last_updated` timestamp to the **Last Updated** sensor on manual refresh.
### Changed
- Rewrote all docstrings in imperative, one‑line style to comply with PEP 257 and remove in‑line `# noqa` directives.
- Reorganized `sensor.py` with clear section headers and streamlined comments for readability.

## [1.3.8] - 2025-06-16
### Added
- Service pollenlevels.force_update to manually trigger an immediate refresh of all sensors and reset the update interval.
- New Last Updated metadata sensor displaying the ISO‑8601 timestamp of the last successful data fetch.
### Changed
- Cleaned up docstrings to imperative style to comply with PEP 257 and avoid per-line # noqa directives.
- Reorganized sensor.py with clear section headers and comments.

## [1.3.7.1] - 2025-05-29
### Added
- **New plant sensor attribute**: Added `cross_reaction` field showing pollen cross-reactivity information for each plant type.
### Fixed
- **Critical syntax error**: Fixed unclosed parenthesis in config_flow.py that prevented integration loading.
- **Language validation**: 
  - Improved error logging for invalid language codes
  - Corrected indentation in validation error handling
### Improved
- **Data completeness**: Plant sensors now include all available API data including cross-reactivity warnings
- **Error handling**: More detailed logging for configuration flow errors

## [1.3.6] - 2025-05-29
### Fixed
- **Critical translation error**: Moved `"empty"` key from `data` to `error` section in `en.json` (was causing UI serialization issues).
- **Language code validation**:
  - Updated regex pattern to `^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$` (supports 3-letter base codes like `cmn` and regions like `zh-Hant`).
  - Added case-insensitive matching (`en-US` and `en-us` now both valid).
  - Improved empty string check with `.strip()` to catch whitespace-only inputs.
### Improved
- Added detailed warning logs for language code validation failures in `config_flow.py`.

## [1.3.5] - 2025-05-27
### Added
- New **Region** and **Date** metadata sensors to expose `regionCode` and API response date in a dedicated **Pollen Info** device.
### Improved
- **Language code validation** refined using IETF regex `^[a-zA-Z]{2,3}(-[a-zA-Z]{2})?$` to support codes like `es`, `en-US`, `fr-CA`, etc.
- Introduced `is_valid_language_code(value)` helper that raises `vol.Invalid("invalid_language")` for invalid formats and `vol.Invalid("empty")` for blank inputs.
- Translations updated with new error keys `invalid_language` and `empty` across all supported languages.
### Fixed
- ❗️ **UI schema serialization crash**: Removed `vol.All(cv.string, is_valid_language_code)` from the `data_schema` to restore compatibility with Home Assistant's UI config flow system.  
  Validation now occurs manually before API call, and error is assigned via `errors[CONF_LANGUAGE_CODE]`.


## [1.3.3] - 2025-05-26
### Improved
- Basic IETF Regular Expression Validation:
    Uses the pattern ^[a-zA-Z]{2,3}(-[a-zA-Z]{2})?$ to allow codes like es, en-US, fr-CA, etc.
- Function is_valid_language_code(value):
    Checks for non-empty language and pattern matching.
    Throws vol.Invalid("invalid_language") if invalid.
- Validation in async_step_user:
    Before contacting the API, validate the language code and return the appropriate error if it's invalid.
- Custom Error Key:
    Uses errors[CONF_LANGUAGE_CODE] = "invalid_language" to integrate into the configuration interface.
- Updated languages.

## [1.3.2] - 2025-05-23
- Added RU an UK translations. Thanks to [@gruzdev-studio](https://github.com/gruzdev-studio)

## [1.3.1] - 2025-05-22
- Updated from beta.
- Fixed translations (PL)

## [1.3.0] - 2025-05-22
### Added
- Optional `language_code` field in configuration to request API responses in the desired language.  
- Translations updated to include `language_code` label and description.  
### Improved
- Separated sensors into two devices: **Pollen Types** and **Plants** per location.  
- Assigned distinct icons for `pollenTypeInfo` codes (GRASS, TREE, WEED).  
- Assigned icons in *plant* sensors based on `type` attribute, falling back to default flower icon.  
- Exposed additional attributes on *plant* sensors: `inSeason`, `type`, `family`, `season`.
### Breaking Changes
- **REINSTALL REQUIRED**: Prior sensor and device entities must be **deleted** and the integration re-added to apply the new device grouping and attributes.

## [1.2.2] - 2025-05-21
### Fixed
- Changed `name=DOMAIN` to `name=f"{DOMAIN}_{entry_id}"` in sensor.py to allow multiple locations.

## [1.2.1] - 2025-05-20
### Added
- Translations
- More Entities

## [1.2.0] - 2025-05-20
- Repaired issue https://github.com/eXPerience83/pollenlevels/issues/2  
- Now Integration appears on config/integrations

## [1.1.0] - 2025-05-19
### Added
- `issue_tracker` URL in `manifest.json` so the UI links to GitHub issues.  
- Bumped `version` to 1.1.0 for clearer display in Integrations.

## [1.0.0] - 2025-05-19
### Added
- Dynamic sensors created from `plantInfo` array instead of fixed categories.  
- Removed hard‑coded allergen selection.  
- Simplified attributes to `value` and `category`.

## [0.1.0] - 2025-05-16
### Added
- Initial repository structure and manifest.
