# Independent audit remediation: controlled rollout (2026-10-20)

This branch is **not a production promotion**. All old model artifacts, registries,
runtime configuration, worker selection, workflows and deployments are unchanged.

## Audit findings and immediate policy
- WTA blended Champion: reported Oct 5–14 forward Brier 0.2668, worse than
  constant 0.50 (0.25); this is **auditor-reported, not yet independently reproduced**.
  Candidate research alternatives: SR Challenger (reported 0.2548) and Elo-only.
  **WTA blend is targeted for SHADOW demotion, but live routing is NOT changed by
  this branch.** Do not assert the switch happened.
- ATP Champion: auditor-reported 261-match-window ATP accuracy 67.5%, Brier
  0.2110. Retain as research-only pending larger prospective evaluation.
- Existing mixed-vintage SR/Elo blend coefficients do not have an auditable
  self-consistent blend-fit trail. Historical blend metrics are **NON-CITABLE**
  as evidence of its prospective superiority until independently reproduced.
- No captured Phoenix Unified v2 code or test receipt is present in this branch.
  Do not claim its 28 tests or quoted scores were independently reproduced.

## Changes here
1. Correct misleading provenance docstring in native Champion wrapper.
2. Reject unmatched player Elo/history instead of inventing neutral priors.
3. Reject missing serving/returning exposures in the Champion wrapper.
4. Remove unfitted BO5 re-conversion of match-level Elo output.
5. Add regression tests for player-history and format behavior.

**Important:** the native Champion binds source file hashes at runtime.
Changing this source on a development branch intentionally does NOT update
registered hashes; a reviewed re-registration / migration plan is necessary
before activating. Do not bypass source hash checks.

## Subsequent gated phases
### P0 / service and labeling
- Confirm current production routing and isolate WTA blended score from
  actionable outputs. Prefer Elo-only if verified Elo observations are
  available; otherwise return NO_FORECAST rather than invent a probability.
- Preserve historical WTA blend as shadow-only with distinct model ID.
- Repair NFL first-TD settlement ordering to consume authoritative
  order_sequence, add reversed-play-ID canary and event-consistency validation.

### P1 / reproducible fitting
- Supply exact pinned vintage of SR coefficients, point observations, Elo
  histories, blend-fit script and parameter derivation receipts.
- Derive walk-forward OOF predictions on immutable fit/validation windows.
- Fit ATP/WTA temperature on disjoint validation only; fit and score
  disjointness must be mechanically enforced.
- Gate jointly on four exposures (each player's serve and return points)
  and each player's Elo completed-match count.
- Quarantine Experimental V3.4-A update labels from evaluation labels;
  require out-of-fold residuals and disjoint temporal windows.

### P2 / research and benchmarking
- Add Elo uncertainty and layoff recovery with prospective ablations.
- Monthly 365-day-decay SR refit; freeze until independent paired gate passes.
- Deduplicate fixture IDs, preserve date/surface/edition in stable IDs.
- Content-hash fetched evidence bytes, not merely hash-formatted strings.
- Capture timestamped pre-match odds, no-vig market probability, closing
  prices and CLV (only where legally/technically available).
- Publish rolling-origin common-sample paired Brier and log-loss,
  bootstrap uncertainty and pre-registered rules (minimum n=200).
- Rebuild NBA possession mechanics and verify against real score/usage data.

## Promotion policy
RESEARCH → REPRODUCIBLE → BACKTESTED → PROSPECTIVE_SHADOW
→ PROMOTION_ELIGIBLE → ACTIVE_CHAMPION.

No automatic promotion solely from this branch. Require source-complete
reproduction, hash-valid provenance, independent holdout, point-in-time
assessment, paired confidence intervals excluding material harm,
market benchmarking and explicit operator approval.
