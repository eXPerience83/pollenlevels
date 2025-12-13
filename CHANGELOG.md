# Changelog
## [1.9.0-alpha1] - 2025-12-11
### Changed
- Moved runtime state to config entry `runtime_data` with a shared
  `GooglePollenApiClient` per entry while keeping existing sensor behaviour and
  identifiers unchanged.
- Updated sensors, diagnostics, and the `pollenlevels.force_update` service to
  read coordinators from runtime data so each entry reuses a single API client
  for Google Pollen requests.
- Treated HTTP 401 responses like 403 to surface `invalid_auth` during setup
  validation and runtime calls instead of generic connection errors.
- Restored API key validation during setup to raise `ConfigEntryAuthFailed`
  when the key is missing instead of retrying endlessly.
- Centralized config entry title normalization during setup so the cleaned
  device titles are reused across all sensors.
- Simplified metadata sensors by relying on inherited `unique_id` and
  `device_info` properties instead of redefining them.
- Updated the `force_update` service to queue coordinator refreshes via
  `async_request_refresh` and added service coverage for entries lacking
  runtime data.
- Cleared config entry `runtime_data` after unload to drop stale coordinator
  references and keep teardown tidy.

## [1.8.6] - 2025-12-09
### Changed
- Parallelized the `force_update` service to refresh all entry coordinators concurrently
  and log per-entry failures without aborting other updates.
- Aligned `force_update` refresh result logging to the entries that spawned refresh
  tasks so errors are attributed correctly.
- Clarified tooling-versus-runtime Python guidance to keep integration code compatible
  with Home Assistant's Python 3.13 floor while tooling targets Python 3.14+.
- Added Home Assistant type hints for sensor setup and coordinator helpers while
  guarding imports so the lightweight test harness runs without the full Home
  Assistant package installed.
- Hardened tests by enforcing `requires-python` 3.14+, verifying sensor device
  metadata trims or defaults titles, strengthening the asyncio test hook and stubs,
  and stamping stub coordinators with placeholder `last_updated` values.
- Raised the minimum Home Assistant requirement to 2025.3.0 and finalized the
  integration version at 1.8.6.
- Simplified runtime validation by relying on config and options flows for coordinates
  and forecast ranges while keeping only a minimal guard for missing entries.
- Consolidated per-day cleanup coverage into a single parametrized test covering
  D+1/D+2 removal combinations without duplicating setup code.

## [1.8.5] - 2025-12-06
### Changed
- Sanitized map selector defaults and suggested values to drop invalid Home Assistant
  coordinates instead of pre-filling the map at (0,0) or an empty location, keeping setup
  reliable even when core location settings are missing.
- Normalized config entry titles and device translation placeholders to fall back to the
  default name when users supply blank or whitespace-only titles, preventing empty device
  labels in the UI.
- Cleared stale `error_message` placeholders when unexpected errors surface as `unknown`
  in the config flow to avoid misleading details in the setup form.
- Trimmed whitespace-only names in the ConfigEntry test stub to mirror runtime title handling
  and keep test behavior aligned with production.
- Avoided suggesting null map coordinates when Home Assistant has no valid location, keeping
  the selector empty until the user picks a point.
- Simplified user-facing connection errors during setup by removing raw HTTP status codes from
  the `error_message` placeholder while retaining detailed logging for debugging.
- Hardened the map selector defaults to validate Home Assistant coordinates and fall back to a
  safe entry title when core configuration values are missing or invalid, keeping setup usable
  in edge cases.
- Expanded the Home Assistant constant test stub with common config keys to improve isolation of
  sensor tests without altering runtime behavior.
- Fixed legacy coordinate validation to surface `invalid_coordinates` on the appropriate field
  (map `location` when present; base-level only for legacy lat/lon reauth forms), and aligned the
  longitude test stub with Home Assistant's invalid-type behavior. Unexpected validation errors
  now map to `unknown`.
- Simplified options-flow connectivity errors to use generic localized messages without the
  `error_message` placeholder, keeping detailed HTTP context limited to setup and
  reauthentication flows.
- Updated `invalid_coordinates` translations across all locales to reference selecting a valid
  location on the map instead of entering raw latitude/longitude values.
