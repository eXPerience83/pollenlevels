# Pollen Levels Integration for Home Assistant

A custom integration for [Home Assistant](https://www.home-assistant.io) that fetches pollen data from the Google Maps Pollen API.

It creates one sensor per pollen type (e.g. grass, tree, weed, plus individual plant codes like OAK, PINE, etc.) and groups them under a single device representing your location.

---

## Features

- **Current pollen levels** (Universal Pollen Index) for grass, tree, weed  
- **Individual plant‑type sensors** (e.g. OAK, PINE, BIRCH, etc.) with value & category  
- Configurable update interval (default: 6 hours)  
- Automatic device grouping by location  
- No YAML configuration—setup entirely via UI  
- HACS‑compatible  
- **Multi-language support** for configuration UI (English, Spanish, Catalan, German, French, Italian, Polish)

---

## Installation

### HACS (preferred)

1. In HACS, go to **Integrations** → three‑dot menu → **Custom repositories**.  
2. Add this repository URL:  
   ```
   https://github.com/eXPerience83/pollenlevels
   ```  
3. Choose **Integration** as category and click **Add**.  
4. In **Integrations**, search for **Pollen Levels** and install.  
5. Restart Home Assistant.

### Manual

1. Copy the `pollenlevels` folder into `config/custom_components/`.  
2. Ensure the structure is:
   ```
   config/
   └── custom_components/
       └── pollenlevels/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── manifest.json
           ├── sensor.py
           └── translations/
               ├── en.json
               ├── es.json
               ├── ca.json
               ├── de.json
               ├── fr.json
               ├── it.json
               └── pl.json
   assets/
     └── logo.png
   hacs.json
   README.md
   ```

3. Restart Home Assistant.

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.  
2. Search **Pollen Levels**.  
3. Enter:
   - **Google API Key**  
   - **Latitude** & **Longitude** (defaults to Home Assistant’s configured location)  
   - **Update interval** in hours (default: 6)
   - **Language Code** for the API response (en, es, de, ca, …).

Once configured, you’ll see a device named `Pollen Levels (LAT,LON)` under **Devices**, with one sensor per pollen code under **Entities**.

---

## Obtaining a Google API Key

1. Open the [Google Cloud Console](https://console.cloud.google.com/).  
2. Create (or select) a project with billing enabled.  
3. Go to **APIs & Services → Library**, enable **Maps Pollen API**.  
4. In **APIs & Services → Credentials**, click **Create credentials → API key**.  
5. (Recommended) Restrict key to **Maps Pollen API**.  
6. Use this key when setting up the integration.

---

## API Endpoints

- **Forecast lookup** (use for both current levels and forecast for up to 5 days):
  ```
  GET https://pollen.googleapis.com/v1/forecast:lookup
      ?key={API_KEY}
      &location.latitude={LAT}
      &location.longitude={LON}
      &days={N}
  ```
  - **days**: number of days (1 for today only)

The response includes:

- **dailyInfo[n].pollenTypeInfo** → UPI per pollen category (`GRASS`, `TREE`, `WEED`)
- **dailyInfo[n].plantInfo** → individual plant codes (`OAK`, `PINE`, `BIRCH`, …), with:
  - `indexInfo.value` → numeric index  
  - `indexInfo.category` → one of:  
    `"Very Low"`, `"Low"`, `"Moderate"`, `"High"`, `"Very High"`

See Google’s docs for full details:  
- [Pollen Forecast](https://developers.google.com/maps/documentation/pollen/forecast)  
- [Pollen Index](https://developers.google.com/maps/documentation/pollen/pollen-index)

---

## Donations

If you find this integration useful and would like to support its development, please consider donating:
- [PayPal](https://paypal.me/eXPerience83)
- [Ko-fi](https://ko-fi.com/experience83)

---

## License

This project is licensed under the **MIT License**.  
See [LICENSE](LICENSE) for details.

---

## Credits

Built by @eXPerience83 using the **Google Maps Pollen API** and the Home Assistant integration framework.
