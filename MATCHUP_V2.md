# Experimental Tennis Matchup Intelligence V2 — implementation and evidence contract

**Experimental slot designation:** Matchup Intelligence V2 (research-only), backed by frozen v3.4-A inference. On the Challenger branch, the Experimental output has a new model ID, preserves identical v3.4-A probabilities as an auditable baseline, and attaches V2 feature readiness. It additionally outputs `work/matchup-v2-shadow.json`. Unvalidated feature deltas never alter match probabilities.

## Eight independently gated dimensions

| Family | Planned derived signal | Input evidence required | Now |
|---|---|---|---|
| Surface | opponent-adjusted surface serve/return residual | match-level serve/return and surface history, before match start | gated slot |
| Indoor/outdoor | venue-specific environment effect | verified venue cover type and conditioned historical sample | gated slot |
| Playing style | measured aggression, serve reliance, return/rally profile interaction | pre-match point or shot-level features, not subjective labels | gated slot |
| Head-to-head | sample-shrunk direct opponent history | verified historical completed matches before match time | gated slot |
| Fatigue | last 7/14-day workload, rest/travel and qualifying | timestamped match durations, locations and starts | gated slot |
| Injury | verified current availability uncertainty | publicly reported, attributed and timestamped evidence | gated slot; missing never means healthy |
| Weather | venue forecast wind, heat, humidity and precipitation | timestamped geolocated **forecast as known before match**, not retrospectively observed weather | gated slot |
| Physical traits | verified handedness, height and reach-style interactions | current provider bio and proven historical effect | gated slot |

These are **input contracts and bounded research feature channels, not a claim that all providers or calibrated transformations have been implemented**. No real trustworthy numerical feature extractor for style, injury, weather, or physical traits is available in the current repo, so their status is *missing*. It would be misleading to invent trait labels or adjust scores based on them.

Each accepted evidence field must have a match ID, recognized provider URL, 64-character provenance hash, strict pre-start observation timestamp, and minimum effective sample size. This is a defensive schema gate, **not** an independent cryptographic attestation of remote data; actual authenticated fetching and measured feature generation remain separate work. The shadow report surfaces missing-reason codes and never promotes itself into a betting probability.

### Stage gates for actual predictive integration
1. Implement independently documented pre-match data adapters by family, including provenance, temporal cutoffs, player identity verification, explicit source failures and non-guessing policies. Weather requires archived forecasts, injuries require publicly reported availability facts rather than medical speculation.
2. Fit coefficients from **past** data only and compare out-of-sample ablations versus the same unchanged registered v3.4-A predictions. Use match-day embargo/purging for temporal leakage.
3. Measure coverage, log loss, Brier, calibration curves, tour/surface slices and confidence intervals, including error rates and missingness.
4. Keep zero-covariate baseline intact and decline promotion if evidence is incomplete or performance gains are not reproducible.
5. Register a new challenger artifact only after prospective shadow outcomes and explicit approval; never overwrite `Champion` or registered `Experimental v3.4-A`.

This Challenger branch replaces the **Experimental slot identity** with V2, not the registered Champion or underlying v3.4-A artifact. Live publication requires validated integration and a deliberate PR merge. Feature adapters remain unavailable until they are independently sourced and prospectively tested.