- Removed the unused entry-name constant and cleaned up import declarations to drop dead code
  without altering entity identifiers.
- Removed the unused `options.error.invalid_coordinates` translation key across all locales to
  keep translation strings aligned with the current options flow.
- Options flow descriptions now show the config entry title and unexpected validation errors map
  to the generic `unknown` message instead of implying connectivity failures.
- Switched the setup form to a map-based location selector that defaults to the Home Assistant
  location name and coordinates while validating latitude/longitude with Home Assistant helpers.
- Updated config-flow messaging and translations to reflect the new map selector and include richer
  connection and location validation errors.
- Added sanitized `error_message` placeholders to `cannot_connect` responses in the config and
  reauthentication flows so users see short reasons for HTTP, timeout, and malformed response
  failures without exposing secrets.
- Updated the remaining locale setup descriptions to reference selecting a location on the map
  instead of entering latitude and longitude manually.
- Replaced Home Assistant common translation placeholders with explicit labels across all locales
  so the custom integration strings render correctly in setup and options.
- Device names now include the config entry title (for example, "Home – Pollen Types") while
  keeping identifiers unchanged for existing entities.

### Added
- Expanded config flow tests to cover map selector input, coordinate edge cases, and connectivity
  failures while ensuring normalized coordinates are stored in entries.
- Regression coverage ensuring `error_message` is set when validation maps to `cannot_connect`,
  keeping the new placeholder behavior guarded.

## [1.8.4] - 2025-11-27
### Fixed
- Added a bounds check to the sensor test SequenceSession helper so exhausting the
  fake response list raises a clear AssertionError instead of an IndexError.
- Added metadata consistency tests to keep the package name/version aligned with
  the manifest and catch missing fields early in CI.
- Corrected the manifest JSON formatting so metadata parses cleanly without
  trailing separators.

## [1.8.3] - 2025-11-24
### Fixed
- Stop logging coordinate values through the invalid-coordinate exception message in the config
  flow; messages are now static and fully redacted.
- Redacted raw coordinates from the "Unique ID setup failed" error log in the config flow to
  strictly align with the integration's privacy standards.
- Stop logging raw latitude/longitude in config-flow coordinate warnings; values are now redacted
  to better align with the integration's privacy guarantees.
- Keep the approximate diagnostics location visible by renaming rounded coordinates to dedicated
  keys and reducing precision to a single decimal place for better privacy.

### Changed
- Added an approximate, rounded location to diagnostics so support can review rough geography
  without exposing precise coordinates while keeping exact values redacted.
- Moved the `force_update` service name and description into translation files and added English and
  Spanish entries to improve internationalization.
- Synced the manifest version with the release notes to prepare the stable 1.8.3 release.

## [1.8.2] - 2025-11-15
### Fixed
- Detect config entries missing the API key during sensor setup and raise
  `ConfigEntryAuthFailed` immediately so Home Assistant prompts for
  reauthentication instead of crashing with `KeyError`.
- Let `ConfigEntryAuthFailed` escape the setup wrapper so Home Assistant immediately prompts for
  reauthentication when the forwarded sensor platform reports invalid credentials.
- Validate latitude/longitude inside the config-flow error handling so invalid coordinates surface a
  localized `invalid_coordinates` error instead of crashing the form.
- Enforce geographic range limits (±90°, ±180°) on latitude/longitude during validation so
  impossible coordinates are rejected before hitting the API.
- Restrict the Date sensor's ISO parsing handler to `ValueError`/`TypeError` so unexpected issues
  propagate while malformed payloads still log a clear error.
- Config-flow credential validation now evaluates the HTTP status before decoding the body, avoiding
  large/binary logging on failures and ensuring missing `dailyInfo` is handled as a clean
  `cannot_connect` error.

### Added
- Regression tests validating the setup wrapper propagates authentication failures while still
  wrapping unexpected exceptions in `ConfigEntryNotReady`.
- Config-flow regression coverage ensuring non-numeric coordinates are rejected with the new
  translation-aware error key, which is localized across every language file.
- Added regression coverage for out-of-range coordinates to keep the validation logic honest when
  latitude/longitude exceed physical limits.

