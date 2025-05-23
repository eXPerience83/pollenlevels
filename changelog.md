# Changelog

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
