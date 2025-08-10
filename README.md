<p align="center">
  <img src="https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/pollenlevels/icon.png" alt="Pollen Levels logo" width="140"/>
</p>

# 🌼 Pollen Levels Integration for Home Assistant

**Monitor real‑time pollen levels** from the Google Maps Pollen API directly in Home Assistant.
Get sensors for grass, tree, weed pollen, plus individual plants like **OAK**, **PINE**, **OLIVE**, and many more!

[![GitHub Release][release-shield]][release-url]
[![License][license-shield]](LICENSE)
[![hacs\_badge][hacs-shield]][hacs-url]

[![Open your Home Assistant instance and add this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eXPerience83&repository=pollenlevels&category=integration)

[release-shield]: https://img.shields.io/github/release/eXPerience83/pollenlevels.svg?style=flat
[release-url]: https://github.com/eXPerience83/pollenlevels/releases
[license-shield]: https://img.shields.io/github/license/eXPerience83/pollenlevels.svg?style=flat
[hacs-shield]: https://img.shields.io/badge/HACS-Default-blue.svg?style=flat
[hacs-url]: https://github.com/hacs/integration
[downloads-shield]: https://img.shields.io/github/downloads/eXPerience83/pollenlevels/total.svg?style=flat
[downloads-latest-shield]: https://img.shields.io/github/downloads/eXPerience83/pollenlevels/latest/total.svg?style=flat

> **Good news!** Since **July 2025** this integration is part of the **HACS Default** repository. You no longer need to add it manually as a *Custom Repository* — just search for **Pollen Levels** directly in HACS and install it.

---

## 🌟 Features

- **Multi-language support**  
  UI available in 9 languages (EN, ES, CA, DE, FR, IT, PL, RU, UK) + API responses in any language
- **Dynamic sensors**  
  Auto-creates sensors for all pollen types found in your location
- **Smart grouping**  
  Organizes sensors into intuitive devices:
  - Pollen Types (Grass/Tree/Weed)
  - Plants (Oak/Pine/Birch/etc.)
  - Pollen Info (Region/Date metadata)
- **Configurable updates (Options Flow)**  
  Change update interval and language without reinstalling
- **Manual refresh**  
  Call the service `pollenlevels.force_update` to trigger an immediate update and reset the refresh timer.
- **Last Updated sensor**  
  Shows the timestamp of the last successful data fetch in local time.
- **Richer attributes (types & plants)**  
  `inSeason`, UPI `description`, `advice` (health recommendations), `color_hex`, and for plants also `code`, `picture`, `picture_closeup`.

## ⚙️ Installation

### Via HACS (recommended)

1. Open **HACS → Integrations** in Home Assistant.
2. Click **Explore & Download Repositories** (🔍 icon).
3. Search for **Pollen Levels** **or simply click the badge above** to open it directly.
4. Click **Download** and follow the prompts.
5. Restart or *Reload* Home Assistant when prompted.

<details>
<summary>Manual installation (only if you cannot use HACS)</summary>

1. Download the latest release from the [releases page][release-url].
2. Copy the `custom_components/pollenlevels` folder into your Home Assistant `custom_components` directory.
3. Restart Home Assistant.

</details>

## 🔑 Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Pollen Levels**.
3. Enter:

   * **Google API Key**
   * **Location** (auto‑filled from HA config)
   * **Update Interval** (hours)
   * **Language Code** (e.g. `en`, `es`, `de`, `fr`, `uk`)

## ⚙️ Options (interval & language)

After adding the integration, you can change:
- **Update interval (hours)**
- **API response language code** (e.g., `en`, `es`, `fr`, `de`, `uk`)

Open **Settings → Devices & Services → Pollen Levels → Configure**.
Changes are stored as entry options and automatically applied after the integration reloads.

## 🗝️ Obtaining a Google API Key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select a project and **enable Billing**.
3. Enable the **Maps Pollen API**.
4. Create an **API Key** under **Credentials**.
5. *(Recommended)* Restrict the key to the **Maps Pollen API**.

## 🌐 Example API request

```bash
curl -X GET "https://pollen.googleapis.com/v1/forecast:lookup?key=YOUR_KEY&location.latitude=48.8566&location.longitude=2.3522&days=1&languageCode=es"
```

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

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/experience83)  [![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal\&style=flat)](https://paypal.me/eXPerience83)

## 📜 License

MIT © 2025 [eXPerience83](LICENSE)

> **Data Source:** [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen)