### Changed
- Removed unused reauthentication step strings so locales only maintain the confirmation form that
  users interact with during credential refreshes.
- Simplified the pollen-type metadata fallback helper by relying on closure variables, improving
  readability without changing behavior.
- Streamlined the pollen-type metadata lookup to scan each forecast day once, reducing branching and
  keeping the fallback path easier to follow.

## [1.8.1] - 2025-11-12
### Added
- Allow configuring a friendly entry name during setup so new installations appear with personalized
  titles out of the box.

### Changed
- Localized the entry-name field across every supported language to keep the setup form consistent
  worldwide.

## [1.8.0] - 2025-11-11
### Fixed
- Prevent completing setup with empty pollen data by raising `ConfigEntryNotReady` until the API
  includes daily information, ensuring entities populate correctly.
- Rebuild pollen type metadata from future forecast days when today lacks `dailyInfo`, keeping
  sensors classified as `source="type"` with their forecast attributes.
- Treat 403 authentication failures from the Google Pollen API as `ConfigEntryAuthFailed` so Home
  Assistant immediately prompts for re-authentication instead of leaving the entry broken.
- Prevent crashes while redacting API keys when providers return non-UTF-8 payloads by decoding
  bytes with replacement before sanitizing logs.
- Restore the re-authentication reload path by updating entries and reloading them separately,
  avoiding AttributeError from the previous helper call.
- Surface canonical BCP-47 validation errors with localized messaging instead of raw exception text,
  covering every translation file.
- Ensure stale D+1/D+2 entities are actually removed by awaiting entity-registry cleanup before
  finishing setup adjustments.
- Localize the reauthentication confirmation form so translated titles and descriptions appear when
  refreshing credentials.

### Added
- Regression tests covering single-day and multi-day API payload shaping to ensure pollen type
  sensors retain forecast metadata when only future indices are available.
- Regression coverage for plant forecast attributes so plant sensors continue to expose trend, peak,
  and per-day values.

### Changed
- Unique ID assignment now logs a redacted stack trace and aborts setup on unexpected failures while
  still handling normal duplicate locations gracefully.
- Validation timeout aligns with the coordinator ceiling (`ClientTimeout(total=10)`) so probing the
  API cannot hang longer than runtime refreshes.
- Added a dedicated re-authentication step that reuses validation logic, only requests the API key,
  and reloads the entry automatically once credentials are refreshed.
- Centralized API-key redaction into a shared helper reused by the config flow, coordinator, and
  diagnostics for consistent logging hygiene.
- Continuous-integration workflows now install the latest Black and Ruff releases to inherit
  upstream bug fixes without manual updates.

## [1.7.18] - 2025-09-11
### Security
- **GitHub Actions (least privilege):** add explicit `permissions: { contents: read }` to `lint.yml`
  to satisfy CodeQL’s `actions/missing-workflow-permissions`.
- Stop logging raw request parameters (coordinates/key) in `sensor.py` and `config_flow.py`. Debug
  logs now include only non-sensitive metadata (`days`, `lang_set`). Fixes CodeQL “clear-text
  logging of sensitive information”.


## [1.7.17] - 2025-09-10
### Changed
- **Code Refinement**: Improved readability of a filter in the diagnostics module. No functional
  change.
- **Services**: Added a `name` to the `force_update` service for a clearer presentation in the
  Developer Tools UI.

## [1.7.16] - 2025-09-09
### Fixed
- Color parsing: treat empty or channel-less `indexInfo.color` as **absent** instead of `#000000`.
  Prevents misleading black when the API omits color.

## [1.7.15] - 2025-09-09
### Fixed
- **Diagnostics**: Use `DEFAULT_FORECAST_DAYS` instead of a hard-coded fallback to avoid drift when
  defaults change.
### Changed
- **Diagnostics**: Added `days` to `forecast_summary.type` (already present for `plant`) for
  structural symmetry and easier troubleshooting.
- **Sensors**: Enabled `_attr_has_entity_name = True` for `PollenSensor` so Home Assistant composes
  names as “Device • Entity” (modern UI pattern). No impact on `entity_id`/`unique_id` or device
  grouping.
- **Manifest**: Bump version to `1.7.15` and add `integration_type: "service"` for clearer
  classification in Home Assistant.

