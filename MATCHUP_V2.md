# Experimental Tennis Matchup Intelligence V2 — implementation and evidence contract

**Experimental slot designation:** Matchup Intelligence V2 (research-only), backed by frozen v3.4-A inference. On the Challenger branch, the Experimental output has a new model ID, preserves identical v3.4-A probabilities as an auditable baseline, and attaches V2 feature readiness. It additionally outputs `work/matchup-v2-shadow.json`. Unvalidated feature deltas never alter match probabilities.

## Eight independently gated dimensions

| Family | Planned derived signal | Input evidence required | Now |
|---|---|---|---|
| Surface | descriptive historical surface serve/return competence (not yet opponent-adjusted) | SHA-checked archive with 21-day tournament-date embargo | **measured historical context** |
| Indoor/outdoor | published indoor/outdoor category; no calibrated effect | Tennis.com tournament surface metadata | **implemented as descriptive venue input** |
| Playing style | observed serve-reliance proxy; no shot-level aggression/rally classification | pre-match aggregate service/return points | **implemented as proxy only** |
| Head-to-head | completed direct-match wins (3+ minimum) | archive matches, 21-day conservative date embargo | **implemented as descriptive H2H** |
| Fatigue | last 7/14-day workload, rest/travel and qualifying | timestamped match durations, locations and starts | gated slot |
| Injury | verified current availability uncertainty | publicly reported, attributed and timestamped evidence | gated slot; missing never means healthy |
| Weather | venue forecast wind, heat, humidity and precipitation | timestamped geolocated **forecast as known before match**, not retrospectively observed weather | gated slot |
| Physical traits | verified reported historical handedness/height, no effect coefficient | SHA-checked historical player-bio CSV fields | **implemented as descriptive bio context** |

**Real implemented historical adapters:** `scripts/historical_matchup_features.py` calculates observed serve/return surface competence, a serve-dependence playing-style proxy, and 3+-meeting H2H, with verified source hashes and 21-day tournament-date proxy exclusion; it also extracts descriptive height and handedness. `scripts/tenniscom.py` preserves indoor/outdoor tournament metadata. `scripts/runtime.py` adds a retrieval receipt timestamp after checking pinned CSV hashes. The old v3.4-A probability is still the only forecast; V2 exposes *observed measurements*, not arbitrary additive effects. No verified injury, weather, exact fatigue/rest or fine-grained shot-style data has been connected. No claim of improved Brier, accuracy or calibration is made.

Each accepted evidence field must have a match ID, recognized provider URL, 64-character provenance hash, strict pre-start observation timestamp, and minimum effective sample size. Historical archive data have week-start date proxies, NOT exact match times; this precludes accurate rest/fatigue estimates and certified historical point-in-time backtesting. This is a defensive schema gate, **not** an independent cryptographic attestation of remote data; actual authenticated fetching and measured feature generation remain separate work. The shadow report surfaces missing-reason codes and never promotes itself into a betting probability.

### Stage gates for actual predictive integration
1. Implement independently documented pre-match data adapters by family, including provenance, temporal cutoffs, player identity verification, explicit source failures and non-guessing policies. Weather requires archived forecasts, injuries require publicly reported availability facts rather than medical speculation.
2. Fit coefficients from **past** data only and compare out-of-sample ablations versus the same unchanged registered v3.4-A predictions. Use match-day embargo/purging for temporal leakage.
3. Measure coverage, log loss, Brier, calibration curves, tour/surface slices and confidence intervals, including error rates and missingness.
4. Keep zero-covariate baseline intact and decline promotion if evidence is incomplete or performance gains are not reproducible.
5. Register a new challenger artifact only after prospective shadow outcomes and explicit approval; never overwrite `Champion` or registered `Experimental v3.4-A`.

This Challenger branch replaces the **Experimental slot identity** with V2, not the registered Champion or underlying v3.4-A artifact. Live publication requires validated integration and a deliberate PR merge. Feature adapters remain unavailable until they are independently sourced and prospectively tested.
