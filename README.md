# 🌼 Pollen Levels Integration for Home Assistant

**Monitor real-time pollen levels** from the Google Maps Pollen API directly in Home Assistant.  
Get sensors for grass, tree, weed pollen, plus individual plants like OAK, PINE, OLIVE, and more!

[![GitHub Release][release-shield]][release-url]
[![License][license-shield]](LICENSE)
[![hacs][hacs-shield]][hacs-url]

[release-shield]: https://img.shields.io/github/release/eXPerience83/pollenlevels.svg?style=flat
[release-url]: https://github.com/eXPerience83/pollenlevels/releases
[license-shield]: https://img.shields.io/github/license/eXPerience83/pollenlevels.svg?style=flat
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat
[hacs-url]: https://hacs.xyz

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
- **Configurable updates**  
  Set refresh interval (default: 6 hours)
- **Rich attributes**  
  Includes season status, plant family, allergy info
- **Zero YAML**  
  Fully configurable via Home Assistant UI
- **HACS compatible**  
  Easy installation and updates

## ⚙️ Installation

### HACS (Recommended)
1. Go to **HACS → Integrations**
2. Click **⋮ → Custom repositories**
3. Add URL: `https://github.com/eXPerience83/pollenlevels`
4. Install **Pollen Levels** integration
5. **Restart** Home Assistant

### Manual
```bash
# Create directory
mkdir -p config/custom_components/pollenlevels

# Download integration
wget -O config/custom_components/pollenlevels.zip \
  https://github.com/eXPerience83/pollenlevels/archive/main.zip

# Unzip and cleanup
unzip -j config/custom_components/pollenlevels.zip '*/custom_components/pollenlevels/*' \
  -d config/custom_components/pollenlevels
rm config/custom_components/pollenlevels.zip
```

## 🔑 Configuration
1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Pollen Levels**
3. Enter:
   - **Google API Key** ([Get Key](#-obtaining-a-google-api-key))
   - **Location** (auto-filled from HA config)
   - **Update Interval** (hours)
   - **Language Code** (e.g., `en`, `es`, `de`, `fr`, `uk`)

## 🗝️ Obtaining a Google API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project → **Enable Billing**
3. Enable **Maps Pollen API**
4. Create **API Key** under *Credentials*
5. (Recommended) Restrict key to **Maps Pollen API**

## 🌐 API Response Example
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

## ❤️ Donations
If this integration helps you breathe easier (literally!), consider supporting development:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/experience83)  
[PayPal](https://paypal.me/eXPerience83)

## 📜 License
MIT © 2025 [eXPerience83](LICENSE)

> **Data Source**: [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen)
