# Challenger fixture recovery

Primary: Tennis.com scheduled singles with verified metadata.

Backup 1: ESPN independently sourced fixtures, requiring matching tour, identities, event, surface and scheduled start. Do not infer Challenger classification from an ATP label.

Backup 2: Manually collected fixtures from official ATP Challenger event pages. Record original URL, retrieval timestamp, both full names and player IDs, surface, tournament, round, and scheduled time with timezone. Reject incomplete or conflicting rows. Never enter probabilities manually.

Backup 3: Retain the most recent verified artifact only for historical inspection. Expired or restored snapshots must never be republished or graded as fresh.

A green CI run is not proof of Challenger completeness. Run the Challenger coverage gate against the new snapshot; on zero Challenger fixtures or unavailable provider scope, mark Challenger coverage degraded and alert. A nonzero count is presence, not proof of complete coverage. Champion artifacts must remain unchanged. Promotion, merge and deployment require separate approval.
