# ❓ Frequently Asked Questions (FAQ)

*Last verified: 2026-07-10 (UTC). Pricing and quota limits may change; always confirm the current values in the official Google Maps Platform pages linked below.*

## 1. How many requests can I make to the Google Maps Pollen API?

Pricing/free usage cap last checked: **2026-06-13 (UTC)**.

Google's current Pollen API documentation describes pay-as-you-go pricing per
request, based on usage volume tiers. The current global Google Maps Platform
pricing list shows **Pollen Usage** with a **Free Usage Cap of 5,000 monthly
billable events**, followed by paid per-1,000-event tiers.

The old separate Google Maps Platform monthly credit ended on
**February 28, 2025**. Use the Pollen SKU's current Free Usage Cap, plus Google
Cloud quotas, budgets and alerts, to control spend. The Pollen API also
documents a maximum **6,000 queries per minute (QPM)** limit for each API
method; that is a service rate limit, not the monthly free usage cap.

**Pricing list (official):** https://developers.google.com/maps/billing-and-pricing/pricing
**Pollen usage & billing page:** https://developers.google.com/maps/documentation/pollen/usage-and-billing

**Quick links**
- Enable the API in your project: https://console.cloud.google.com/apis/library/pollen.googleapis.com  
- Go to Maps quotas: https://console.cloud.google.com/google/maps-apis/quotas

---

## 2. Does this integration consume a lot of API calls?

No. By default the integration fetches every **6 hours** (~**4 requests/day**),
which is roughly **~120 requests/month per location**. That is well below the
current **5,000 monthly billable events** Free Usage Cap shown for the
**Pollen Usage** SKU. Your actual cost depends on Google's current Pollen API
pricing, your configured locations, manual refreshes, quota settings and any
billing credits on your account.

---

## 3. Can I manually refresh the data?

Yes. You can use either method:
- Press the per-location **Update now** button entity created by the integration to refresh one configured location.
- Call the `pollenlevels.force_update` service from **Developer Tools → Services** to refresh all configured locations.
Both methods request an immediate coordinator refresh. The normal scheduled polling interval remains managed by Home Assistant's DataUpdateCoordinator.

---

## 4. Why am I getting “Invalid API Key” or “Quota Exceeded” errors?

- **Invalid API Key**: Confirm the key is correct and that the **Pollen API** is enabled in your project.  
- **Quota Exceeded**: You may have hit **your custom daily/minute caps** (see §10) or another Google Cloud quota/billing limit on the project.
  **Check/adjust quotas**: https://console.cloud.google.com/google/maps-apis/quotas  

> **Note:** **Budgets/alerts don’t stop usage**; they only notify.  
> Budgets (official docs): https://cloud.google.com/billing/docs/how-to/budgets

---

## 5. How is the pollen data obtained?

Data is sourced from the **Google Maps Pollen API**, which provides localized pollen levels for **trees, grasses, and weeds**, plus plant-level details and up to **5-day forecasts**.  
Docs: https://developers.google.com/maps/documentation/pollen/overview

---

## 6. Can I request pollen data in my language?

Yes. Set a **language code** in the integration options (e.g., `en`, `es`,
`fr`, `de`, `uk`). This controls localized fields returned by the API, such as
display names, categories, descriptions, and health recommendations.

Pollen Levels uses Google `plantInfo.code` values, not localized
`displayName` values, to build plant sensor identity. In tests across `es`,
`en`, `fr`, `de`, `it`, and `pt`, Google returned the same plant codes while
localizing the visible names. For example, `GRAMINALES` remained the plant code
for grass pollen plants, while the display name changed by language.

This means changing the API language should update localized attributes without
recreating plant sensors, as long as Google keeps returning the same
`plantInfo.code` values. If Google changes plant codes in the future, treat it
as an upstream API behavior change and include diagnostics when reporting it.

---

## 7. How can I reduce API usage?

- Increase the update interval (e.g., every 12 or 24 hours).
- Avoid excessive manual refreshes.
- **Set daily/minute quota caps** (see §10).
- Monitor usage and set Google Cloud budgets/alerts for the billing account.

