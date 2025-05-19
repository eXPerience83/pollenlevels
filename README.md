# Google Pollen Sensor for Home Assistant

This is a custom integration for [Home Assistant](https://www.home-assistant.io) to retrieve pollen data from the [Google Maps Pollen API](https://developers.google.com/maps/documentation/pollen/forecast).

It provides current pollen levels and forecasts for grass, trees, and weeds at your location.

---

## Features

- Current **Universal Pollen Index (UPI)** for `grass`, `trees`, and `weeds`
- Pollen **forecast for upcoming days**
- Fully integrated into Home Assistant as sensors
- Multilingual support (English, Spanish, more coming soon)
- Compatible with **HACS** (Home Assistant Community Store)

---

## Installation

### HACS (Recommended)

1. In HACS, go to **Integrations** > click on the three-dot menu > **Custom repositories**.
2. Add this repository:  
   `https://github.com/your-username/google_pollen_homeassistant`
3. Select category `Integration` and click **Add**.
4. Search for "Google Pollen Sensor" in HACS and install it.
5. Restart Home Assistant.

### Manual Installation

1. Copy the contents of this repository into:  
   `config/custom_components/google_pollen/`
2. Restart Home Assistant.

---

## Configuration

After installation and restart, go to **Settings > Devices & Services** > **Add Integration**, then search for "Google Pollen".

You will need to provide:

- Your **Google API Key**
- Your **latitude** and **longitude** (if not using default location)
- Number of forecast days (optional)

---

## Obtaining an API Key for the Google Maps Pollen API

To use the Pollen API, you need a valid Google Cloud API key with the **Maps Pollen API** enabled:

1. **Create or select a Google Cloud project**  
   Go to the [Google Cloud Console](https://console.cloud.google.com/) and either select an existing project or create a new one. You must have billing enabled on this project.

2. **Enable the Maps Pollen API**  
   In the Cloud Console, navigate to **APIs & Services > Library**, search for **Maps Pollen API**, and click **Enable**.

3. **Create an API key**  
   Go to **APIs & Services > Credentials** and click **Create credentials > API key**. Your new key will appear in a dialog.

4. **Restrict your API key (recommended)**  
   On the Credentials page, edit your new key:  
   - Under **API restrictions**, select **Restrict key**.  
   - Choose **Maps Pollen API** only.  
   - Click **Save**.

5. **Use your API key in the integration**  
   Enter your key in the integration setup, or store it securely in your `secrets.yaml`.

---

## API Usage and Requests

- **Current pollen data** is retrieved via:

  ```
  GET https://pollenws.googleapis.com/v1/pollen?
      latitude={LAT}&longitude={LON}&key={API_KEY}
  ```

- **Forecast data** is retrieved via:

  ```
  GET https://pollenws.googleapis.com/v1/pollen/forecast?
      latitude={LAT}&longitude={LON}&key={API_KEY}
  ```

- The API returns levels for:
  - `grass`
  - `tree`
  - `weed`

Each category includes:
- `value`: numeric level
- `category`: "Very Low", "Low", "Moderate", "High", "Very High", ¿"Very High+"?
- `dominantType`: e.g. `"BIRCH"`, `"OAK"`, `"RAGWEED"`

Documentation:
- [Pollen Index](https://developers.google.com/maps/documentation/pollen/pollen-index)
- [Forecast](https://developers.google.com/maps/documentation/pollen/forecast)

---

## Screenshots

*Coming soon...*

---

## Localization

- `en` – English  
- `es` – Español  
More translations are welcome! Submit via PR.

---

## License

MIT License

---

## Credits

This integration is inspired by the official Google Maps Pollen API and the Home Assistant community.
