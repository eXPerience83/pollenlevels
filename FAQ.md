# ❓ Frequently Asked Questions (FAQ)
*Last verified: 2026-05-18 (UTC). Pricing and quota limits may change; always confirm the current values in the official Google Maps Platform pages linked below.*

## 1. How many requests can I make to the Google Maps Pollen API?
As of **March 1, 2025**, Google Maps Platform applies **free monthly usage caps per SKU**.  
For the **Pollen API (SKU: “Pollen Usage”, Pro)** the **free cap is 5,000 requests/month**. Beyond the free cap, usage is billed pay-as-you-go per 1,000 requests.  
**Pricing list (official):** https://developers.google.com/maps/billing-and-pricing/pricing  
**Pollen usage & billing page:** https://developers.google.com/maps/documentation/pollen/usage-and-billing

**Quick links**
- Enable the API in your project: https://console.cloud.google.com/apis/library/pollen.googleapis.com  
- Go to Maps quotas: https://console.cloud.google.com/google/maps-apis/quotas

---

## 2. Does this integration consume a lot of API calls?
No. By default the integration fetches every **6 hours** (~**4 requests/day**), which is roughly **~120 requests/month per location**, well below the free cap.

---

## 3. Can I manually refresh the data?
Yes. Call the `pollenlevels.force_update` service from **Developer Tools → Services** in Home Assistant.  
This fetches new data immediately and resets the refresh timer.

---

## 4. Why am I getting “Invalid API Key” or “Quota Exceeded” errors?
- **Invalid API Key**: Confirm the key is correct and that the **Pollen API** is enabled in your project.  
- **Quota Exceeded**: You may have hit **your custom daily/minute caps** (see §10) or the **monthly free cap**.  
  **Check/adjust quotas**: https://console.cloud.google.com/google/maps-apis/quotas  

> **Note:** **Budgets/alerts don’t stop usage**; they only notify.  
> Budgets (official docs): https://cloud.google.com/billing/docs/how-to/budgets

---

## 5. How is the pollen data obtained?
Data is sourced from the **Google Maps Pollen API**, which provides localized pollen levels for **trees, grasses, and weeds**, plus plant-level details and up to **5-day forecasts**.  
Docs: https://developers.google.com/maps/documentation/pollen/overview

---

## 6. Can I request pollen data in my language?
Yes. Set a **language code** in the integration options (e.g., `en`, `es`, `fr`, `de`, `uk`).  
This controls localized fields returned by the API.

---

## 7. How can I reduce API usage?
- Increase the update interval (e.g., every 12 or 24 hours).
- Avoid excessive manual refreshes.
- **Set daily/minute caps** (see §10).
- Monitor usage and set alerts in Google Cloud.

---

## 8. Will this work without internet?
No. The integration requires internet access to reach the Google Maps Pollen API.

---

## 9. Does the integration store my API key?
The API key is stored securely by Home Assistant and is **never shared** with third parties.

---

## 10. Which QUOTAS should I cap in Google Cloud Console (to stay within the free tier)?
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
> **Caution:** Quota caps are a useful safety guard, but Google notes they may not be enforced with absolute precision due to latency. Keep a buffer below the free cap instead of setting limits right at the monthly maximum.

- **Forecast Usage per day** → **150**  
  (≈ 4,500/month, comfortably under the 5,000 free cap; increase only if you have multiple locations or frequent manual refreshes)
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

## References (official)
- **Core services pricing list (Environment → Pollen Usage)** — last updated shown on page: https://developers.google.com/maps/billing-and-pricing/pricing  
- **Pollen API usage & billing (quota editing steps)**: https://developers.google.com/maps/documentation/pollen/usage-and-billing  
- **Pollen API — Forecast endpoint**: https://developers.google.com/maps/documentation/pollen/forecast  
- **Pollen API — Heatmap tiles**: https://developers.google.com/maps/documentation/pollen/heatmap-tiles  
- **Cap API usage (daily/minute/per-user caps)**: https://cloud.google.com/apis/docs/capping-api-usage  
- **View/manage quotas in Console**: https://cloud.google.com/docs/quotas/view-manage  
- **Pollen API FAQ (6,000 QPM)**: https://developers.google.com/maps/documentation/pollen/faq