---

## 8. Will this work without internet?

No. The integration requires internet access to reach the Google Maps Pollen API.

---

## 9. Does the integration store my API key?

The API key is stored by Home Assistant in the parent Pollen Levels config entry
and is sent directly from your Home Assistant instance to the Google Maps Pollen
API when requesting pollen data. It is not sent to the Pollen Levels project
maintainer.

---

## 10. Which QUOTAS should I cap in Google Cloud Console?

Open **Google Cloud Console → Google Maps Platform → Quotas** and select **Pollen API**.  
Direct link: https://console.cloud.google.com/google/maps-apis/quotas

Typical quota items you’ll see (names may vary slightly by locale):
- **Pollen – Forecast Usage per day**
- **Pollen – Forecast Usage per minute**
- **Pollen – Forecast Usage per minute per user**
- **Pollen – HeatMap Usage per day**
- **Pollen – HeatMap Usage per minute**
- **Pollen – HeatMap Usage per minute per user**

**What this integration uses:** the **Forecast** endpoint (point forecast).  
**What we don’t use:** **HeatMap tiles** (map overlays via `heatmapTiles`).  

> **Safe setting:** You can set **HeatMap** quotas to **0** (or the minimum allowed) to block tile usage and avoid accidental billing.

**Recommended hard caps (safe defaults):**
> **Caution:** Quota caps are a useful safety guard, but Google notes they may
> not be enforced with absolute precision due to latency. Keep a buffer below
> the monthly Free Usage Cap and monitor billing instead of relying on a cap as
> your only guardrail.

- **Forecast Usage per day** → **150**
  (about 4,500/month, leaving a buffer below the current 5,000 monthly Free
  Usage Cap; increase only if you have multiple locations or frequent manual
  refreshes and accept the possible cost).
- **Forecast Usage per minute** → **10**
- **Forecast Usage per minute per user** → **10**
- **HeatMap quotas** → **0** (or minimum allowed) to disable tiles.

**How to edit a quota**
1) Go to **Quotas** and choose **Pollen API**.  
2) Tick the box for the target quota (e.g., **Pollen – Forecast Usage per day**).  
3) Click **Edit**, set your value (e.g., **150**), and **Save/Submit**.  
Reference guide: https://cloud.google.com/apis/docs/capping-api-usage

---

## 11. Are there rate limits?

Yes. The **default rate limit is 6,000 queries per minute (QPM)** for the Pollen API.  
FAQ: https://developers.google.com/maps/documentation/pollen/faq

---

## 12. What happens to my entries when upgrading to the v3 pre-release?

The v3 pre-release migrates Pollen Levels to Home Assistant config subentries.
Legacy 2.x entries that share the same Google API key are grouped under one
parent API-key entry, and each migrated location becomes one location subentry.
The API key is stored once on the parent instead of duplicated across legacy
entries.

Duplicate legacy entries are marked as merged and removed after their
locations, entities, and devices are moved to the parent entry. If Home
Assistant cannot move those registry links safely, the legacy entry is kept so
the migration can be retried.

Migrated location subentries keep the legacy entry ID internally so existing
entity unique IDs, device identifiers, dashboards, history, and automations
continue to match after the entries are consolidated.

If grouped legacy entries used different update interval or language options,
the parent keeps the first entry's options and fills missing values from the
remaining entries. You can adjust the shared options after upgrading.

After upgrading, diagnostics can help validate the migration:

- `registry_summary.entities.without_subentry` should normally be `0`.
- `registry_summary.devices.without_subentry` should normally be `0`.
- `registry_summary.devices.with_legacy_none_association` should normally be
  `0`.
- `runtime_summary.stale_location_count` should normally be `0` after reloading
  the parent entry.

If `runtime_summary.stale_location_count` is greater than `0` immediately after
deleting a location subentry, reload the Pollen Levels parent entry from Home
Assistant. This clears the stale runtime coordinator from memory.

Diagnostics redact the API key and only include approximate coordinates rounded
to 1 decimal for support purposes. They may also include Home Assistant internal
`entry_id` and `subentry_id` values so support can match runtime, registry, and
subentry state. These IDs are not credentials, but review diagnostics before
sharing them publicly.

