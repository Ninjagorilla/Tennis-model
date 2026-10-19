# Tennis scan reliability and recovery runbook

This branch is Challenger-only. Do not modify or promote registered Champion weights.

## CI regression prevention (primary)
- The source audit automatically approves **only** new root-level `scripts/*.py`, `scripts/*.mjs`, `test/test_*.py`, and `test/*.test.mjs` files. It checks UTF-8, size, symlinks, suspicious content, total payload size, and pinned manifest digests. New workflows, site assets, data, and engine/NFL artifacts still require explicit review in `scripts/audit.mjs`.
- The audit reports **all** disallowed tracked paths in one CI failure, rather than surfacing a new missing path on each run.
- Pull-request builds run the deterministic audit, Node/Python regression checks, and site build without external live-score dependencies. Production `main` performs live forecasting, and `challenger-integration.yml` provides a separate real-data challenger scan.
- The separate Challenger live workflow installs pinned Python dependencies **before** Python test collection; its branch filter covers future `challenger/**` branches. A live `NO_AVAILABLE_SCAN` remains an explicit failure of the live integration gate, not a fabricated green prediction.
- Tests ensure that the PR workflow cannot silently regain its live-feed dependency and that the source approval pattern never admits model weights or unknown workflow files.
- No change to Champion model artifacts, hashes, promotion rules, or result probabilities. A green PR verifies build quality; it is **not** evidence that live predictions are available.

## Primary architecture (preferred)
1. GitHub Actions on main runs the security source allowlist, Node/Python tests, manifest digest verification, pinned historical inputs, three 4-case model preflights, and a double-observed 24-hour fixture scan.
2. Fixture identities use tour + audited full-name aliases + tournament key + regime. Conflicting surfaces, formats, or material start-time discrepancies fail closed. Never merge different opponents by fuzzy similarity.
3. Every model returns an explicit `ok` or `unavailable` status. Experimental missing data must be diagnosed by reason, never silently filled with the Champion or a guess.
4. Every forecast includes provenance (model id, fitted state date, artifact hash), and Devil's Advocate output is **read-only**.
5. The main dashboard retains `last-success.json`. The independent `scan-results/public-results/latest.json` is updated **only** for available scans; consumers must enforce its `expires_at` timestamp.

## Backup paths
- **A: Latest valid published snapshot.** Read the independent results branch, confirm `prediction_status=available`, `expires_at` in the future, source commit, and three model statuses before presenting. If expired, label historical/stale, never current.
- **B: GitHub Pages `data/last-success.json`.** Use only after confirming matching schema and freshness. Never substitute cached predictions for live fixtures.
- **C: Existing scheduled/dispatch workflows.** Rerun the same pinned commit and review job logs and preflight output. An `unavailable` model is not a successful full three-model scan.
- **D: Offline pinned replay.** `OFFLINE_RUNTIME` supplies *only verified pinned historical data* for `scripts/runtime.py`. The runtime checks SHA-256 hashes before any inference. Preserve snapshot source timestamps and never label replay as a fresh live run.
- **E: Diagnostic degraded mode.** Show available model results individually, with missing role and reason counts. Withhold a three-model average unless all three returned valid probabilities.
- **F: Rollback.** If Challenger tests or source audit fail, keep main untouched and return to last registered working commit. Never replace Champion artifacts or change model registration in response to missing data.

## Verification before merging
- Run `npm run audit`, `npm test`, `python -m unittest discover -s test -p 'test_*.py'`, and NFL regression tests from the workflow.
- Check duplicate aliases, schedule conflicts, full/missing model predictions, Devil's Advocate abstention and non-mutating behavior.
- Execute a real scan on a pinned commit and report the number of fixtures, per-model predictions, unavailable-reason counts and duplicate collapses.
- Confirm site publication never exposes failed or expired predictions as current.
- Keep PR draft until CI passes and reviewer verifies actual coverage. Model promotions are governed by prospective scoring, not a single scan.

## Incident triage
1. **Audit fails:** inspect the complete list of rejected paths. Ordinary root-level scripts and tests are handled by `public-path-policy.mjs`; review and register only new workflows/assets/other files explicitly in `scripts/audit.mjs`. Never blanket-allow engine or NFL artifacts.
2. **Runtime staging fails:** inspect pinned source URL availability and expected SHA; never substitute unverified data.
3. **One role has missing predictions:** inspect `coverage.model_missing_reasons`, verify player identities and data history, and leave unmatched predictions unavailable.
4. **Fixtures disappear:** inspect second observation and source status, plus `coverage.conflicting_matches` and `coverage.identity_diagnostics`.
5. **Publish fails:** inspect token permissions and the `scan-results` branch; main dashboard may still be valid, but keep stale detection enabled.
6. **CI fails:** do not merge or claim deployment success.

## Automatic Recovery Controller (production workflow and challenger live CI)

`python scripts/recovery_controller.py` runs an actual inference scan and validates its output, with **a maximum of two attempts** and an eight-second pause between attempts. A second attempt runs the normal source collection and the original frozen models from scratch. A scan with failing preflights, invalid probabilities, duplicate identities, no usable predictions, or unavailable public data sources fails closed. A healthy empty schedule can succeed as `unavailable`, but **never represents predictions that were not produced**.

