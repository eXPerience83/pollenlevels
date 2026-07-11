<p align="center">
  <img src="https://raw.githubusercontent.com/home-assistant/brands/master/custom_integrations/pollenlevels/icon.png" alt="Pollen Levels logo" width="140"/>
</p>

# 🌼 Pollen Levels Integration for Home Assistant

**Monitor real-time pollen levels** from the Google Maps Pollen API directly in Home Assistant.  
Get sensors for **grass**, **tree**, **weed** pollen, plus individual plants like **OAK**, **PINE**, **OLIVE**, and many more!

[![GitHub Release](https://img.shields.io/github/v/release/eXPerience83/pollenlevels)](https://github.com/eXPerience83/pollenlevels/releases)
![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)
[![Lint](https://github.com/eXPerience83/pollenlevels/actions/workflows/lint.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/lint.yml)
[![hassfest validation](https://github.com/eXPerience83/pollenlevels/actions/workflows/hassfest.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/eXPerience83/pollenlevels/actions/workflows/validate.yml/badge.svg)](https://github.com/eXPerience83/pollenlevels/actions/workflows/validate.yml)
[![CodeQL enabled](https://img.shields.io/badge/CodeQL-enabled-brightgreen.svg)](https://github.com/eXPerience83/pollenlevels/security/code-scanning)
[![License](https://img.shields.io/github/license/eXPerience83/pollenlevels?logo=github)](https://github.com/eXPerience83/pollenlevels/blob/main/LICENSE)
[![HACS Default](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/hacs/integration)
[![FAQ](https://img.shields.io/badge/FAQ-Read%20Here-blue?logo=readthedocs&logoColor=white)](https://github.com/eXPerience83/pollenlevels/blob/main/FAQ.md)
[![Terms](https://img.shields.io/badge/Terms-Read-blue)](TERMS.md)
[![Privacy](https://img.shields.io/badge/Privacy-Read-blue)](PRIVACY.md)
[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/experience83)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?logo=paypal)](https://paypal.me/eXPerience83)

[![Open your Home Assistant instance and add this repository inside HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eXPerience83&repository=pollenlevels&category=integration)

---

## Requirements

- Requires Home Assistant 2026.3.0 or newer.
- This release line targets Python 3.14+, matching the Home Assistant runtime baseline.

## 🌟 Features

- **Multi-language support** — UI in 21 languages (**EN, ES, CA, DE, FR, IT, PL, RU, UK, NL, ZH-Hans, SV, CS, PT-BR, DA, NB, PT-PT, RO, FI, HU, ZH-Hant**) + API responses in any language.
- **Dynamic sensors** — Auto-creates sensors for all pollen types found in your location.  
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
- **Manual refresh** — Use the per-location **Update now** button entity to refresh a single configured location, or call the global `pollenlevels.force_update` service to refresh all configured locations.
- **Last Updated sensor** — Shows timestamp of last successful update.
- **Rich attributes** — Includes `inSeason`, index `description`, health `advice`
  for pollen types, `color_hex`, `color_rgb`, and plant details.
- **Resilient startup** — Retries setup automatically when the first API response lacks daily pollen info (`dailyInfo` types/plants), ensuring entities appear once data is ready.

---

## 🔒 Security & Privacy

- Your **API key** is stored by Home Assistant’s secure config entries.  
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
configuration.

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

## Migrating from per-day forecast sensors

Pollen Levels no longer creates separate per-day pollen type forecast sensors
such as:

```text
sensor.example_grass_d1
sensor.example_grass_d2
```

Forecast data is now exposed on the base pollen type sensor through attributes.
Existing legacy `_d1` and `_d2` entity registry entries owned by Pollen Levels
are removed automatically during setup/reload. Recorder history is not purged.
This beta brings that cleanup forward so the migration can be tested with the
fixed 5-day forecast model before the release candidate.

Before:

```jinja
{{ states("sensor.example_grass_d1") }}
{{ states("sensor.example_grass_d2") }}
```

After:

```jinja
{{ state_attr("sensor.example_grass", "tomorrow_value") }}
{{ state_attr("sensor.example_grass", "d2_value") }}
```

For advanced templates, use the `forecast` attribute and select the desired
offset:

```jinja
{% set forecast = state_attr("sensor.example_grass", "forecast") or [] %}
{% set tomorrow = forecast | selectattr("offset", "eq", 1) | first %}
{{ tomorrow.value if tomorrow else none }}
```

With the fixed 5-day horizon, the base sensor can expose future forecast items
with offsets `1` to `4`, depending on the data returned by the API.

---

## Multiple locations and upgrades

The v3 pre-release line migrates Pollen Levels to Home Assistant config
subentries. Configuration is stored as one parent API-key entry with one or more
location subentries. Existing 2.x entries are consolidated by API key during
migration:

- Legacy entries with the same Google API key are grouped under one parent
  entry, so the API key is stored once on the parent instead of duplicated.
- Each migrated legacy location becomes a location subentry under that parent.
- Duplicate legacy entries are marked as merged and removed after their
  locations, entities, and devices are moved to the parent. If Home Assistant
  cannot move the entity or device registry links safely, the legacy entry is
  kept so the migration can be retried.
- Migrated location subentries keep the legacy entry ID internally so existing
  entity unique IDs, devices, dashboards, history, and automations continue to
  match.

If legacy entries sharing a key used different update interval or language
options, the parent entry keeps the first entry's options and fills missing
values from the remaining entries. You can adjust the shared options after
upgrading from **Settings -> Devices & Services -> Pollen Levels -> Configure**.

To add another location after upgrading, go to **Settings -> Devices & Services
-> Pollen Levels**, open the parent entry, and add a new location subentry.
Reconfigure a location from that same entry when only its name or map
coordinates need to change. Each location has its own sensors and **Update now**
button; shared options such as update interval and language stay on the parent
**Configure** flow.

When reauthenticating or reconfiguring the parent API key, the integration tries
the configured locations until one returns usable pollen data. Authentication
and quota errors are treated as key-level failures.

During startup, the v3 beta keeps the parent entry available when at least one
configured location loads successfully. Locations that fail their initial
non-auth refresh are isolated in diagnostics and retried on parent reload; after
a repeated retryable failure, the integration creates a Repair warning for the
affected location. If no configured location can load successfully, the parent
entry is marked not ready so Home Assistant can retry setup.

Create a Home Assistant backup before installing the v3 pre-release.
Downgrading to Pollen Levels 2.x after the subentry migration is not supported.

### Diagnostics after the v3 migration

Diagnostics include two support summaries for the v3 migration:

- `registry_summary` shows how many entities and devices are associated with
  each location subentry.
- `registry_summary.entities.without_subentry` should normally be `0`.
- `registry_summary.devices.without_subentry` should normally be `0`.
- `registry_summary.devices.with_legacy_none_association` should normally be
  `0`.
- `runtime_summary` reports temporary runtime-only locations that can remain in
  memory after deleting a location subentry before the parent entry is reloaded.
- `runtime_summary.stale_location_count` should normally be `0` after reloading
  the parent entry.
- If `runtime_summary.stale_location_count > 0` immediately after deleting a
  location, reload the Pollen Levels parent entry from Home Assistant.

Diagnostics redact the API key and only include approximate coordinates rounded
to 1 decimal for support purposes.

---

## Health recommendations

Google Pollen API currently provides health recommendations at pollen type level
(`GRASS`, `TREE`, `WEED`). Plant sensors expose plant-specific index and
description data when available, but health advice is usually not provided for
individual plants.

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
- Install: HACS → Frontend

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
curl -X GET "https://pollen.googleapis.com/v1/forecast:lookup?key=YOUR_KEY&location.latitude=48.8566&location.longitude=2.3522&days=5&languageCode=es"
```

> **Note:** Replace `YOUR_KEY` locally and never share full API URLs containing `key=...` publicly.

---

## ❤️ Support the project

If this integration helps you, consider supporting development:

[![Ko-fi](https://img.shields.io/badge/Ko%E2%80%91fi-Support%20this%20project-ff5e5b?logo=ko-fi\&logoColor=white)](https://ko-fi.com/experience83)
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