## [1.7.14] - 2025-09-09
### Fixed
- i18n wording consistency: CA, PT-BR, PL, RU, IT, NB.
  - Catalan: typographic apostrophes in “l’interval / l’idioma”.
  - pt-BR: “chave da API do Google”.
  - Polish: “odpowiedzi API” + natural title.
  - Russian: “Это местоположение...” for “location”.
  - Italian: “Opzioni dei sensori...” and “Informazioni sul polline”.
  - Norwegian Bokmål: “Dette stedet...”.

## [1.7.13] - 2025-09-09
### Fixed
- i18n wording/consistency: CA, ES, DE, FR, NL, RU, UK, PT-PT.
  - Natural titles and API phrasing (e.g., “response of the API”).
  - Removed hidden soft hyphen in Dutch device name (“Pollentypen”).

## [1.7.12] - 2025-09-07
### Added
- Translations: **sv**, **cs**, **pt-BR**, **da**, **nb**, **pt-PT**, **ro**, **fi**, **hu**,
  **zh-Hant**.
### Changed
- No functional changes; translation keys match `en.json`.

## [1.7.11] - 2025-09-06
### Added
- Translations: **Dutch (nl)** and **Chinese (Simplified, zh-Hans)**.

## [1.7.10] - 2025-09-06
### Changed
- Service `pollenlevels.force_update`: added `vol.Schema({})` to enforce an empty payload and
  provide clearer validation errors. No functional impact for valid calls.

## [1.7.9] - 2025-09-06
### Fixed
- **Date sensor**: Return a `datetime.date` object for `device_class: date` (was a string). Ensures
  correct UI formatting and automation compatibility.

## [1.7.8] - 2025-09-05
### Changed
- **Date sensor**: Set `device_class: date` so Home Assistant treats the value as a calendar date
  (UI semantics/formatting). No functional impact.
- > Note: 1.7.8 set `device_class: date` but still returned a string. This was corrected in 1.7.9 to
  return a proper `date` object.

## [1.7.7] - 2025-09-05
### Changed
- **Performance/cleanup**: Precompute static attributes for metadata sensors:
  - Set `_attr_unique_id` and `_attr_icon` in `RegionSensor`, `DateSensor`, and `LastUpdatedSensor`.
  - Set `_attr_device_info` once in `_BaseMetaSensor`.
  - Also set `_attr_unique_id` in `PollenSensor` for consistency.
  These changes avoid repeated property calls and align with modern HA entity patterns. No functional impact.

## [1.7.6] - 2025-09-05
### Changed
- **UI polish**: Mark **Region** and **Date** sensors as `diagnostic` to better reflect their
  metadata nature.
- **Display**: Add `suggested_display_precision: 0` to pollen sensors so values are shown as
  integers (this does not affect statistics or storage).

## [1.7.5] - 2025-09-04
### Changed
- **Sensors**: Migrate to `SensorEntity` and use `native_value` across all sensors for better
  alignment with modern HA patterns.
- **Statistics**: Set `state_class: measurement` on main pollen sensors to enable long-term
  statistics.
- **Last Updated**: Switch to `device_class: timestamp` and return a `datetime` object so the
  frontend formats it automatically.

## [1.7.4] - 2025-09-04
### Fixed
- **Config Flow**: avoid double-consuming the HTTP body during API validation (switched to single
  read + `json.loads`). Prevents sporadic validation failures with `cannot_connect`.

## [1.7.3] - 2025-09-04
### Changed
- **Sensors**: Hide forecast-related attributes (`forecast`, `tomorrow_*`, `d2_*`, `trend`,
  `expected_peak`) when **Forecast days = 1** to keep entities clean and concise.
- If you referenced `tomorrow_has_index` in templates with `forecast_days=1`, the attribute is now
  absent instead of `false`.

## [1.7.2] - 2025-09-01
### Fixed
- **Diagnostics**: redact `location.latitude`/`location.longitude` inside the request example to
  avoid leaking coordinates in exports.

## [1.7.1] - 2025-09-01
### Changed
- Internal refactor: centralize forecast attribute building for TYPES & PLANTS into a single helper
  to reduce duplication and ensure parity.
