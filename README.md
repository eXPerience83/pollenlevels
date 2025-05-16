# Home Assistant Pollen Levels Integration

This custom integration uses the **Google Maps Pollen API** to fetch pollen data.

## Features
- Fetches **current** pollen levels.
- Configurable update interval (default **6 hours**, configurable via options or YAML).
- Supports multiple allergens: `GRASS`, `TREE`, `WEED`, `MOLD`.
- Creates one sensor per allergen with attributes:
  - `level` (numeric pollen count)
  - `category` (low, medium, high)
  - `unit` (grains/m³)
  - `timestamp` (ISO 8601)
  - `location` (lat,lon)

## Installation (HACS)
1. Add this repo in **HACS > Custom Repositories** (category: Integration).
2. Install **Pollen Levels**.
3. Restart Home Assistant.

## Configuration
### UI
1. **Settings > Devices & Services > Add Integration**
2. Search **Pollen Levels**
3. Enter:
   - **API Key**
   - **Latitude**, **Longitude**
   - **Allergens**
   - **Update Interval** (hours)

### YAML
```yaml
sensor:
  - platform: pollenlevels
    api_key: YOUR_GOOGLE_API_KEY
    latitude: 39.4702
    longitude: -0.3768
    allergens:
      - GRASS
      - TREE
    update_interval: 6  # in hours
```

## Obtaining an API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select a project
3. Enable **Maps Pollen API**
4. Create an API key in **APIs & Services > Credentials**
5. (Optional) Restrict key
6. Add billing

## Update Frequency
- Default: **6 hours**
- Change via `update_interval`

## Forecast Support (Future)
- Forecast up to 5 days available via API
- Not yet implemented but feasible: create additional sensors or a forecast Lovelace card

## Requirements
- Internet access for Home Assistant
- User-provided API key with billing enabled
- No static IP or extra SSL needed
- Dependencies: `aiohttp`

## Lovelace Example
```yaml
type: entities
entities:
  - entity: sensor.pollen_grass
    name: Grass Pollen Level
```
