<p align="center">
  <img src="https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/pollenlevels/icon.png" alt="Pollen Levels logo" width="140"/>
</p>

# 🌼 Pollen Levels Integration for Home Assistant

**Monitor real-time pollen levels** from the Google Maps Pollen API directly in Home Assistant.  
Get sensors for **grass**, **tree**, **weed** pollen, plus individual plants like **OAK**, **PINE**, **OLIVE**, and many more!

[![GitHub Release](https://img.shields.io/github/v/release/eXPerience83/pollenlevels)](https://github.com/eXPerience83/pollenlevels/releases)
[![hassfest validation](https://github.com/eXPerience83/pollenlevels/actions/workflows/hassfest.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/eXPerience83/pollenlevels/actions/workflows/validate.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/eXPerience83/pollenlevels?logo=github)](https://github.com/eXPerience83/pollenlevels/blob/main/LICENSE)
[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/integration)
[![FAQ](https://img.shields.io/badge/FAQ-Read%20Here-blue?logo=readthedocs&logoColor=white)](https://github.com/eXPerience83/pollenlevels/blob/main/FAQ.md)
[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/experience83)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://paypal.me/eXPerience83)

[![Open your Home Assistant instance and add this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eXPerience83&repository=pollenlevels&category=integration)

---

## 🌟 Features

- **Multi-language support** — UI in 21 languages (**EN, ES, CA, DE, FR, IT, PL, RU, UK, NL, ZH-Hans, SV, CS, PT-BR, DA, NB, PT-PT, RO, FI, HU, ZH-Hant**) + API responses in any language.
- **Dynamic sensors** — Auto-creates sensors for all pollen types found in your location.  
- **Multi-day forecast for TYPES & PLANTS** —
  - `forecast` list with `{offset, date, has_index, value, category, description, color_*}`
  - Convenience: `tomorrow_*` and `d2_*`
  - Derived: `trend` and `expected_peak`
  - **Per-day sensors:** remain **TYPES-only** (optional `D+1` / `D+2`).  
    **PLANTS** expose forecast **as attributes only** (no extra entities).
- **Smart grouping** — Organizes sensors into:
  - **Pollen Types** (Grass / Tree / Weed)
  - **Plants** (Oak, Pine, Birch, etc.)
  - **Pollen Info** (Region / Date metadata)  
- **Configurable updates** — Change update interval, language, forecast days, and per-day sensors without reinstalling.  
- **Manual refresh** — Call `pollenlevels.force_update` to trigger an immediate update and reset the timer.
- **Last Updated sensor** — Shows timestamp of last successful update.
- **Rich attributes** — Includes `inSeason`, index `description`, health `advice`, `color_hex`, `color_rgb`, `color_raw`, and plant details.
- **Resilient startup** — Retries setup automatically when the first API response lacks daily pollen info (`dailyInfo` types/plants), ensuring entities appear once data is ready.

---

## 🔒 Security & Privacy

- Your **API key** is stored by Home Assistant’s secure config entries.  
- **We never log your API key.** As a safety net, if it ever appears in an error message, it is **redacted** as `***`.  
- **We do not log request parameters** (coordinates). Debug logs only include non-sensitive metadata (e.g., forecast days and whether a language is set).  
- Avoid sharing full debug logs publicly; review them for sensitive information before posting.

---

## ⚙️ Options

You can change:

- **Update interval (hours)**
- **API response language code**
- **Forecast days** (`1–5`) for pollen TYPES
- **Per-day TYPE sensors** via `create_forecast_sensors`:
  - `none` → no extra sensors
  - `D+1` → sensors for each TYPE with suffix `(D+1)`
  - `D+1+2` → sensors for `(D+1)` and `(D+2)`

> **Validation rules:**
> - `D+1` requires `forecast_days ≥ 2`
> - `D+1+2` requires `forecast_days ≥ 3`

> **After saving Options:** if per-day sensors are disabled or `forecast_days` becomes insufficient, the integration **removes** any stale D+1/D+2 entities from the **Entity Registry** automatically. No manual cleanup needed.

Go to **Settings → Devices & Services → Pollen Levels → Configure**.

---

## 🗝️ Getting a Google API Key

You need a valid Google Cloud API key with access to the **Maps Pollen API**.

1. **Open** the [Google Cloud Console](https://console.cloud.google.com/).  
2. **Create or select** a project and **enable billing** for it.  
3. Go to **APIs & Services → Library** and **enable** the  
   **[Maps Pollen API](https://console.cloud.google.com/apis/library/pollen.googleapis.com)**.  
4. Go to **APIs & Services → Credentials → Create credentials → API key**.  
5. **Restrict your key** (recommended):  
   - **API restrictions** → **Restrict key** → select **Maps Pollen API** only.  
   - **Application restrictions** (optional but recommended):  
     - **HTTP referrers** (for frontend usages) or  
     - **IP addresses** (for server-side usage, e.g. your HA host).  
6. **Copy** the key and paste it in the integration setup.  

👉 See the **[FAQ](FAQ.md)** for **quota tips**, rate-limit behavior, and best practices to avoid exhausting your free tier.

---

## 🔧 Showing colors in the UI

Home Assistant **does not** color icons natively from attributes.  
If you want **dynamic colors** driven by `color_hex` / `color_rgb`, you have these options:

### ✅ Native options (no custom cards)

1) **Entities card** (attribute row)

```yaml
type: entities
title: Grass
entities:
  - type: attribute
    entity: sensor.type_grass
    attribute: category
    name: Category
  - type: attribute
    entity: sensor.type_grass
    attribute: description
    name: Index description
````

> Simple and robust. It shows attributes clearly but **doesn’t color** the icon.

2. **Gauge card** (color by severity based on numeric value)

```yaml
type: gauge
entity: sensor.type_grass
min: 0
max: 5
severity:
  green: 0
  yellow: 2
  red: 4
```

> Color is driven by thresholds, not by `color_hex`.

---

### 🧩 Custom cards (for real dynamic color binding)

If you need the icon/badge to follow the **exact** API color (`color_hex`):

**Mushroom (mushroom-template-card)**

```yaml
type: custom:mushroom-template-card
entity: sensor.type_grass
primary: >-
  Grass: {{ states(entity) }} ({{ state_attr(entity, "category") }})
icon: mdi:grass
badge_icon: mdi:circle
badge_color: >-
  {{ state_attr(entity, "color_hex") or "var(--primary-color)" }}
```

**button-card**

```yaml
type: custom:button-card
entity: sensor.type_grass
icon: mdi:grass
show_state: false
name: '[[[
  const s = states[entity];
  const cat = s?.attributes?.category ?? "";
  return `Grass: ${s?.state ?? "unknown"} (${cat})`;
]]]'
color: '[[[
  const s = states[entity];
  return s?.attributes?.color_hex || "var(--primary-color)";
]]]'
```

---

## ⚠️ Known caveats

* **Localized plant codes**: Google may localize `plantInfo.code` in some locales (e.g., `GRAMINALES` in ES) while others remain English (`OLIVE`, `MUGWORT`).
  Changing `languageCode` may recreate plant sensors with a different suffix.
  **Recommendation**: keep API language stable or rename entities in UI after changing it.

---

## ⚙️ Installation

### Via HACS (recommended)

1. Open **HACS → Integrations** in Home Assistant.
2. Click **Explore & Download Repositories**.
3. Search for **Pollen Levels** or click the badge above.
4. Click **Download** and follow prompts.
5. Restart or *Reload* HA when prompted.

---

## 🔑 Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Pollen Levels**.
3. Enter:

   * **Google API Key**
   * **Location**
   * **Update Interval** (hours)
   * **Language Code**

---

## 🌐 Example API request

```bash
curl -X GET "https://pollen.googleapis.com/v1/forecast:lookup?key=YOUR_KEY&location.latitude=48.8566&location.longitude=2.3522&days=2&languageCode=es"
```

---

## ❤️ Support the project

If this integration helps you, consider supporting development:

[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi\&logoColor=white)](https://ko-fi.com/experience83)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://paypal.me/eXPerience83)

---

## 📜 License

MIT © 2025 [eXPerience83](LICENSE)
**Data Source:** [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen)
