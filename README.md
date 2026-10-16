# Tennis command center

[Dashboard](https://Ninjagorilla.github.io/Tennis-model/) · [Run / inspect workflow](https://github.com/Ninjagorilla/Tennis-model/actions/workflows/dashboard.yml)

Personal tennis research dashboard for Champion **SR-Elo 1.0**, Challenger **SR-GLM 0.2**, and Experimental **v3.4-A**. A successful website build is not a successful prediction run.

## What works today

- A static dashboard, refreshed daily at 13:17 UTC and on pushes to `main`.
- Manual refresh: open the workflow link, choose **Run workflow**, use `main`. This rebuilds status; it does not run the local models.
- Live workflow status from GitHub's public read API; API failures are shown as unknown.
- A dated, sanitized local recovery receipt: all three actual models were recovered and executed across ATP, WTA, ATP Challenger and WTA 125 diagnostic fixtures. Counts, saved-state dates and SHA-256 evidence are displayed. These checks establish execution, not model quality.
- An explicit blocked state for cloud inference. No probabilities, fake fixtures, claimed zero-match slates, fallback model labels, consensus probabilities or betting picks are generated.

## What is still unavailable

The verified model artifacts remain local. There is **no approved cloud runtime delivery source**, no Linux portability verification, and no current fixture collector. The Actions workflow deliberately runs the dashboard checks only. Rebuilding it does not refresh model state, rerun local preflight or scan current matches.

`config/recovery.json` is a historical diagnostic receipt, not a signed third-party attestation or a cloud execution claim. Its hashes allow comparison against retained local evidence; the private report and archives are not published. Saved-state dates are not necessarily last-match data dates. Experimental is uncalibrated, and agreement between models is not independent evidence or a calibrated ensemble.

## To enable real cloud inference later

This requires a reviewed implementation change, not flipping a flag. The build rejects `cloud_enabled: true` until an actual execution path is implemented and verified.

1. Establish a zero-cost, authorized delivery location for a sanitized runtime package **outside this public repository**. Review data rights and remove private files first. Never upload the recovered archive wholesale: it contains machine paths and private recovery context. Do not commit model binaries or use Git LFS, release attachments, caches or public workflow artifacts to hide them elsewhere in this repository.
2. Pin approved artifact SHA-256 hashes, registration identities, source revision and dependency versions. Download into ephemeral runner storage, verify before loading, run least-privileged without secrets, then discard. Never execute arbitrary workflow-dispatch URLs, commands, unreviewed pickle files or pull-request artifacts. Verify Linux startup and exact registered identities.
3. Collect fresh public singles fixtures across ATP, WTA, ATP Challenger and WTA 125, including qualifying. Preserve evidence timestamps and hashes; reconcile identity, match status and format. An unreviewed category is unknown, not empty.
4. Run all available models independently, retain valid partial results, and give specific missing-model reasons. Record actual artifact hashes, state dates, fixture input hash and execution timestamps. Reconcile upcoming status before publishing. Keep diagnostic canaries separate from live results.
5. Add a strict public projection schema and tests for stale/future data, invalid probabilities, wrong identities, partial failures and private-field removal before enabling output. Keep market evidence out of model inputs. No credential may enter a browser, log or artifact.

## Free operation

Only standard `ubuntu-latest` runners on this public repository and GitHub Pages are used. The workflow skips a private repository. No paid APIs, larger runners, custom domain, external hosting, billing setup, card, npm dependency installation or Actions cache is required. Only the tiny website is uploaded, with one-day artifact retention and five-minute job timeouts.

GitHub documents [free standard runner usage for public repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions) and [GitHub Pages availability](https://docs.github.com/en/pages/getting-started-with-github-pages/about-github-pages). Free service limits still apply. Schedules can be delayed and may be disabled after 60 days of repository inactivity. The site flags snapshots older than 48 hours; it never calls a stale snapshot current.

## Development and deployment

Node.js 22 or newer, no installed dependencies:

```sh
npm test
npm run audit
npm run build
```

The audit checks tracked Git files against a reviewed allowlist and size limits; stage intended source files before running it. Manually review all changes for private content before pushing. `.gitignore` and scanners are safeguards, not a guarantee against a collaborator committing secrets.

For a new installation, select **Settings → Pages → Source → GitHub Actions**. Push to `main` or manually dispatch **Tennis dashboard**. Pull requests run validation only and cannot deploy. Check the deploy job and the public URL to establish deployment success. See [GitHub's Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Only five files from `dist/` are publishable; model archives, logs and runtime files are excluded. Third-party actions are pinned to full commit hashes, checkout credentials are not persisted, and only the separate deployment job gets Pages/OIDC permissions. The static site uses no cookies, analytics, forms or browser credentials. Its only external request is the public GitHub workflow status endpoint.
