# ❓ Frequently Asked Questions (FAQ)

## 1. How many requests can I make to the Google Maps Pollen API?
The Google Maps Pollen API offers **1,000 requests per month** for free, per billing account.  
Once you exceed this quota, standard Google Maps Platform billing rates apply.  
For more details, check the [Google Cloud Console Pollen API page](https://console.cloud.google.com/apis/library/pollen.googleapis.com).

---

## 2. Does this integration consume a lot of API calls?
No. The integration is designed to **fetch data only at the interval you configure** (default: every 6 hours).  
With the default interval, the monthly usage is around **120 requests** (4 requests/day × 30 days), which is well below the free tier limit.

---

## 3. Can I manually refresh the data?
Yes. Call the `pollenlevels.force_update` service from Home Assistant's **Developer Tools → Services**.  
This will immediately fetch new data and reset the refresh timer.

---

## 4. Why am I getting "Invalid API Key" or "Quota Exceeded" errors?
- **Invalid API Key**: Check that you copied the key correctly and that it is restricted only to the **Maps Pollen API**.  
- **Quota Exceeded**: You have reached the free 1,000 requests/month limit or your billing account has restrictions.

---

## 5. How is the pollen data obtained?
Data is sourced from the [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen), which provides real-time pollen information for grass, trees, and weeds, as well as detailed plant-level data.

---

## 6. Can I request pollen data in my language?
Yes. You can specify a **language code** (e.g., `en`, `es`, `fr`, `de`, `uk`) in the integration options.  
This controls the language of the data returned by the API.

---

## 7. How can I reduce API usage?
- Increase the update interval in the integration options (e.g., every 12 or 24 hours).  
- Avoid excessive manual refreshes unless necessary.  
- Monitor API usage in the [Google Cloud Console](https://console.cloud.google.com/).

---

## 8. Will this work without internet?
No. The integration requires an active internet connection to reach the Google Maps Pollen API.

---

## 9. Does the integration store my API key?
The API key is stored securely inside Home Assistant’s configuration system and is **never shared** with third parties.

---
