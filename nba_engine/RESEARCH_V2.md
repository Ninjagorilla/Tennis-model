# NBA V2 research blueprint (2026-10-20)

## Prior WNBA lessons
- Build minutes -> rotation -> possession -> usage -> opportunities -> correlated outcomes.
- WNBA rebound accounting reduced MAE but worsened bias: do not promote on one metric.
- Arithmetic matchup pace previously overprojected totals; test geometric pace with league shrinkage.
- Four Factors are explanatory inputs; avoid double-counting them on top of team offensive rating.
- Separate NBA calibration from WNBA and isolate market information from fundamental forecasts.

## External model references
- DARKO: https://www.darko.app/about (time decay, Kalman-type updates, age and role effects)
- EPM: https://dunksandthrees.com/about/epm (player impact priors and adjusted plus-minus)
- FiveThirtyEight: https://fivethirtyeight.com/methodology/how-our-nba-predictions-work/ (rotation-based team projections)
- Court Vision: https://github.com/neeljshah/court-vision/blob/master/docs/models/possession-simulators.md (shared possession pie)
- Basketball-Modelling: https://github.com/DanielTomaro13/Basketball-Modelling (Elo and walk-forward baselines)
These are research inspirations; no proprietary weights or trained models are copied.

## New isolated utilities
- Advanced module adds injury-aware 240-minute allocation, shared usage, decay with prior, geometric pace and descriptive Four Factors.
- Ledger freezes pre-tipoff independent forecasts with source provenance, market separation and hash.
- Tests cover redistribution, leakage, pace and market firewall.

## Must complete before promotion
1. Source NBA-specific historical possessions, stints, injuries, lineups, rotations, player rates and actual historical market lines.
2. Constrain rotation realism: 5 on court, <=48 regulation minutes/player, 240 team minutes; explicit overtime scenarios.
3. Replace independent Poisson player draws with coherent lineup-conditioned possession/event simulation.
4. Train NBA-specific player impact, per-stat recency decay and empirical residual distributions.
5. Fit parameters on rolling training sets; use disjoint calibration and final holdout.
6. Test Brier, log loss, spread/total MAE, prop bias, coverage, subgroup calibration and closing-line value.
7. Require complete live-provider verification, source failover, alerts, prospective shadow grading and approved promotion.
No model accuracy, edge or profitable bet is claimed.
