# Home Assistant Pollen Levels Integration

This custom integration uses the **Google Maps Pollen API** to fetch pollen data.

**Repository:** https://github.com/eXPerience83/pollenlevels

## Features
- Current pollen levels for Grass, Tree, and Weed
- Configurable update interval (default 6 hours)
- Per-allergen sensors with attributes: level, category, timestamp, unit, location

## Installation (HACS)
1. HACS > Custom Repositories > Add URL:  
   `https://github.com/eXPerience83/pollenlevels`
2. Install **Pollen Levels**
3. Restart Home Assistant

## Configuration
Via UI (Settings > Devices & Services > Integrations > Add):
- Enter **API Key**, **Latitude**, **Longitude**
- Select one or more **Allergens**
- Set **Update Interval** (hours)

**Note:** YAML configuration is _not_ supported.

