# Tennis scan reliability and recovery runbook

This branch is Challenger-only. Do not modify or promote registered Champion weights.

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
1. **Audit fails:** read GitHub job log, review whether the new public source is safe, explicitly register only the reviewed file in `scripts/audit.mjs`.
2. **Runtime staging fails:** inspect pinned source URL availability and expected SHA; never substitute unverified data.
3. **One role has missing predictions:** inspect `coverage.model_missing_reasons`, verify player identities and data history, and leave unmatched predictions unavailable.
4. **Fixtures disappear:** inspect second observation and source status, plus `coverage.conflicting_matches` and `coverage.identity_diagnostics`.
5. **Publish fails:** inspect token permissions and the `scan-results` branch; main dashboard may still be valid, but keep stale detection enabled.
6. **CI fails:** do not merge or claim deployment success.

## Automatic Recovery Controller (challenger deployment)

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
