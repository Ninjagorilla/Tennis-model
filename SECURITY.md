# Publication boundaries

Public: reviewed inference code, text fitted parameters, public player names, public completed tennis results with source URLs, diagnostic examples, integrity digests, and strictly projected match predictions.

Never commit credentials, personal/private data, chat transcripts or links, original recovery archives, model binaries, raw historical datasets, runtime folders, local logs, or virtual environments. `.gitignore`, the exact file allowlist and manifest hashes enforce the expected package; a human content review is still necessary for changes. New artifacts require explicit review before changing the allowlist or manifest.

The runtime uses JSON numeric arrays, not pickle or executable binary serialization. Historical data downloads are allowlisted to one immutable public Git commit, size bounded, and SHA-256 checked. Runtime paths must stay within their staging directory. No model archive is extracted in CI. The workflow never refits or silently replaces a model. The manifest is a version-controlled integrity record, not an independent cryptographic signature.

Actions are pinned by commit. Build has read-only repository permission and checkout does not persist credentials. Deployment is a separate main-only job with Pages/OIDC permissions; fork pull requests cannot deploy. No secrets are referenced. The free-runner guard excludes private repositories. The browser uses textContent for external labels, a restrictive CSP, no trackers and no authentication token.

Only `dist/index.html`, `style.css`, `app.js`, `.nojekyll`, and `data/status.json` are deployable. Diagnostics and input documents stay in temporary runner storage. Worker output is projected to numeric results, model identities, state dates and digests; raw exceptions and traceback text are never sent to the website. Tests cover unsupported/expired fixtures, malformed probabilities, model verification and workflow permissions.

To report a suspected secret exposure, contact the repository owner privately; do not paste the suspected secret in a public issue.
