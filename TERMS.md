# Terms of Use

Last updated: July 10, 2026

These terms are provided for the Pollen Levels Home Assistant custom integration.
They are not legal advice and do not state that the project has received legal
review, Google certification, or guaranteed legal compliance.

## Scope

These terms cover use of the Pollen Levels custom integration.

Pollen Levels is an independent open-source project. It is not affiliated with,
sponsored by, or endorsed by Google or the Home Assistant project.

## Google Maps features and content

Pollen Levels includes Google Maps features and content supplied through the
Google Maps Pollen API. Use of those features and content is subject to the
current [Google Maps End User Additional Terms](https://maps.google.com/help/terms_maps/)
and the [Google Privacy Policy](https://policies.google.com/privacy).

Google Maps Platform terms and service-specific terms may also apply to your
Google Cloud account and use of the API, including:

- [Pollen API policies and attribution](https://developers.google.com/maps/documentation/pollen/policies)
- [Google Maps Platform Terms](https://cloud.google.com/maps-platform/terms)
- [Google Maps Platform Service Specific Terms](https://cloud.google.com/maps-platform/terms/maps-service-terms)
- [Google Maps Platform EEA Terms](https://cloud.google.com/terms/maps-platform/eea)
- [Google Maps Platform EEA Service Specific Terms](https://cloud.google.com/terms/maps-platform/eea/maps-service-terms)

The Google agreement applicable to you can depend on your Google Cloud account,
billing address, and relationship with Google. These terms do not replace or
reinterpret Google's terms.

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

Pollen Levels excludes future forecast-derived attributes from Home Assistant
Recorder persistence, but it does not automatically purge Home Assistant
Recorder history. Users configuring Home Assistant Recorder retention beyond 365
days must exclude Pollen Levels entities or otherwise prevent current pollen data
from being retained beyond the applicable limit.

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