- Logging: add a top-level INFO when `pollenlevels.force_update` is invoked.
- No behavior changes; entities, attributes, and options remain identical.

## [1.7.0] - 2025-08-31
### Fixed
- TYPE per-day sensors (D+1/D+2) now use the **correct day's** `inSeason` and `advice` instead of
  inheriting today's values.
### Added
- **Plant forecast (attributes only):** plant sensors now include `forecast`, `tomorrow_*`, `d2_*`,
  `trend`, and `expected_peak`, mirroring TYPE sensors.
### Changed
- No new plant entities are created; forecast is available via attributes to keep entity count low.

## [1.6.5] - 2025-08-26
### Fixed
- Timeouts: catch built-in **`TimeoutError`** in Config Flow and Coordinator.  
  On Python 3.14 this also covers `asyncio.TimeoutError`, so listing both is unnecessary (and auto-removed by ruff/pyupgrade).
- Added missing `options.error` translations across all locales so **Options Flow** errors display
  localized.
- **Security**: Config Flow now sanitizes exception messages (including connection/timeout errors)
  to avoid leaking the API key in logs; explicit handling of `TimeoutError` returns a clean
  `cannot_connect`.
- **Parsers**: Skip `plantInfo` entries without `code` to prevent unstable keys (`plants_`) and
  silent overwrites.
- **Defensive access**: Use safe dictionary access in sensor properties to avoid rare `KeyError`
  during concurrent refreshes.
- **Localization**: Added `config.abort.already_configured` in all locales to localize the
  duplicate-location abort reason.
### Changed
- Improved wording for `create_forecast_sensors` across all locales:
  - Field label now clarifies it’s the **range** for per-day TYPE sensors.
  - Step description explains each choice with plain language:
    - **Only today (none)**, **Through tomorrow (D+1)**, **Through day after tomorrow (D+2)** (and local equivalents).
### Changed
- Minimal safe backoff in coordinator: single retry on transient failures (**TimeoutError**,
  `aiohttp.ClientError`, `5xx`).
  For **429**, honor numeric `Retry-After` seconds (capped at **5s**) or fall back to ~**2s** plus small jitter.

## [1.6.4] - 2025-08-22
### Fixed
- **Config Flow validation timeout**: Added `ClientTimeout(total=15)` to prevent UI hangs if the
  provider stalls.
- **Coordinator hardening**: Sanitized exception messages and logs to avoid accidental API key
  leakage; explicit `ClientTimeout(total=10)` on fetch.
### Added
- **Diagnostics**: New `diagnostics.py` with secret redaction (API key and location) and coordinator
  snapshot.

## [1.6.3] - 2025-08-22
### Fixed
- Language validation now accepts common **BCP-47** forms (e.g., `zh-Hant-TW`, `es-419`) and relies
  on the API’s **closest-match** fallback when a sub-locale is unavailable.
- **Language normalization**: both Setup and Options now **persist the trimmed language** (e.g., `"
  es "` → `"es"`), and the coordinator **omits** `languageCode` if empty after normalization.
- **Entity cleanup**: remove stale per-day TYPE sensors `(D+1)/(D+2)` from the **Entity Registry**
  on entry setup when options no longer request them or `forecast_days` is insufficient. Prevents
  “Unavailable” leftovers after Options → Reload.
- **Options validation**: show a **field-level** error for `forecast_days` when the chosen value is
  incoherent, instead of a generic base error.
- **Config step parity**: initial setup now allows an **empty** `language_code` (same as Options).
  When empty, validation is skipped and `languageCode` is not sent to the API during the probe.
### Changed
- **Icons (plants)**: normalize `type` to uppercase to map icons consistently.
- **Translations**: minor wording fixes in **CA** and **IT** titles.

## [1.6.2] - 2025-08-14
### Changed
- **Options Flow**: unify D+1 / D+2 toggles into a single selector `create_forecast_sensors` with
  values `none` (default), `D+1`, `D+1+2`.
- Validation ensures `forecast_days` covers the selected per-day sensors.  
- Updated translations (EN/ES/CA/DE/FR/IT/PL/RU/UK).  

