# Sources and data terms

Historical tennis records were compiled by **Jeff Sackmann / Tennis Abstract**:

- https://github.com/JeffSackmann/tennis_atp
- https://github.com/JeffSackmann/tennis_wta

Recovered execution uses the public [Aneeshers/tennis-sackmann-archive](https://github.com/Aneeshers/tennis-sackmann-archive), pinned to commit `83733587353df8a41f2fd4f516147d5aa83f5a8d`. Exact input URLs and SHA-256 digests are in `engine/sources.json`. The source data is offered under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0**: https://creativecommons.org/licenses/by-nc-sa/4.0/ . Retain attribution, do not use commercially, and preserve applicable share-alike terms for derived data/parameter material. This project adds no commercial license grant. Raw historical files are fetched only into temporary runner storage.

The small completed-match update file contains public tennis results and row-level public source URLs. Fitted model JSON is a recovered derived state, converted from numeric arrays without retraining. Public publication is authorized by the owner; attribution and source restrictions continue to apply.

Current fixtures come from ESPN's public ATP/WTA scoreboards and Tennis.com's public daily scores. Current tournament metadata comes from Tennis.com tournament pages discovered during each scan. No credentials, paid subscription or API key are used. These unofficial integrations have no availability guarantee and provide partial coverage. Only minimal factual labels, numeric model evidence and derived research results are republished; no page content, images, provider predictions, market prices or commentary. Standard singles scoring is documented by [ATP/WTA](https://www.wtatennis.com/news/3043764/tennis-explained-learn-the-game). Unsupported scoring categories are withheld, not assigned a guessed format.

No endorsement by these organizations is claimed. Access restrictions are respected; failed or blocked sources remain unavailable.


## NFL inputs

NFL research uses public nflverse play-by-play, rosters and injury data and the nfldata schedule. Per-input URLs, retrieval times and SHA-256 hashes are kept in the temporary source manifest. The public repository stores only numeric model parameters and compact validation evidence, not republished raw datasets. ESPN is used solely as an independent upcoming-fixture identity, kickoff and status check. Provider-derived gambling odds are not used as model inputs.
