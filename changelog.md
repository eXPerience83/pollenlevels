# Changelog

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
