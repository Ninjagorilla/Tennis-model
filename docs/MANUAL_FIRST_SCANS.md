# Tennis fixture inputs and coverage limits

## Current production behavior

`scripts/collect.py` discovers ATP/WTA main-tour fixtures through Tennis.com and ESPN. ATP Challenger and WTA 125 fixtures come from `data/manual_challenger_fixtures.json` via `scripts/manual_challenger.py`. The reviewed ledger remains a required production input for those two categories. Missing, invalid or empty ledgers supply no Challenger/WTA 125 forecasts; they do not prove an empty official slate.

The loader requires source links, distinct player IDs, a reviewer, a review timestamp within 12 hours, and a start within the next 48 hours. These checks validate submitted records, not the completeness or independent authenticity of the slate. Treat the ledger as untrusted input and verify its contents against current official draws and dated orders of play before use. Rejected entries cause the scan validator to fail. The scan rechecks accepted fixtures after inference and labels fixture coverage `partial`.

## Removed recovery path

`data/manual_fixtures.json` was an empty recovery artifact on this branch. Its all-tour loader was never called by the production collector or workflows. Both have been removed, and the file path is ignored and excluded from the public audit allowlist. Do not regenerate it as a production input.

The previous version of this document incorrectly claimed that production defaulted to an offline all-tour ledger with a `TENNIS_FIXTURE_MODE=legacy` switch. That switch was never implemented. Production still uses the sources described above.

## Coverage requirements still outstanding

This cleanup does not implement the requested America/Los_Angeles calendar window, independent per-tour/per-UTC-date reference counts and tolerance gate, or the October 21 Pacific / October 22 UTC-only regression test. Main-tour collection currently uses a rolling 24-hour window; the manual Challenger loader accepts 48 hours. A successful workflow does not establish complete coverage.

Before any full-coverage claim, define the requested Pacific window and its UTC bounds, fetch every overlapping UTC date, filter by fixture timestamp, and reconcile each tour/date against an independent reference. Missing references or counts below tolerance must block publication or retain an explicit PARTIAL label, with observed and reference counts reported for every tour/date. A fixture file cannot serve as its own completeness reference.

Champion registration, model artifacts, weights, routing and promotion rules are unchanged by this cleanup. Archived receipts and recovery snapshots remain reconstruction evidence, never fresh forecasts.
