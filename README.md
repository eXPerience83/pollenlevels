<p align="center">
  <img src="https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/pollenlevels/icon.png" alt="Pollen Levels logo" width="140"/>
</p>

# 🌼 Pollen Levels Integration for Home Assistant

**Monitor current and forecast pollen levels** from the Google Maps Pollen API directly in Home Assistant.  
Track **grass**, **tree**, and **weed** pollen, regional plant species, daily summaries, and up to **5 days of forecast data** across multiple locations.

[![GitHub Release](https://img.shields.io/github/v/release/eXPerience83/pollenlevels)](https://github.com/eXPerience83/pollenlevels/releases)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant%20v5-2026.11.0%2B-41BDF5?logo=home-assistant&logoColor=white)](https://www.home-assistant.io/)
[![Latest Home Assistant Compatibility](https://github.com/eXPerience83/pollenlevels/actions/workflows/ha-compatibility-canary.yml/badge.svg?branch=main)](https://github.com/eXPerience83/pollenlevels/actions/workflows/ha-compatibility-canary.yml)
[![hassfest validation](https://github.com/eXPerience83/pollenlevels/actions/workflows/hassfest.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/hassfest.yml)
[![Marketplace validation (HACS action)](https://github.com/eXPerience83/pollenlevels/actions/workflows/validate.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/validate.yml)
[![Marketplace catalog](https://img.shields.io/badge/Marketplace-Community%20Catalog-blue.svg)](https://github.com/hacs/default/blob/master/integration)
[![License](https://img.shields.io/github/license/eXPerience83/pollenlevels?logo=github)](LICENSE)

[Installation](#installation) · [Configuration](#configuration) · [FAQ](FAQ.md) · [Terms](TERMS.md) · [Privacy](PRIVACY.md)

[![Open Pollen Levels in your Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=eXPerience83&repository=pollenlevels&category=integration)

---

## Requirements

- **Pollen Levels 5.0:** Home Assistant **2026.11.0 or newer** (earlier Home Assistant versions must use a compatible 4.x release).
- **Distribution:** the built-in **Settings → Marketplace** in Home Assistant 2026.11+; no separate HACS installation.
- A Google Cloud project with billing enabled and a Google API key restricted to the **Maps Pollen API**.

Install a [published Pollen Levels release](https://github.com/eXPerience83/pollenlevels/releases) compatible with your Home Assistant version. This guide documents the **5.0** functionality and upgrade path.

---

## Installation

### Home Assistant 2026.11+ (Marketplace)

1. Open **Settings → Marketplace** and search for **Pollen Levels**, or use the Marketplace badge above.
2. Select **Install** and review the community-integration notice and the selected release version.
3. If the repository is not listed, select **Add from link**, enter `https://github.com/eXPerience83/pollenlevels`, then install it. Adding a custom repository requires connecting GitHub; catalog installation does not.
4. When Home Assistant offers the integration setup flow, configure it. Otherwise open **Settings → Devices & services → Add integration → Pollen Levels**.
5. Restart Home Assistant when prompted after an integration **update**.

Marketplace normally offers the current stable release. Check its release notes before upgrading an existing installation.

### Existing HACS installations and older Home Assistant

Home Assistant 2026.11 migrates supported HACS integrations, custom repositories, and update entities into Marketplace automatically. **Do not uninstall and reinstall Pollen Levels just to migrate**: preserve configuration entries, entities, history, and automations. See the [official Marketplace migration guide](https://www.home-assistant.io/integrations/marketplace).

On Home Assistant **2026.5–2026.10**, use the compatible legacy HACS installation of [Pollen Levels 4.0.3](https://github.com/eXPerience83/pollenlevels/releases/tag/v4.0.3). Version 5.0 requires HA 2026.11+.

Before upgrading an existing installation to v5, read [Upgrading to 5.0](#upgrading-to-50) and [PREPARATION_5.0.md](PREPARATION_5.0.md).

---

## Configuration

1. Open **Settings → Devices & services → Add integration → Pollen Levels**.
2. Enter your **Google API key**, a **location name** and its **map location**, then choose an optional update interval and API language.
3. To add more locations with the **same API key**, open the existing Pollen Levels parent entry and **add a location**. Do not create another parent entry with the same key.
4. To change a location name/coordinates, reconfigure that location. Use the parent's **Configure** action for the shared polling interval and API language.

Each location gets its own pollen sensors and **Update now** button. By default Pollen Levels refreshes every **6 hours**, with an adjustable interval of **1–24 hours**. The forecast request is fixed at five days. Use `pollenlevels.force_update` for a manual refresh of all loaded active locations.

---

## 🌟 Features

- **Multi-language support** — UI in 21 languages (**EN, ES, CA, DE, FR, IT, PL, RU, UK, NL, ZH-Hans, SV, CS, PT-BR, DA, NB, PT-PT, RO, FI, HU, ZH-Hant**) and a configurable Google API language code; Google may return the closest available translation.
- **Location-specific sensors** — Creates sensors for pollen types and plants present in the location's initial API data; a reload may be needed if Google introduces a new plant code after setup.  
- **Daily summary sensors** — Adds plants in season today, overall pollen risk today, and top pollen types today.
- **Five-day forecast for TYPES, PLANTS, and summary sensors** —
  Pollen Levels always requests the maximum 5-day forecast horizon supported by
  the Google Maps Pollen API.
  - `forecast` list with `{offset, date, has_index, value, category, description, color_*}`
  - Convenience: `tomorrow_*` and `d2_*`
  - Derived: `trend` and `expected_peak`
  - **PLANTS** expose forecast as attributes only (no extra entities).
- **Smart grouping** — Organizes sensors into:
  - **Pollen Types** (Grass / Tree / Weed)
  - **Plants** (Oak, Pine, Birch, etc.)
  - **Pollen Info** (Region / Date metadata)  
- **Configurable updates** — Change update interval and API response language without reinstalling.
- **Manual refresh** — Use the per-location **Update now** button entity to refresh a single configured location, or call the global `pollenlevels.force_update` action to refresh all configured locations.
- **Last Updated sensor** — Shows timestamp of last successful update.
- **Rich attributes** — Includes `inSeason`, index `description`, health `advice`
  for pollen types, `color_hex`, `color_rgb`, and plant details.
- **Resilient startup** — Retries when the first request lacks usable `dailyInfo` and isolates a failed location from healthy locations sharing the same API key.

---

## ⚙️ Options

You can change:

- **Update interval (hours)** (1–24)
- **API response language code**

The config and options flows use modern Home Assistant selectors and include
links to Google’s API key setup and security best practices so you can follow
the recommended restrictions.

Forecast days are no longer configurable. Pollen Levels always requests 5 days
of forecast data so existing sensors can expose the maximum available forecast
attributes.

Go to **Settings → Devices & Services → Pollen Levels → Configure**.

---

## Daily summary sensors

The integration creates three current-day summary sensors in addition to the
individual pollen type and plant sensors:

- `plants_in_season_today`
  - State: number of plants explicitly marked as in season today.
  - Key attributes: `plant_codes`, `plant_names`, `in_season_count`,
    `out_of_season_count`, `unknown_season_count`, `total_plant_count`,
    `unknown_season_codes`, and `unknown_season_names`.
  - Missing or non-boolean `inSeason` values are treated as unknown, not false.
- `overall_pollen_risk_today`
  - State: highest current-day pollen type index value.
  - Key attributes: `category`, `description`, `top_pollen_codes`,
    `top_pollen_names`, `top_pollen_categories`, and `tie_count`.
  - Tied top pollen types are preserved in the attributes.
- `top_pollen_types_today`
  - State: top pollen type name, or comma-separated names when tied.
  - Key attributes: `top_value`, `top_pollen_codes`, `top_pollen_names`,
    `top_pollen_categories`, and `tie_count`.

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
   - **Application restrictions** (optional):  
     - Prefer **IP addresses** for server-side usage (your HA host).  
     - If your IP is dynamic, consider **no application restriction** and rely on
       the API restriction above.  
6. **Copy** the key and paste it in the integration setup.

The setup form also links directly to the Google documentation for obtaining
an API key and best-practice restrictions.

👉 See the **[FAQ](FAQ.md)** for **quota tips**, rate-limit behavior, and best practices to monitor and control Google Cloud billing.

HTTP referrer (website) restrictions are intended for browser-based apps and
are not supported by this integration.

### Troubleshooting 403 errors

403 responses during setup or updates now include the API’s reason (when
available). They often indicate billing is disabled, the Pollen API is not
enabled, or your key restrictions do not match your Home Assistant host.

---

## Upgrading to 5.0

Pollen Levels 5.0 targets the built-in Marketplace and Home Assistant 2026.11+. It retains the existing parent API-key and location-subentry model, sensor identities, forecast attributes, and update actions.

- **Before upgrading, make a complete, recoverable Home Assistant backup**, including config entries, `.storage`, entity/device registries, and Recorder data. Back up an external Recorder database separately. Keep an off-device copy and the recovery key when applicable.
- When upgrading Home Assistant from a version with HACS, let **Marketplace migrate the existing installation**. Update Pollen Levels in place; do not remove and re-add it.
- Check that locations, sensors, custom entity IDs, dashboards, automations, Recorder history and long-term statistics remain associated after restart. Multi-location and historical-migration checks are particularly important.
- **Downgrade by file replacement is not supported** after stored migration changes. Restore the matching **pre-upgrade** configuration, registries and database from a consistent backup.

For detailed migration checks and recovery procedures, see the [5.0 upgrade and rollback guide](PREPARATION_5.0.md).

### Historical compatibility

Pollen Levels v3 replaced the old one-entry-per-location layout and separate `_d1` / `_d2` forecast entities. Future values are attributes of the base sensor:

```jinja
{{ state_attr("sensor.example_grass", "tomorrow_value") }}
{{ state_attr("sensor.example_grass", "d2_value") }}
```

### Upgrading to 4.0.0: long-term statistics restored

Pollen Levels 4.0.0 restored long-term statistics eligibility for current-day
pollen type and plant sensors and `overall_pollen_risk_today`. Previously
collected statistics can continue under the **same entity and statistic identity**;
the period on 3.1.0 may contain a gap. Statistics manually deleted after
upgrading to 3.1.0 cannot be reconstructed automatically. New statistics begin
with a supported version.

These numeric states represent Google's current-day forecast, not direct
physical measurements. Forecast attributes for future days are excluded
from Recorder persistence.

See the [FAQ](FAQ.md) for the v2→v3 migration, legacy forecast entities and
Recorder details.

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
```

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

**Pollen dashboard card (recommended): pollenprognos-card**

If you want a dedicated pollen Lovelace card with forecast visualizations and a visual editor UI,
**pollenprognos-card** supports this integration since **v2.9.0**.
The base sensor `forecast`, `tomorrow_*`, `d2_*`, `trend`, and `expected_peak`
attributes keep their existing format for card compatibility.

- Repo: [pollenprognos-card](https://github.com/krissen/pollenprognos-card)
- Install: Settings → Marketplace → `pollenprognos-card` (dashboard plugin)

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

* **Plant codes and localized names**: Pollen Levels uses Google
  `plantInfo.code` values to keep plant sensor identities stable. In tests
  across `es`, `en`, `fr`, `de`, `it`, and `pt`, Google returned the same plant
  codes while localizing `displayName`, descriptions, categories, and
  recommendations. For example, `GRAMINALES` is the Google plant code for grass
  pollen plants, while the visible name may appear as `Gramíneas`, `Grasses`,
  `Graminées`, `Gräser`, or another localized value depending on the selected
  API language. Pollen Levels does not use localized `displayName` values to
  build entity identity. If Google changes plant codes in the future, treat that
  as an upstream API behavior change and include diagnostics when reporting it.

---

## 🔒 Security & Privacy

- Your **API key** is saved in Home Assistant's local config-entry storage. Protect your Home Assistant configuration and backups, which may contain this key.  
- **We never log your API key.** As a safety net, if it ever appears in an error message, it is **redacted** as `***`.  
- **We do not log request parameters** (coordinates). Debug logs only include non-sensitive metadata (e.g., forecast days and whether a language is set).  
- Diagnostics include redacted daily, registry, and runtime summaries to help
  troubleshoot the integration without exposing API keys or exact coordinates.
  Approximate coordinates are rounded to 1 decimal for support purposes.
  Diagnostics may also include Home Assistant internal config entry and location
  subentry identifiers (`entry_id`, `subentry_id`). These are not credentials, but
  you should still review diagnostics before posting them publicly.
- Avoid sharing full debug logs publicly; review them for sensitive information before posting.
- Never share real Google API keys publicly, and do not paste full Google Pollen
  API URLs containing `key=...` into public issues. If a key was exposed,
  rotate it in Google Cloud Console and restrict it to the required API and
  allowed referrers/IPs where possible.

Requests go directly from your Home Assistant instance to the Google Maps Pollen
API. The project maintainer does not operate a data-collection backend; Google
processes request data under its own privacy policy. See [PRIVACY.md](PRIVACY.md)
for details.

Live forecast attributes remain available to dashboards, templates, automations,
and compatible custom cards. Pollen Levels excludes `forecast`, `tomorrow_*`,
`d2_*`, `trend`, and `expected_peak` from Home Assistant Recorder persistence,
while current states and non-excluded attributes remain subject to your Recorder
configuration. Its own stale Pollen API coordinator snapshot has a fixed 24-hour
runtime cache lifetime. Recorder history and Home Assistant-generated long-term
statistics are separate local storage layers; see [PRIVACY.md](PRIVACY.md) for
details.

---

## 🌐 Example API request

```bash
curl -X GET "https://pollen.googleapis.com/v1/forecast:lookup?key=YOUR_KEY&location.latitude=48.8566&location.longitude=2.3522&days=5&languageCode=es"
```

> **Note:** Replace `YOUR_KEY` locally and never share full API URLs containing `key=...` publicly.

---

## ❤️ Support the project

If this integration helps you, consider supporting development:

[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/experience83)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://paypal.me/eXPerience83)

---

## 📜 License

MIT © 2025 [eXPerience83](LICENSE)

---

## Data source, attribution, and terms

Google Maps — Source: Includes pollen data from Google

Pollen Levels uses the [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen)
and follows the [Pollen API policies and attribution](https://developers.google.com/maps/documentation/pollen/policies)
guidance. Use of Google Maps features and content is subject to Google's
applicable terms and privacy policy. See [TERMS.md](TERMS.md) and
[PRIVACY.md](PRIVACY.md).
