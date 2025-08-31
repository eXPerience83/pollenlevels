# Changelog

## [1.7.0] – 2025-08-31
### Added
- **Plant forecast (attributes only):** plant sensors now include `forecast`, `tomorrow_*`, `d2_*`, `trend`, and `expected_peak`, mirroring TYPE sensors.
### Notes
- No new plant entities are created; forecast is available via attributes to keep entity count low.

## [1.6.5] – 2025-08-26
### Fixed
- Timeouts: catch built-in **`TimeoutError`** in Config Flow and Coordinator.  
  On Python 3.11 this also covers `asyncio.TimeoutError`, so listing both is unnecessary (and auto-removed by ruff/pyupgrade).
- Added missing `options.error` translations across all locales so **Options Flow** errors display localized.
- **Security**: Config Flow now sanitizes exception messages (including connection/timeout errors) to avoid leaking the API key in logs; explicit handling of `TimeoutError` returns a clean `cannot_connect`.
- **Parsers**: Skip `plantInfo` entries without `code` to prevent unstable keys (`plants_`) and silent overwrites.
- **Defensive access**: Use safe dictionary access in sensor properties to avoid rare `KeyError` during concurrent refreshes.
- **Localization**: Added `config.abort.already_configured` in all locales to localize the duplicate-location abort reason.
### Changed
- Improved wording for `create_forecast_sensors` across all locales:
  - Field label now clarifies it’s the **range** for per-day TYPE sensors.
  - Step description explains each choice with plain language:
    - **Only today (none)**, **Through tomorrow (D+1)**, **Through day after tomorrow (D+2)** (and local equivalents).
### Reliability
- Minimal safe backoff in coordinator: single retry on transient failures (**TimeoutError**, `aiohttp.ClientError`, `5xx`).
  For **429**, honor numeric `Retry-After` seconds (capped at **5s**) or fall back to ~**2s** plus small jitter.

## [1.6.4] – 2025-08-22
### Fixed
- **Config Flow validation timeout**: Added `ClientTimeout(total=15)` to prevent UI hangs if the provider stalls.
- **Coordinator hardening**: Sanitized exception messages and logs to avoid accidental API key leakage; explicit `ClientTimeout(total=10)` on fetch.
### Added
- **Diagnostics**: New `diagnostics.py` with secret redaction (API key and location) and coordinator snapshot.

## [1.6.3] – 2025-08-22
### Fixed
- Language validation now accepts common **BCP-47** forms (e.g., `zh-Hant-TW`, `es-419`) and relies on the API’s **closest-match** fallback when a sub-locale is unavailable.  
- **Language normalization**: both Setup and Options now **persist the trimmed language** (e.g., `" es "` → `"es"`), and the coordinator **omits** `languageCode` if empty after normalization.  
- **Entity cleanup**: remove stale per-day TYPE sensors `(D+1)/(D+2)` from the **Entity Registry** on entry setup when options no longer request them or `forecast_days` is insufficient. Prevents “Unavailable” leftovers after Options → Reload.  
- **Options validation**: show a **field-level** error for `forecast_days` when the chosen value is incoherent, instead of a generic base error.  
- **Config step parity**: initial setup now allows an **empty** `language_code` (same as Options). When empty, validation is skipped and `languageCode` is not sent to the API during the probe.  
### Improved
- **Icons (plants)**: normalize `type` to uppercase to map icons consistently.
- **Translations**: minor wording fixes in **CA** and **IT** titles.

## [1.6.2] – 2025-08-14
### Changed
- **Options Flow**: unify D+1 / D+2 toggles into a single selector `create_forecast_sensors` with values `none` (default), `D+1`, `D+1+2`.  
- Validation ensures `forecast_days` covers the selected per-day sensors.  
- Updated translations (EN/ES/CA/DE/FR/IT/PL/RU/UK).  