## [1.6.0] - 2025-08-14
### Added
- Multi-day forecast for pollen **TYPES** (GRASS/TREE/WEED):  
  - `forecast` attribute with entries (`offset`, `date`, `has_index`, `value`, `category`,
    `description`, `color_*`).
  - Convenience: `tomorrow_*` and `d2_*`  
  - Derived: `trend` and `expected_peak`  
  - **Optional** per-day TYPE sensors for **(D+1)** and **(D+2)**.  

### Changed
- Plant forecasts remain current-day only in 1.6.0. Future expansion planned.  

## [1.5.5] - 2025-08-11
### Changed
- **button-card example**: fixed JavaScript snippets to access entity state correctly and use proper
  `color` property.
- Clarified native vs. custom color handling in README.
- No code changes; documentation-only release.

## [1.5.4] - 2025-08-10
### Fixed
- **Color extraction**: `color_hex` is now always produced even if the API omits channels. Missing
  channels default to `0`. Supports floats (`0..1`) and integers (`0..255`).

### Added
- Attributes for better Lovelace integration:  
  - `color_rgb`: `[R, G, B]` integers (0–255).  
  - `color_raw`: original API color dict.  

### Changed
- Updated UI examples:  
  - Removed invalid `template` card.  
  - Clarified Markdown limitations with inline CSS.  
  - Added working examples for **Mushroom** and **button-card**.  
  - Kept native **Entities**, **Tile + Template Sensor**, and **Gauge**.  

## [1.5.3] - 2025-08-09
### Added
- **Type sensors**: new attributes `inSeason`, `advice` (health recommendations), and `color_hex`.  
- **Plant sensors**: new attributes `advice`, `color_hex`, `code`, `picture`, `picture_closeup`.  

## [1.5.2] - 2025-08-09
### Added
- Full localization of Options Flow strings in 9 languages (EN, ES, CA, DE, FR, IT, PL, RU, UK).  

## [1.5.1] - 2025-08-08
### Added
- **Index description attribute**: All sensors expose `description` (UPI index info).  

## [1.5.0] - 2025-08-08
### Added
- **Options Flow**: change `update_interval` and `language_code` without reinstalling.  
- **Duplicate prevention**: entries uniquely identified by `(latitude, longitude)`.  

### Changed
- Options reload integration automatically after saving.  

## [1.4] - 2025-06-21
### Changed
- Core sensors **Region**, **Date**, **Last Updated** now use `translation_key` for localization.  
- No more hard-coded names: entities are translated automatically across all supported languages.  

## [1.3.8.3] - 2025-06-21
### Added
- Multi-language support for device and entity names (EN, ES, CA, DE, FR, IT, PL, RU, UK).  

## [1.3.8.2] - 2025-06-21
### Fixed
- Moved **Last Updated** sensor to Diagnostics category.  
- Reused HA HTTP session in coordinator.  
- `async_refresh()` used in `force_update`.  

## [1.3.8] - 2025-06-16
### Added
- **pollenlevels.force_update** service.  
- **Last Updated** sensor with timestamp of last fetch.  

## [1.3.7.1] - 2025-05-29
### Added
- New **plant sensor attribute**: `cross_reaction`.  

### Fixed
- Critical syntax error in `config_flow.py`.  
- Improved language validation error handling and logging.  

## [1.3.6] - 2025-05-29
### Fixed
- Translation key placement error (`empty` moved to `error` section).  
- Regex updated to support 3-letter codes (`cmn`) and case-insensitive matching.  

## [1.3.5] - 2025-05-27
### Added
- New **Region** and **Date** metadata sensors.  

### Fixed
- Restored config flow UI compatibility by moving language validation outside schema.  

## [1.3.0] - 2025-05-22
### Added
- Optional `language_code` field in config.  
- Split sensors into **Pollen Types** and **Plants** devices.  
- Icons assigned to pollen types and plants.  
- Plant sensors expose extra attributes (`inSeason`, `type`, `family`, `season`).  

### Changed
- **Reinstall required**: entities must be removed and integration re-added due to device
  regrouping.

## [1.2.0] - 2025-05-20
### Added
- Integration now appears in HA Config → Integrations.

## [1.0.0] - 2025-05-19
### Added
- Initial release with dynamic sensors from `plantInfo`.
