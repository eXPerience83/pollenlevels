# Terms of Use

Last updated: August 20, 2026

These terms are provided for the Pollen Levels Home Assistant custom integration.
They are not legal advice and do not state that the project has received legal
review, Google certification, or guaranteed legal compliance.

## Scope

These terms cover use of the Pollen Levels custom integration.

Pollen Levels is an independent open-source project. It is not affiliated with,
sponsored by, or endorsed by Google or the Home Assistant project.

## Google Maps features and content

By using Pollen Levels and Google Maps features and content exposed through the
integration, you acknowledge that such use is subject to the applicable
[Google Maps End User Additional Terms](https://maps.google.com/help/terms_maps/)
and [Google Privacy Policy](https://policies.google.com/privacy). The owner of
the Google Cloud project and API key is responsible for complying with the
Google Maps Platform agreement applicable to that account.

Google Maps Platform terms and service-specific terms may also apply to your
Google Cloud account and use of the API, including:

- [Pollen API policies and attribution](https://developers.google.com/maps/documentation/pollen/policies)
- [Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms)
- [Google Maps Platform Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)
- [Google Maps Platform EEA Terms](https://cloud.google.com/terms/maps-platform/eea)
- [Google Maps Platform EEA Service Specific Terms](https://cloud.google.com/terms/maps-platform/eea/maps-service-terms)

The applicable Google agreement can depend on the Google Cloud account, billing
address, and relationship with Google. Installing Pollen Levels is not itself
presented as acceptance of a Google Maps Platform customer agreement. These
terms do not replace or reinterpret Google's terms.

## Attribution

Pollen Levels uses the following project attribution for Google Maps Pollen API
content:

Google Maps — Source: Includes pollen data from Google

Google Maps attribution must remain visible. Users must not remove, hide,
obscure, or misrepresent Google Maps or pollen-source attribution when presenting
data produced by the integration.

## API key, billing, and quotas

You are responsible for:

- supplying your own Google Cloud API key;
- enabling the required API and billing;
- restricting and protecting the key;
- monitoring requests, quotas, budgets, alerts, and charges;
- rotating a key if it is exposed;
- complying with the agreement attached to your Google Cloud account.

Pollen Levels cannot guarantee free usage or prevent Google charges.

## Permitted use and data retention

Data from the Google Maps Pollen API must be used in accordance with Google's
applicable terms.

Under the current Pollen API service-specific caching terms:

- future Pollen API forecast values must not be retained for more than 24 hours;
- today's forecast values must not be retained for more than 365 consecutive
  calendar days;
- heatmap values must not be retained for more than 24 hours.

Pollen Levels does not use Pollen API heatmap tiles.

Pollen Levels does not retain its own stale Pollen API coordinator snapshot
beyond the fixed 24-hour runtime cache lifetime. This integration-owned cache is
separate from Home Assistant's local storage.

Pollen Levels excludes future `forecast`, `tomorrow_*`, `d2_*`, `trend`, and
`expected_peak` attributes from Home Assistant Recorder persistence. Recorder
may store current states and other non-excluded attributes according to the
user's configuration.

Home Assistant may independently generate long-term statistics, including
minimum, maximum, and mean aggregates, from eligible numeric entity states.
These locally derived statistics are not stored raw Pollen API response
payloads. The cited Google terms specify caching periods for Google Maps
Content, but they do not expressly classify these Home Assistant-generated
aggregates for retention purposes. This documentation therefore makes no legal
conclusion that such aggregates are either permitted indefinitely or prohibited
after 365 days. The Google Cloud project and API-key owner remains responsible
for the agreement applicable to that account.

Normal Recorder state history follows the user's configured retention and
purging. Home Assistant's hourly long-term-statistics aggregates are stored
separately and are not automatically purged by normal Recorder retention. Users
seeking a conservative interpretation can exclude the affected entities from
Recorder to prevent future history and statistics, then manage any existing
long-term statistics separately under **Developer Tools → Statistics**.
Excluding an entity does not remove statistics already stored for it.

Pollen Levels does not automatically purge Home Assistant Recorder history or
long-term statistics and cannot control the user's local database.

You must not use the integration to scrape, bulk-export, rehost, resell, or
create an independent historical pollen database from Google Maps Content.

## Health and safety

Pollen data, risk levels, health recommendations, trends, and forecasts are
informational. They may be delayed, incomplete, unavailable, or inaccurate.

They are not medical advice. Consult qualified healthcare professionals for
medical decisions.

Do not use the integration for emergency, safety-critical, or life-critical
decisions.

## Availability and changes

Google can change API output, pricing, quotas, coverage, terms, or availability.
Home Assistant and Pollen Levels can also change. Uninterrupted operation is not
guaranteed.

## Open-source license and warranty

Pollen Levels is distributed under the repository's [MIT License](LICENSE).

The software is provided without warranties to the extent allowed by the
applicable license and law.

## Termination

You can stop using Pollen Levels by removing the integration from Home Assistant
and revoking or deleting the associated Google Cloud API key.

## Changes to these terms

Material changes to these terms will be published in this repository and
reflected by the file's last-updated date.

## Contact

Use the repository's [GitHub Issues](https://github.com/eXPerience83/pollenlevels/issues)
page for project contact and support.

Do not post API keys, complete authenticated API URLs, unreviewed diagnostics,
or precise private coordinates in public issues.