## [1.6.0] – 2025-08-14
### Added
- Multi-day forecast for pollen **TYPES** (GRASS/TREE/WEED):  
  - `forecast` attribute with entries (`offset`, `date`, `has_index`, `value`, `category`, `description`, `color_*`).  
  - Convenience: `tomorrow_*` and `d2_*`  
  - Derived: `trend` and `expected_peak`  
  - **Optional** per-day TYPE sensors for **(D+1)** and **(D+2)**.  

### Notes
- Plant forecasts remain current-day only in 1.6.0. Future expansion planned.  

## [1.5.5] – 2025-08-11
### Docs
- **button-card example**: fixed JavaScript snippets to access entity state correctly and use proper `color` property.  
- Clarified native vs. custom color handling in README.  

### Notes
- No code changes; documentation-only release.  

## [1.5.4] – 2025-08-10
### Fixed
- **Color extraction**: `color_hex` is now always produced even if the API omits channels. Missing channels default to `0`. Supports floats (`0..1`) and integers (`0..255`).  

### Added
- Attributes for better Lovelace integration:  
  - `color_rgb`: `[R, G, B]` integers (0–255).  
  - `color_raw`: original API color dict.  

### Docs
- Updated UI examples:  
  - Removed invalid `template` card.  
  - Clarified Markdown limitations with inline CSS.  
  - Added working examples for **Mushroom** and **button-card**.  
  - Kept native **Entities**, **Tile + Template Sensor**, and **Gauge**.  

## [1.5.3] – 2025-08-09
### Added
- **Type sensors**: new attributes `inSeason`, `advice` (health recommendations), and `color_hex`.  
- **Plant sensors**: new attributes `advice`, `color_hex`, `code`, `picture`, `picture_closeup`.  

## [1.5.2] – 2025-08-09
### Added
- Full localization of Options Flow strings in 9 languages (EN, ES, CA, DE, FR, IT, PL, RU, UK).  

## [1.5.1] – 2025-08-08
### Added
- **Index description attribute**: All sensors expose `description` (UPI index info).  

## [1.5.0] – 2025-08-08
### Added
- **Options Flow**: change `update_interval` and `language_code` without reinstalling.  
- **Duplicate prevention**: entries uniquely identified by `(latitude, longitude)`.  

### Notes
- Options reload integration automatically after saving.  

## [1.4] – 2025-06-21
### Changed
- Core sensors **Region**, **Date**, **Last Updated** now use `translation_key` for localization.  
- No more hard-coded names: entities are translated automatically across all supported languages.  

## [1.3.8.3] – 2025-06-21
### Added
- Multi-language support for device and entity names (EN, ES, CA, DE, FR, IT, PL, RU, UK).  

## [1.3.8.2] – 2025-06-21
### Fixed
- Moved **Last Updated** sensor to Diagnostics category.  
- Reused HA HTTP session in coordinator.  
- `async_refresh()` used in `force_update`.  

## [1.3.8] – 2025-06-16
### Added
- **pollenlevels.force_update** service.  
- **Last Updated** sensor with timestamp of last fetch.  

## [1.3.7.1] – 2025-05-29
### Added
- New **plant sensor attribute**: `cross_reaction`.  

### Fixed
- Critical syntax error in `config_flow.py`.  
- Improved language validation error handling and logging.  

## [1.3.6] – 2025-05-29
### Fixed
- Translation key placement error (`empty` moved to `error` section).  
- Regex updated to support 3-letter codes (`cmn`) and case-insensitive matching.  

## [1.3.5] – 2025-05-27
### Added
- New **Region** and **Date** metadata sensors.  

### Fixed
- Restored config flow UI compatibility by moving language validation outside schema.  

## [1.3.0] – 2025-05-22
### Added
- Optional `language_code` field in config.  
- Split sensors into **Pollen Types** and **Plants** devices.  
- Icons assigned to pollen types and plants.  
- Plant sensors expose extra attributes (`inSeason`, `type`, `family`, `season`).  

### Breaking Changes
- **Reinstall required**: entities must be removed and integration re-added due to device regrouping.  

## [1.2.0] – 2025-05-20
- Integration now appears in HA Config → Integrations.  

## [1.0.0] – 2025-05-19
- Initial release with dynamic sensors from `plantInfo`.
