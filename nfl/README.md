# Full NFL integration

This directory contains the complete recovered NFL-v9.1-integrated-1 Python engine and a separately fitted first-touchdown Research Challenger 0.2.1. Tennis model artifacts and scoring code are unchanged.

## Actual coverage

The original engine includes joint integer scores and player opportunity simulation; moneyline, spread, game and team totals; passing, rushing and receiving count/yardage props; anytime and 2+ TDs; scenario-dependent quarterback effects; same-draw joint probabilities; quote comparison; immutable freezes; and outcome settlement. The static website receives only an allowlisted public status record. It is not an interactive Python server and it cannot place bets.

The new first-TD estimator uses separate game-first and team-first risk sets. It estimates cause-specific quarter hazards and player scoring shares from strictly earlier games, with explicit unknown-scorer and no-touchdown probability. All overtime is pooled into a fifth interval. Its sparse overtime risk is smoothed rather than presented as a high-confidence fitted effect.

## Evidence and release gate

- Original runtime: 95 tests passed after repairing Parquet support.
- Existing first-TD core: 65 tests passed.
- Numeric JSON export: identical predictions for 1,473 feature rows and one exact seeded 6,000-draw joint forecast. No executable pickle is shipped to the public service.
- Historical data: 1,504 completed games from 2021 through October 15, 2026. Scoring aggregates reconcile for every game/team.
- First-TD fit: 2022-2023. Temperature calibration: 2024. Retrospective test: 365 later games, with 730 team-first contracts.
- Corrected provider chronology uses `order_sequence`, not numeric `play_id`. The earlier provisional analysis that excluded 12 games for apparent final-score mismatches is retained in the local audit package, not used for publication.
- The parameter fitting and temperature grid were unchanged after this data-ordering repair. The evaluation is retrospective and is not represented as untouched prospective evidence.
- No new Champion promotion, pricing edge, ROI or profit claim is made.

The website's NFL publication gate remains **closed**. The full engine executes for paper forecasting, but its current probabilities are not put into the public forecast list. Research evaluation, runtime health, supported markets and verified future fixture identities are visible. A reviewed release must explicitly approve publication after sufficient prospective evidence; engineering tests or one favorable historical metric do not auto-promote the model.

## Reproduce

From the repository root, install `requirements.txt`, then run:

```sh
PYTHONPATH=nfl:nfl/engine python -m pytest nfl/tests -q
python nfl/pipeline.py
npm run build
```

The pipeline downloads public data into temporary working storage. It verifies pinned historical hashes, checks current schedule identity and kickoff against ESPN both before and after inference, refreshes team/player state without refitting the original scoring coefficients, executes all supported markets, and writes an immutable paper freeze. Questionable-player participation is not assigned an invented numerical probability. Inference failures become explicit blocked status records and do not substitute a different model or prevent tennis publication.

Only small paper-freeze artifacts are retained for grading. No raw history, binary model, personal ledger, credentials or betting-account connection is published. No paid host, private runner, purchased domain, billing setting or card entry is required. Future-season and historical-source changes require explicit review.


## Prospective paper records

The original parameters remain fixed while pregame state is refreshed. Each paper forecast includes paired first-TD baseline probabilities. The grader verifies immutable hashes and pre-kickoff timestamps, admits only independently checked pregame freezes, maps unseen scorers to the correct team residual and counts each game/parameter pair once. Small daily artifacts carry unresolved forecasts and cumulative result rows forward. Retrospective records and local offline replays are rejected as prospective evidence. Game-winner probabilities are also scored when reconciled final scores exist. Player-stat bet settlement remains withheld without participation and market-contract evidence.

The 2026-only game-first subgroup worsened versus the baseline: log loss 3.2054 versus 3.1879, Brier 0.9385 versus 0.9348. That is a material reason to preserve the closed publication gate despite favorable aggregate results. The current prospective sample starts at zero. There is no automatic promotion function.
