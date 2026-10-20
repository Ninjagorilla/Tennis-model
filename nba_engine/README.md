# NBA Engine V1 (isolated research challenger)

No changes to Tennis or NFL Champions. No deployment, betting automation, scheduler, or production promotion.

## Current implementation
- Three distinct game models: baseline Champion candidate, experimental rest/recent-form/injury-impact adjustments, and adversarial stress test.
- Home win probability, expected margin and total; optional market comparison fields.
- Point-in-time timestamp validation, plausible-range checks, fixture identity and duplicate checks.
- CLI: `python -m nba_engine.cli fixtures.json`
- Tests: `python -m unittest discover -s tests -p 'test_nba_engine.py'`

## Required input
JSON array of fixtures with game_id, tipoff_utc, asof_utc, home and away team objects. Team objects require name, offensive_rating, defensive_rating and pace. Optional fields: net_rating_recent, rest_days, unavailable_impact, projected_minutes_confirmed. Market fields are optional. **No missing statistics are invented.**

## Critical limitations
The formulas and variance parameters are provisional research heuristics, **not fitted, calibrated, or validated NBA forecasts**. Do not present model percentages as betting edges or verified performance. Inputs are not fetched automatically. The current module does not yet simulate player minutes or produce player props. The 'Champion' label in output denotes a baseline *candidate*, not a registered Champion.

## Promotion gates
1. Add reliable historical team/player data ingestion with point-in-time snapshots, identity resolution and coverage thresholds.
2. Build possession/rotation/minutes-based player projections and correlated player-prop simulations.
3. Fit variance and parameters using walk-forward time splits, no post-tipoff leakage.
4. Report Brier score, log loss, calibration, ATS/total errors, prop hit-rate and market benchmarks.
5. Run live shadow forecasts, grade results, implement bounded retries, source failover, alerts and rollback tests.
6. Promote only after prospective evidence supports improvement and explicit approval.

## Source policy
Prefer NBA official schedules, gamebooks and official injury reports. Record retrieval timestamp and provider on each ingested snapshot. Reject incomplete fixtures rather than publishing stale or fabricated predictions.
