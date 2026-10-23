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


## Missing-feeds development branch — October 19, 2026

Active development branch: challenger/experimental-v2-missing-feeds-20261019 (branched from merged PR #23 on main). This is NOT a new production model or Champion promotion.

Implemented research adapters (scripts/v2_missing_feed_adapters.py):

- **Weather:** Free Open-Meteo hourly forecast retrieved before the match, only with a separately reviewed *court location* and indoor/outdoor metadata. Saves forecast-hour measurements, API URL, actual downloaded response SHA-256, and retrieval timestamp. No city-center or historical actual-weather fallback. Indoors is marked not applicable. A source-reviewed venue catalog is still needed for actual live coverage.
- **Observed workload:** Timestamped match completion data permit observed 7/14-day counts, documented court minutes, and time since the most recent observed completion. This is never a claim of comprehensive workload. Old tournament-week date proxies are disallowed. External source capture and reconciled complete coverage remain missing.
- **Public availability notices:** Only attributed, officially published, fixture-specific participation statuses; missing notices are UNKNOWN, not healthy. Source links and timestamps are validated, but the actual notice bytes are NOT independently authenticated by this adapter. A reliable public-notice fetcher remains missing.
- **Travel and shot-level playing style:** Still blocked pending exact venue routing and detailed point-by-point/shot feeds.

scripts/run_v2_missing_feeds.py runs in Challenger CI without network by default and writes work/v2-missing-feeds.json. It reports coverage gaps and why observations cannot be made. Opt-in weather requests require --enable-weather-fetch with a reviewed --venues catalog. Exact workload requires --completed-matches and --player-ids. Official participation updates require --availability.

All new evidence remains descriptive: win_probability_adjustment is null. No production model, probability, calibration coefficient, Champion, or registered engine artifact is changed. Future production integration is conditional on verified sources and prospective out-of-sample calibration.


## Phase 1/2 — verified provider identity and recent completed-match coverage

New files:
- scripts/v2_phase12_pipeline.py: reads source athlete IDs from the scheduled ATP/WTA tennis feeds. Identity is tour + provider + athlete ID. Names are labels, never an assumption that IDs from two providers are equivalent. Historical finals are linked to response SHA256 receipts; conflicting final results for a repeated match ID are withheld.
- scripts/scan.py: preserves public provider-scoped source_player_ids and source_event_id as extra research metadata without affecting win probabilities.
- scripts/run_v2_phase12.py: optionally reads up to 14 days of ESPN ATP/WTA completed results with bounded concurrent requests, and computes observed 7/14-day completed-start counts. Writes work/v2-phase12-evidence.json.
- scripts/run_v2_missing_feeds.py: automatically uses source-scoped fixture IDs where present, instead of classifying every match as missing identities.
- Challenger integration: invokes Phase 1/2 verification after a successful 3-model scan and retains the research report in diagnostics.

Observed initial live integration October 19, 2026 (run 39352282631):
- 36/36 scheduled match fixtures had source-scoped ESPN athlete IDs.
- 36/36 had tournament city context, but none had an independently verified court-level address or GPS location.
- 700 recent completed-match observations from 30/30 successfully fetched ESPN day-and-tour feeds.
- 57 of 72 player sides had at least one observed completed match with a scheduled start within 14 days. This is observed partial coverage, NOT a complete record of each player's recent history.

Important precision limits:
- An ESPN scheduled start and the time a scoreboard was first observed as final are NOT an actual finish timestamp. Exact duration, rest hours and minutes played remain unavailable (null). Do not convert these timestamps into fabricated fatigue or court-minute load.
- Tournament city and published indoor/outdoor classification do NOT establish exact court coordinates; weather requests need independently verified locations.
- The original historical archive uses tournament-week dates, which are unsuitable for exact match-level rest. The new completed-match feed is prospective research context, not a certified historical point-in-time backtest.
- Existing production Champion and Challenger models, registered artifacts and Experimental v3.4-A derived scores remain unchanged. New features are research-only and need prospective validation before affecting probabilities.