After two failures, `scripts/backup_select.mjs` checks three allowlisted sources, independently validates schema and time bounds, and selects the newest **unexpired** successful snapshot:
1. Independent `scan-results` branch on GitHub.
2. Pages `data/last-success.json`.
3. Pages `data/status.json`.

Backup selection reports the source and original timestamp but **never writes it as a new scan**, never changes fixture dates, never conceals staleness, and returns a nonzero exit code so GitHub Actions alerts. All sources reside on GitHub infrastructure; they are distinct publication paths, **not** independent disaster-proof hosting. A complete GitHub outage still needs a separately provisioned off-platform replica.

For production failures, a separate least-privileged `alert` job opens or comments on one **Tennis pipeline recovery needed** GitHub issue, allowing normal GitHub notifications. It requires Issues permissions and the user's GitHub notification settings; email/push notification delivery is not guaranteed. Recovery reports and snapshots are uploaded as 7-day workflow artifacts when present. A failure does not publish backup data as current.

## Verified rollback procedure

1. Identify the last known-good **40-character commit SHA**, inspect its CI history, and fetch it into the local checkout.
2. Verify preserved registered sports model data before allowing a rollback:
   `python scripts/verify_rollback.py --target <FULL_COMMIT_SHA>`.
   This checks `engine/manifest.json`, `engine/native/registration.json`, and `nfl/manifest.json` byte-for-byte against the current branch. A changed or unavailable artifact blocks rollback.
3. Create a separate rollback PR that reverts **only the faulty workflow/controller commit(s)**, then rerun the security audit, all tennis/NFL tests, and the end-to-end scan. Never force-push or automatically rewrite `main`.
4. Preserve `scan-results` history, historical timestamps, and old deployed outputs during the rollback. Deploy only after CI passes.

The verified known-good registered-model baseline from before this controller is `69d997c4c6a1f8765f05014fdb6a898d8701bd91`. CI runs a read-only compatibility check against it. That is not an automatic rollback; issuing a rollback PR remains an explicit human-controlled operation.

## Disaster recovery tests

- Two-attempt limit, transient recovery, persistent failure, corrupted and expired backups, unapproved host URLs, and no off-platform backup.
- Refuse stale scans and stale timestamps; never compute a three-model average from missing predictions.
- Reject ambiguous rollback refs or altered Champion/NFL artifacts.
- Perform full CI and a live three-model scan on the Challenger branch before merging.


## Persistent tennis evidence and result-source recovery (Challenger evidence layer)

Production `main` only: `scripts/forecast_ledger.py` captures published **pre-start** research probabilities, including original issued timestamps, opponent orientation and model hashes. `scripts/gh_evidence.py` writes a content-addressed JSON receipt to `tennis-evidence`, performs byte-for-byte readback, and writes a second copy to `scan-results`. Existing paths are never updated with new bytes. `scripts/retrieve_evidence.py` validates record digest and the **GitHub server commit timestamp** against actual scheduled start, then selects the earliest verified pre-match forecast. A late archival receipt is not eligible for prospective grading, even if its JSON claims an earlier issued time.

**Storage recovery priority**:
1. Primary `tennis-evidence:evidence/forecasts/YYYY/MM/DD/RUN_ID/SHA256.json`.
2. Mirror `scan-results:` at the exact same receipt path. Reading a failed/empty primary falls back to the mirror.
3. A `tennis-evidence-RUN_ID` GitHub Actions artifact, retained up to 90 days, only if uploaded successfully. Manual recovery: download this artifact from the original workflow run; inspect `tennis-forecast-ledger.jsonl`; with a token scoped to repository contents write, use `python scripts/gh_evidence.py tennis-forecast-ledger.jsonl --run-id ORIGINAL_RUN_ID`. Verify both remote receipt statuses and their hashes. Never overwrite existing conflicts, reset branch history, or present restored forecasts as new live predictions.

All destinations are GitHub-hosted. This design tolerates a branch/write failure, **not** a complete GitHub outage, deletion across all branches/artifacts, or an untrusted repository administrator. An off-platform encrypted replica, if later provisioned, remains necessary for true disaster recovery. Reports explicitly flag failed remote writes. Evidence artifacts and results archive contain only public research data.

**Results primary**: `scripts/tennis_result_sources.py` fetches independently published ESPN tennis scoreboards and Tennis.com completed-match records. Require confirmed completed singles, two identified competitors, same tour, source event ID where available, consistent pre-match time context, same winner, provider URL and response hash. Retirements, walkovers, disagreements, ambiguous aliases and missing sources remain withheld. `scripts/result_reconciliation.py` rejects mere asserted agreement, and `scripts/paired_evaluation.py` reports metrics only on a common model-availability sample.

**Results fallback strategies**:
1. Replay the already verified and content-addressed `evidence/results` observations from `tennis-evidence` or the `scan-results` mirror when live publishers change their schema or become temporarily unavailable. A replay preserves the original observation date and does not claim a newly completed match.
2. Quarantine results for human adjudication using the official ATP/WTA tournament draw/score documents and the available publisher record. Record authentic source URLs, event IDs and hashes before importing any independent verification. **This official-source adapter is not automated**; no single-source auto-grade or invented status is permitted.

Scheduled daily reconciliations fetch historical forecast receipts and preserve result receipts and provider health. Successful code tests or a green workflow alone do not mean there are enough verified matched results for calibration, statistical improvement or Champion promotion.
