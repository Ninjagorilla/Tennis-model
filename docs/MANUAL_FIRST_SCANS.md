# Manual-first tennis fixture policy

Applies to every user-requested tennis scan: ATP, WTA, ATP Challenger and WTA 125, including requested qualifying where verified.

## Source of truth and no auto fixture ingest

By default, `scripts/collect.py` reads only `data/manual_fixtures.json` and performs no fixture network requests. An empty ledger means zero eligible matches, **not** that the day's slate is empty. The historical automatic discovery path is available only when explicitly set to `TENNIS_FIXTURE_MODE=legacy` for diagnostic research, and is not an authorized production substitute.

## Required procedure, every scan

1. Establish requested dates and time zone; independently list all active events across all four tour categories.
2. Check official tournament draws AND dated official order of play. If one is missing, use a second independently authoritative tournament or governing-tour source. Do not substitute a stale published schedule for current match status.
3. Manually transcribe each verified scheduled singles match into `data/manual_fixtures.json`, preserving the official URLs, verified source player IDs, surface, round, start (ISO time with offset), reviewer, and review time. Do not invent IDs, times or players. Recheck postponements and withdrawals immediately before inference.
4. Review cross-source identity and fixture-count reconciliation for each tour, tournament and requested date. Zero Challenger matches is an explicit coverage gap unless a confirmed official slate is empty.
5. Run registered Champion, Challenger and Experimental models on these fixtures only. No model artifact, promotion or calibration changes.
6. Repeat ledger validation and identity checks after inference. Reject changed/started fixtures and duplicate or stale ledger records. Reject invalid manual rows rather than silently treating the run as complete.
7. Publish with explicit per-model missingness, per-tour/date fixture coverage and freshness/expiry. Any missing tour/draw/source remains **partial**; stale stored outputs never count as new forecasts.
8. Preserve immutable source receipts and the ledger snapshot for offline recovery. Update historical data separately on a documented weekly/monthly cadence, with training cutoffs and reproducible checks.

## Recovery order

* First: manually re-open original official draw and order-of-play links and correct the ledger, retaining prior versions.
* Second: consult a different official tournament/tour source, verify disagreements and annotate unavailable entries; no synthetic fixtures.
* Third: rerun locally using the last fully verified **current** ledger and pinned offline model artifacts, after a new status/time review.
* Fourth: archived source receipts and prior ledger snapshots are **audit/reconstruction backups only**, never publish them as fresh scans.

**Operational limitation:** This repository cannot automatically research the official order of play, supply human review, or populate the ledger. A person/agent must do so at each scan. Full two-day coverage is not established by a successful workflow alone. If the ledger is empty, the scan has no valid forecasts; raise a coverage alert and stop, rather than using the old feed or cached outcomes.
