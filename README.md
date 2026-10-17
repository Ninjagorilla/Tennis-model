# Courtside tennis forecasts

[Open the site](https://ninjagorilla.github.io/Tennis-model/) · [Run history](https://github.com/Ninjagorilla/Tennis-model/actions/workflows/dashboard.yml)

A personal, static tennis site backed by scheduled GitHub Actions. It runs the recovered Champion **SR-Elo 1.0**, Challenger **SR-GLM 0.2**, and experimental **v3.4-A** on supported upcoming singles. The browser only receives public results. No account, server subscription, card, API key or paid data service is required.

## What actually runs

Every trusted main-branch run verifies all published runtime file hashes, downloads checksum-pinned public historical inputs into temporary runner storage, and reproduces four saved diagnostic predictions per model. Each model must pass its own checks before its predictions can be published. These checks establish recovery/port consistency, not calibration or predictive accuracy.

The collector reads ESPN and Tennis.com's public daily schedules for the next 24 hours, including ATP Challenger. It requires two named players with source IDs, a valid future scheduled time, singles, and automatically fetched tournament surface/format metadata. It executes each model separately, checks the feed again, and removes fixtures that changed, disappeared or started. Individual model failures remain visible; there is no substituted model, default probability, synthetic fixture or aggregate probability.

The source package contains sanitized code and JSON fitted parameters explicitly approved for public release. Original NPZ float64 arrays were converted to JSON with exact numerical equality, then verified against original outputs (tolerance 1e-10). `engine/manifest.json` records file hashes and the original registration digest. Private authorization text, personal conversation references, unrelated model histories, original archives and binaries are excluded. Diagnostic cases are labeled synthetic identifiers and never enter the current match list.

## Material limits

- Champion state: October 5, 2026. Challenger state: September 26, 2026. Experimental fit: October 10, 2026. No training occurs in this workflow.
- Public point-history snapshots are pinned to June 2026 to preserve the recovered model execution. Experimental completed-match updates extend through October 14. Current match inputs do **not** mean all model ratings are current.
- Coverage includes available ATP, WTA, ATP Challenger and WTA 125 fixtures. It remains partial: unknown players, unconfirmed times, unsupported surfaces/formats and conflicting source observations are withheld. A model named Challenger is separate from the ATP Challenger competition category.
- Tournament metadata updates automatically every scan. The collector discovers tournament links from the daily score pages and current calendar, reads each current edition's surface, dates, timezone and singles category, and joins ESPN events by exact name or an unambiguous city/country/tour/edition match. There is no dated manual tournament table to expire. Indoor hard/clay map to the recovered models' Hard/Clay categories.
- Only recognized standard best-of-three ATP/WTA/Challenger/125 categories with seven-point deciding tiebreaks are enabled. Grand Slams, Next Gen, team/exhibition events, carpet and unknown formats are withheld until a supported, tested scoring profile is available. New tournaments within supported categories are automatic; new rule systems are not guessed.
- Provider markup/schema changes or outages are visible in the source health record. Public HTML is decoded as literal JSON, never executed. Requests are size/time bounded, use four concurrent metadata fetches at most, and discover at most 60 tournament pages per pass. A discovery cap is reported. Third-party win probabilities and market fields are never model inputs.
- Cross-provider duplicate matches are merged only when scheduled time, surface and format agree; conflicts are withheld. Source status and fixture identity are rechecked after inference.
- Some players lack usable history or an exact identity match. Their model result is unavailable. No fuzzy-name prediction is accepted.
- These are research probabilities conditional on completion, not retirement/withdrawal probabilities, calibrated betting advice, or live in-play estimates. v3.4-A is experimental and uncalibrated. Agreement is not a calibrated ensemble.
- Scheduled starts are estimates. Updates are requested twice hourly, but GitHub can delay them. Results remain visible as dated pre-match research after 90 minutes and after scheduled start; these are explicitly labeled and are never presented as live match status. GitHub can disable schedules after 60 days of public-repository inactivity. A green deployment means the site deployed; the public record separately reports actual inference health.

## Explaining a forecast

Each successful result includes a small numeric `explanation` produced by the actual recovered model. The site shows it under **Why these forecasts?**:

- Champion: serve/return and Elo win probabilities, Elo blend weight and surface-adjusted ratings. Its final probability can be reconstructed as `(1-weight)*SR + weight*Elo`.
- Challenger: raw and adjusted service-point probabilities, fitted serve/return surface terms, calibration settings and minimum point exposure.
- Experimental: baseline probability, the change after dynamic-form adjustments, service probabilities, bounded logit shifts and effective point exposure.

A/B always refer to the displayed player order. Service-point probabilities differ from match probabilities; the tennis scoring calculation connects them. Coefficients are in log-odds and are not percentage-point attributions. These explain the model computation, not causal facts about a player's health or an actual match outcome. Only finite allowlisted numbers are published; source notes, raw traces and private data are excluded. The latest public scan contains normalized tournament/scoring inputs so a breakdown can be tied to its exact run and model hashes.

## Zero-cost operation

The workflow uses only standard `ubuntu-latest` runners in this public repository and GitHub Pages. The job refuses to run if the repository is private. No caches, releases, package hosting, large runners, external paid hosting, purchased domain, billing changes or card entry. Only the small Pages artifact is uploaded, with one-day retention. Raw historical inputs, runtime copies and logs are not uploaded. [GitHub standard public runner policy](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Runs are requested at minutes 17 and 47 of each hour and may also be started by a collaborator using **Actions → Tennis forecasts → Run workflow**. Refresh on the site reloads the latest published scan and reports whether it changed, failed, or returned an older scan. It does not launch a job or require browser credentials. The latest successful scan is retained in a separate public results file across deployments, and validated results are cached on the device when storage is available. A failed or empty scan shows the latest attempt status alongside the last successful results and their original timestamp. A fresh device still needs network access; a total hosting outage cannot serve a page that has never been loaded. Use All scan results to see every match from the saved scan; Future scheduled starts is an optional filter.

## Local verification

Requires Python 3.11 and Node 22+. From the repository root:

```sh
python -m pip install -r requirements.txt
node scripts/audit.mjs
node --test
python -m unittest discover -s test -p 'test_*.py'
python scripts/scan.py
node scripts/build.mjs
```

The scan writes `work/snapshot.json`; only the allowlisted `dist` files are deployed. Missing runtime/source access yields a blocked or unavailable snapshot. A fresh checkout never needs local private model files. Pull requests run offline gate tests and build a blocked preview, with no deployment permissions or live inference.

See [attribution](ATTRIBUTION.md) and [security boundaries](SECURITY.md).


## NFL engine and paper research

The NFL page at `nfl.html` shares this site without changing the tennis models. The complete recovered `NFL-v9.1-integrated-1` engine executes alongside a separately fitted first-TD Research Challenger 0.2.1. It covers game lines, team totals, all implemented passing/rushing/receiving ladders, anytime and multiple TDs, and game-first/team-first TDs.

**Live NFL probability publication remains gated.** The page shows execution health, cross-checked future fixture identities and validation evidence. The first-TD retrospective test improved aggregate log loss, but game-first Brier improvement is uncertain and its 2026-only subgroup worsened. No Champion promotion or profitable-betting claim is made. See `nfl/README.md` for the evidence and remaining acceptance criteria.

The existing hourly public workflow runs the full NFL engine in temporary storage. Small daily/manual paper artifacts retain immutable pregame forecasts and a carried-forward grade ledger for 14 days; no raw historical inputs or binary model archives are retained. Game and first-TD outcomes are graded only when reconciled final labels exist. Player-stat bet grading is withheld without participation and exact contract rules. Duplicate hourly forecasts do not increase the effective game count. No billing changes, paid runners, subscriptions or betting-account connections are used. Artifact restore failures are surfaced, not interpreted as zero prior results.
