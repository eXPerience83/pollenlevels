# Privacy Policy

Last updated: August 20, 2026

This policy describes how the Pollen Levels Home Assistant custom integration
handles data. It is not legal advice and does not state that the project has
received legal review, Google certification, or guaranteed legal compliance.

## Scope

This policy applies to the Pollen Levels custom integration and the project's
maintainer-operated support channels, such as GitHub Issues.

It does not replace the privacy policies of Google, Home Assistant, GitHub,
HACS, or your Home Assistant hosting provider or network provider.

## Project-operated collection

Pollen Levels has no project-operated backend service. The maintainer does not
automatically receive your Home Assistant configuration, API keys, coordinates,
sensor states, or usage data.

The integration does not contain project-operated analytics, advertising, or
telemetry.

## Data stored locally in Home Assistant

Pollen Levels stores configuration in Home Assistant config entries and config
subentries:

- the Google API key is stored in the parent config entry;
- location names, latitude, and longitude are stored in location subentries;
- integration options such as update interval and language are stored with the
  integration entry;
- entity states and attributes are available in Home Assistant;
- diagnostics can be generated on request;
- Home Assistant Recorder may store history according to your Recorder
  configuration.

Removing an integration config entry does not necessarily purge existing
Recorder history automatically.

## Data sent to Google

Your Home Assistant instance sends requests directly to the Google Maps Pollen
API. Relevant request information includes:

- API key;
- latitude and longitude;
- requested forecast days;
- optional language code;
- normal network metadata such as the source IP address.

Google's handling of this data is governed by the
[Google Privacy Policy](https://policies.google.com/privacy) and applicable
Google Maps Platform terms.

## Runtime cache, Recorder, and long-term statistics

Future forecast-derived attributes such as `forecast`, `tomorrow_*`, `d2_*`,
`trend`, and `expected_peak` remain available in the live Home Assistant entity
state for dashboards, templates, automations, and compatible custom cards.
Pollen Levels marks those attributes as excluded from Recorder persistence.

Current states and other non-excluded attributes may still be stored by Home
Assistant Recorder according to your Recorder configuration.

Pollen Levels does not retain its own stale Pollen API coordinator snapshot
beyond the fixed 24-hour runtime cache lifetime. This integration-owned runtime
cache is separate from Home Assistant Recorder history and long-term statistics.

Home Assistant may generate long-term-statistics aggregates for the numeric
Pollen Levels sensors that use `SensorStateClass.MEASUREMENT`. These minimum,
maximum, and mean values are derived locally from entity states rather than
stored raw Pollen API response payloads. The cited Google terms specify caching
periods for Google Maps Content but do not expressly resolve how these
Home Assistant-derived aggregates should be classified for retention purposes.
Users remain responsible for the Google agreement applicable to their Google
Cloud project and API key and control their local Home Assistant storage.

Normal Recorder state history follows the user's configured retention and
purging. Home Assistant's hourly long-term-statistics aggregates are stored
separately and are not automatically purged by normal Recorder retention. Users
seeking a conservative interpretation can exclude the affected entities from
Recorder to prevent future history and statistics, then manage any existing
long-term statistics separately under **Developer Tools → Statistics**.
Excluding an entity does not remove statistics already stored for it.

Pollen Levels does not automatically purge and cannot centrally delete or
control a user's Recorder history or long-term-statistics database.

## Logs and diagnostics

API keys are redacted from integration logs and diagnostics. Diagnostics use
approximate coordinates rounded to one decimal.

Diagnostics may contain Home Assistant entry IDs, subentry IDs, registry
summaries, runtime summaries, and pollen-related status data. Review diagnostics
and logs before sharing them publicly.

## Voluntary support information

The maintainer receives data only when you voluntarily submit it, such as in:

- a GitHub issue;
- logs;
- diagnostics;
- screenshots;
- configuration excerpts.

GitHub processes data under its own privacy terms. Do not submit secrets or
precise private coordinates.

## User control

You can:

- remove location subentries;
- remove the parent integration entry;
- delete or rotate your Google API key;
- change Home Assistant Recorder configuration;
- remove locally stored history using Home Assistant's own tools;
- delete or edit information you posted to GitHub, subject to GitHub's
  capabilities and policies.

## Data security

The integration uses Home Assistant's shared asynchronous HTTP session and local
config-entry storage. No system can guarantee absolute security.

## Changes and contact

Changes to this policy will be published in this repository and reflected in the
last-updated date.

Use the repository's [GitHub Issues](https://github.com/eXPerience83/pollenlevels/issues)
page for contact and support. Do not post API keys, complete authenticated API
URLs, unreviewed diagnostics, or precise private coordinates in public issues.
