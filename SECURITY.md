# Security and public data boundary

This repository and its Pages website are public. Keep account details, credentials, private source snapshots, personal paths, raw runtime reports and model binaries outside both. Never submit secrets in an issue or pull request.

Public data is restricted to model identities, diagnostic check counts, dates, evidence hashes and workflow metadata. The static build constructs this projection field by field. It does not copy raw receipts, runtime directories or arbitrary input documents into the site. No model deserialization or third-party model execution happens in Actions in this version.

The allowlist audit detects unexpected tracked files and selected credential patterns, but runs after a commit reaches GitHub. It cannot retract a leak or prevent an authorized maintainer from bypassing checks. Review locally before every push. If a credential is exposed, revoke it at its issuer immediately and remove the public content and affected history as appropriate.

Changes to execution, artifact delivery, workflow permissions or the publication schema require explicit review and meaningful tests. Do not weaken the blocked inference state just to make the dashboard look healthy. Avoid `pull_request_target`, secrets on untrusted code, unpinned actions and user-supplied shell fragments. Free operation depends on retaining public visibility and standard hosted runners.
