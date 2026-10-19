# Tennis Evidence and Promotion Protocol (Challenger research only)

## Implemented modules
- `scripts/forecast_ledger.py`: local append-only JSONL forecast capture with generated/issued time, event identity, player orientation, all three model states, artifact SHA and commit. It rejects malformed probabilities and post-start records.
- `scripts/result_reconciliation.py`: requires independent confirmation, exact tour and player order, normal completion, plausible settlement timestamps. It does not fetch real outcomes.
- `scripts/prospective_grade.py`: read-only tour-level Brier/log-loss with point-in-time exclusion.
- `scripts/paired_evaluation.py`: matched-fixture-only comparison to avoid availability/coverage bias.
- `test/test_forecast_ledger.py`, `test/test_result_reconciliation.py`, `test/test_paired_evaluation.py`: boundary regression tests.

## Remaining blockers
1. LOCAL IS NOT DURABLE: GitHub runners are temporary. Provision a separate immutable append-only persistent archive, avoid overwriting prior predictions, and independently verify receipt time. Never claim `work/*.jsonl` is an archival solution.
2. NO VERIFIED OUTCOME FEED: plug in two independently sourced results with unique provider event IDs, documented settlement rules, postponements, walkovers, retirements, and manual adjudication for disagreements. A caller-supplied `source_agreement` boolean alone is NOT proof of independence.
3. FIXTURE IDENTITIES: current hashed fallback depends on names/start time and may change after rescheduling. Introduce a versioned canonical source-independent mapping with audited provider IDs and orientation, and maintain a supersession ledger.
4. DATA FRESHNESS: model states are frozen. Do not retrain without data licensing, feature availability timestamps, chronological data partitions and no test-period leakage.
5. PROSPECTIVE EVIDENCE: evaluate uncertainty bands and matched comparisons per tour/surface and confidence bucket. Do not present paired metrics from tiny samples as verified improvement.
6. AUTOMATION: wire durable capture/verified grading only after the preceding prerequisites pass. Make write failures visible, preserve old records and never substitute stale outputs as fresh.

## Promotion is prohibited without
- Frozen pre-registered experimental specification.
- Independent out-of-time evaluation with sufficient effective sample, including distinct ATP/WTA/Challenger slices.
- Paired Brier and log loss improvements, confidence intervals, calibration assessment, and no material subgroup regression.
- Tests for identity collisions, result disagreements, stale sources, late predictions, bad numerical data, withdrawal/retirement, duplicate feeds and restoration.
- Review of registered Champion digests and successful safe rollback exercise.

No implemented module changes Champion model outputs, weights or registration. No module here authorizes automatic Champion promotion or betting claims.
