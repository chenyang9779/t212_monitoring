# Security

## Reporting security issues

**Do not report security vulnerabilities through public GitHub issues.**

If you discover a security issue involving API credentials, data exposure, or any other sensitive vulnerability, please report it through [GitHub Security Advisory / Private Vulnerability Reporting](https://github.com/chenyang9779/t212_monitoring/security/advisories/new).

## API credentials

- Always use **read-only** Trading 212 API keys for the monitoring service.
- Never grant execution or order permissions to the monitoring API key.
- If a credential is ever committed to this repository or discovered in a public place, **revoke and rotate it immediately** through the Trading 212 developer portal.

## SQLite database

The SQLite database (`data/monitor.db`) stores historical portfolio, position, and transaction data. This is sensitive financial account data:

- **Do not commit** database files to any public repository.
- **Do not share** database files that contain real account information.
- Backups should be treated with the same sensitivity as API credentials.

## Network exposure

- The default configuration binds to `127.0.0.1` only (localhost).
- Do not expose the dashboard or API ports directly to the internet.
- For remote access, use SSH tunneling, Tailscale, VPN, or an authenticated reverse proxy.

## Third-party dependencies

Security advisories for dependencies should be evaluated for relevance to this project. Use `pip-audit` to check for known vulnerabilities.
