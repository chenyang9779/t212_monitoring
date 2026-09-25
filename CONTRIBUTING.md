# Contributing to Trading 212 Position Monitor

Thank you for your interest in this project.

## General workflow

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-change`).
3. Make your changes.
4. Run the full test suite: `python -m pytest -q`.
5. Run static checks: `python -m compileall -q app tests`.
6. Commit with clear, descriptive messages.
7. Push to your fork and open a pull request.

## Security-sensitive changes

**Do not commit API keys, secrets, account identifiers, or unredacted portfolio data.** This includes:

- Trading 212 API credentials (`T212_API_KEY`, `T212_API_SECRET`)
- Real SQLite database files (`data/monitor.db*`)
- Personal account data, portfolio snapshots, or transaction exports
- Screenshots containing real financial data

Any accidental commits containing credentials should be treated as compromised and rotated immediately.

## Broker execution separation

This repository is **read-only**. Broker execution functionality (order placement, trade management) should live in a **separate** service or repository. If a quant/execution service consumes data from this monitor, the dependency must be one-way: execution reads from the monitor, not the other way around.

## Reporting issues

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md) or [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

## Pull requests

Please ensure:

- All tests pass
- No secrets or real portfolio data are included
- README is updated if behavior changes
- Monitoring remains read-only
- Security implications are considered

See [PULL_REQUEST_TEMPLATE](.github/pull_request_template.md) for the full checklist.
