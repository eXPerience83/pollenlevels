# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| Latest 2.x release | Yes |
| Older releases | No, unless explicitly stated |

## Reporting a Vulnerability

Please do not open public GitHub issues for security reports.

Use GitHub Security Advisories or private vulnerability reporting if available.
If those options are not available, contact the maintainer through GitHub.

When reporting a vulnerability, include:

- The affected Pollen Levels version.
- The Home Assistant version in use.
- Clear reproduction steps.
- The expected impact.
- Whether secrets, API keys, diagnostics exports, or sensitive location data may
  have been exposed.

## Security Expectations

Do not share Google API keys, full debug logs, or exact coordinates publicly.

Review diagnostics exports for any sensitive information before sharing them.

If an API key or other secret was exposed, rotate it immediately and review its
usage in the relevant provider console.