During parent API-key reauthentication or reconfiguration, the integration tries
configured locations until one validates successfully. Authentication and quota
errors are treated as API-key-level failures.

During startup, if at least one configured location loads successfully, the
parent entry remains available and failed locations are reported separately in
diagnostics. Retryable location setup failures are retried on parent reload and
can create a Repair warning after they repeat. If no configured location can
load successfully, the parent entry is marked not ready so Home Assistant can
retry setup.

Create a Home Assistant backup before upgrading. Downgrading to Pollen Levels
2.x after this migration is not supported.

---

## 13. Can I choose how many forecast days Pollen Levels requests?

No. Starting with v3 beta 4, Pollen Levels always requests 5 forecast days. This
keeps the integration simpler and gives all existing sensors the maximum
available forecast attributes.

Existing users who previously selected fewer days are upgraded automatically.
No base sensors are renamed or recreated.

---

## 14. Where did my `_d1` and `_d2` forecast sensors go?

Pollen Levels no longer creates separate per-day forecast entities. Future
forecast data is available on the base pollen sensors through the `forecast`,
`tomorrow_*`, `d2_*`, `trend`, and `expected_peak` attributes.

If the integration detects legacy per-day forecast entities or settings during
upgrade, it also creates a persistent Repair warning in Home Assistant.

This cleanup has been brought forward in v3 beta 4 so the migration can be
tested before the release candidate.

Update any dashboards, automations, templates or custom cards that reference
entities such as `sensor.example_grass_d1` or `sensor.example_grass_d2`.

---

## 15. Does Home Assistant Recorder store pollen forecast data?

Live forecast attributes remain available in Home Assistant for dashboards,
templates, automations, and compatible custom cards. Future forecast-derived
attributes such as `forecast`, `tomorrow_*`, `d2_*`, `trend`, and
`expected_peak` are excluded from Recorder persistence by Pollen Levels.

Current states and non-forecast attributes may still be recorded according to
your Home Assistant Recorder configuration.

Under the current Pollen API service-specific terms, today's forecast values may
be cached for up to 365 consecutive calendar days, and future forecast values may
be cached for no more than 24 hours. Users with Recorder retention above 365
days should exclude Pollen Levels entities or otherwise ensure compliant
retention.

Pollen Levels does not automatically purge existing Recorder history.

---

## 16. What data is sent to Google?

Your Home Assistant instance sends requests directly to the Google Maps Pollen
API. Requests include your API key, coordinates, requested forecast days, an
optional language code, and normal network metadata such as the source IP
address.

See [PRIVACY.md](PRIVACY.md) and Google's
[Privacy Policy](https://policies.google.com/privacy) for more detail.

---

## References (official)

- **Core services pricing list (Environment → Pollen Usage)** — last updated shown on page: https://developers.google.com/maps/billing-and-pricing/pricing  
- **Pollen API usage & billing (quota editing steps)**: https://developers.google.com/maps/documentation/pollen/usage-and-billing  
- **Pollen API — Forecast endpoint**: https://developers.google.com/maps/documentation/pollen/forecast  
- **Pollen API — Heatmap tiles**: https://developers.google.com/maps/documentation/pollen/heatmap-tiles  
- **Pollen API policies and attribution**: https://developers.google.com/maps/documentation/pollen/policies
- **Google Maps End User Additional Terms**: https://maps.google.com/help/terms_maps/
- **Google Privacy Policy**: https://policies.google.com/privacy
- **Google Maps Platform Service Specific Terms**: https://cloud.google.com/maps-platform/terms/maps-service-terms
- **Google Maps Platform EEA Service Specific Terms**: https://cloud.google.com/terms/maps-platform/eea/maps-service-terms
- **Cap API usage (daily/minute/per-user caps)**: https://cloud.google.com/apis/docs/capping-api-usage  
- **View/manage quotas in Console**: https://cloud.google.com/docs/quotas/view-manage  
- **Pollen API FAQ (6,000 QPM)**: https://developers.google.com/maps/documentation/pollen/faq
