<p align="center">
  <img src="https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/pollenlevels/icon.png" alt="Pollen Levels logo" width="140"/>
</p>

# 🌼 Pollen Levels Integration for Home Assistant

**Monitor real-time pollen levels** from the Google Maps Pollen API directly in Home Assistant.  
Get sensors for **grass**, **tree**, **weed** pollen, plus individual plants like **OAK**, **PINE**, **OLIVE**, and many more!

[![GitHub Release](https://img.shields.io/github/v/release/eXPerience83/pollenlevels)](https://github.com/eXPerience83/pollenlevels/releases)
[![License](https://img.shields.io/github/license/eXPerience83/pollenlevels)](LICENSE)
[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/integration)
[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/experience83) [![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://paypal.me/eXPerience83)

[![Open your Home Assistant instance and add this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eXPerience83&repository=pollenlevels&category=integration)

> **Good news!** Since **July 2025** this integration is part of the **HACS Default** repository. You no longer need to add it manually — just search for **Pollen Levels** in HACS and install it.

---

## 🌟 Features

- **Multi-language support** — UI in 9 languages (EN, ES, CA, DE, FR, IT, PL, RU, UK) + API responses in any language.  
- **Dynamic sensors** — Auto-creates sensors for all pollen types found in your location.  
- **Smart grouping** — Organizes sensors into:
  - **Pollen Types** (Grass / Tree / Weed)
  - **Plants** (Oak, Pine, Birch, etc.)
  - **Pollen Info** (Region / Date metadata)  
- **Configurable updates** — Change update interval and language without reinstalling.  
- **Manual refresh** — Call `pollenlevels.force_update` to trigger an immediate update and reset the timer.  
- **Last Updated sensor** — Shows timestamp of last successful update.  
- **Rich attributes** — Includes `inSeason`, UPI `description`, health `advice`, `color_hex`, and plant details.  

## ⚙️ Installation

### Via HACS (recommended)
1. Open **HACS → Integrations** in Home Assistant.  
2. Click **Explore & Download Repositories** (🔍).  
3. Search for **Pollen Levels** or click the badge above to open directly.  
4. Click **Download** and follow the prompts.  
5. Restart or *Reload* Home Assistant when prompted.

<details>
<summary>Manual installation (if HACS is not available)</summary>

1. Download the latest release from the [releases page](https://github.com/eXPerience83/pollenlevels/releases).  
2. Copy `custom_components/pollenlevels` into your Home Assistant `custom_components` folder.  
3. Restart Home Assistant.  

</details>

## 🔑 Configuration

1. Go to **Settings → Devices & Services → Add Integration**.  
2. Search for **Pollen Levels**.  
3. Enter:
   - **Google API Key**  
   - **Location** (auto-filled from HA config)  
   - **Update Interval** (hours)  
   - **Language Code** (e.g., `en`, `es`, `de`, `fr`, `uk`)  

## ⚙️ Options

You can change:
- **Update interval (hours)**
- **API response language code**  

Go to **Settings → Devices & Services → Pollen Levels → Configure**.  
Changes are saved and applied automatically.

## 🗝️ Getting a Google API Key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).  
2. Create or select a project and **enable Billing**.  
3. Enable the **Maps Pollen API**.  
4. Create an **API Key** under **Credentials**.  
5. *(Recommended)* Restrict the key to the **Maps Pollen API**.

## 🌐 Example API request

```bash
curl -X GET "https://pollen.googleapis.com/v1/forecast:lookup?key=YOUR_KEY&location.latitude=48.8566&location.longitude=2.3522&days=1&languageCode=es"
````

```json
{
  "regionCode": "FR",
  "dailyInfo": [{
    "date": {"year": 2025, "month": 5, "day": 20},
    "pollenTypeInfo": [
      {"code": "GRASS", "displayName": "Hierba", "indexInfo": {"value": 3, "category": "Moderate"}},
      {"code": "TREE", "displayName": "Árbol", "indexInfo": {"value": 2, "category": "Low"}}
    ],
    "plantInfo": [
      {"code": "OLIVE", "displayName": "Olivo", "indexInfo": {"value": 2, "category": "Low"}},
      {"code": "PINE", "displayName": "Pino", "indexInfo": {"value": 1, "category": "Very Low"}}
    ]
  }]
}
```

## ❤️ Support the project

If this integration helps you breathe easier (literally!), consider supporting further development:

[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/experience83)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://paypal.me/eXPerience83)

## 📜 License

MIT © 2025 [eXPerience83](LICENSE)

> **Data Source:** [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen)
