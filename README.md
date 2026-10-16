# Courtside tennis forecasts

[Open the site](https://ninjagorilla.github.io/Tennis-model/) · [Run history](https://github.com/Ninjagorilla/Tennis-model/actions/workflows/dashboard.yml)

A personal, static tennis site backed by scheduled GitHub Actions. It runs the recovered Champion **SR-Elo 1.0**, Challenger **SR-GLM 0.2**, and experimental **v3.4-A** on supported upcoming singles. The browser only receives public results. No account, server subscription, card, API key or paid data service is required.

## What actually runs

Every trusted main-branch run verifies all published runtime file hashes, downloads checksum-pinned public historical inputs into temporary runner storage, and reproduces four saved diagnostic predictions per model. Each model must pass its own checks before its predictions can be published. These checks establish recovery/port consistency, not calibration or predictive accuracy.

The collector reads ESPN's ATP/WTA schedules for the next 24 hours. It requires two named players with source IDs, a valid future scheduled time, singles, and a reviewed tournament surface/format. It executes each model separately, checks the feed again, and removes fixtures that changed, disappeared or started. Individual model failures remain visible; there is no substituted model, default probability, synthetic fixture or aggregate probability.

The source package contains sanitized code and JSON fitted parameters explicitly approved for public release. Original NPZ float64 arrays were converted to JSON with exact numerical equality, then verified against original outputs (tolerance 1e-10). `engine/manifest.json` records file hashes and the original registration digest. Private authorization text, personal conversation references, unrelated model histories, original archives and binaries are excluded. Diagnostic cases are labeled synthetic identifiers and never enter the current match list.

## Material limits

- Champion state: October 5, 2026. Challenger state: September 26, 2026. Experimental fit: October 10, 2026. No training occurs in this workflow.
- Public point-history snapshots are pinned to June 2026 to preserve the recovered model execution. Experimental completed-match updates extend through October 14. Current match inputs do **not** mean all model ratings are current.
- Coverage is partial: available ATP, WTA and WTA 125 fixtures. ATP Challenger schedules are currently unavailable. A model named Challenger is separate from the ATP Challenger competition category.
- Reviewed tournament metadata is in `config/tournaments.json`, with official evidence links and validity dates. Unknown tournaments are withheld and reported. Add reviewed entries as the calendar changes; current entries cover events through October 25, 2026. Never infer the match format from ESPN's `format.regulation.periods` field.
- Some players lack usable history or an exact identity match. Their model result is unavailable. No fuzzy-name prediction is accepted.
- These are research probabilities conditional on completion, not retirement/withdrawal probabilities, calibrated betting advice, or live in-play estimates. v3.4-A is experimental and uncalibrated. Agreement is not a calibrated ensemble.
- Scheduled starts are estimates. Hourly refreshes can be delayed; the site withholds forecasts after 90 minutes and at scheduled start. GitHub can disable schedules after 60 days of public-repository inactivity. A green deployment means the site deployed; the public record separately reports actual inference health.

## Zero-cost operation

The workflow uses only standard `ubuntu-latest` runners in this public repository and GitHub Pages. The job refuses to run if the repository is private. No caches, releases, package hosting, large runners, external paid hosting, purchased domain, billing changes or card entry. Only the small Pages artifact is uploaded, with one-day retention. Raw historical inputs, runtime copies and logs are not uploaded. [GitHub standard public runner policy](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Runs are requested hourly at minute 17 and may also be started by a collaborator using **Actions → Tennis forecasts → Run workflow**. Refresh on the site reloads the latest published scan; it does not launch a job or require browser credentials.

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
