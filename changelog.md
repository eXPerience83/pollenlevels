# Changelog

## [1.1.0] - 2025-05-19
### Changed
- Dynamic sensors created from `plantInfo` array instead of fixed categories.
- Removed hard-coded allergen selection.
- Simplified attributes to `value` and `category`.

## [1.0.0] - 2025-05-19
- Initial implementation with fixed `pollenTypeInfo` sensors (GRASS, TREE, WEED).
- 
### Added
- Full integration with UI config flow and sensor platform
- Initial API credential validation in config flow
- Multi-select allergens: Grass, Tree, Weed
- Default update interval set to 6 hours
- Timestamp conversion to ISO format

### Fixed
- Use async_unload_platforms in `async_unload_entry`
- Specific handling for HTTP 403 (invalid_auth) and 429 (quota_exceeded)
- Validation of API response structure
- Removed redundant `async_update` method

## [0.1.0] - 2025-05-16
### Added
- Initial repository structure and manifest
