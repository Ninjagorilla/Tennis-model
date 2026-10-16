# Sources and data terms

Historical tennis records were compiled by **Jeff Sackmann / Tennis Abstract**:

- https://github.com/JeffSackmann/tennis_atp
- https://github.com/JeffSackmann/tennis_wta

Recovered execution uses the public [Aneeshers/tennis-sackmann-archive](https://github.com/Aneeshers/tennis-sackmann-archive), pinned to commit `83733587353df8a41f2fd4f516147d5aa83f5a8d`. Exact input URLs and SHA-256 digests are in `engine/sources.json`. The source data is offered under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0**: https://creativecommons.org/licenses/by-nc-sa/4.0/ . Retain attribution, do not use commercially, and preserve applicable share-alike terms for derived data/parameter material. This project adds no commercial license grant. Raw historical files are fetched only into temporary runner storage.

The small completed-match update file contains public tennis results and row-level public source URLs. Fitted model JSON is a recovered derived state, converted from numeric arrays without retraining. Public publication is authorized by the owner; attribution and source restrictions continue to apply.

Current fixture observations come from ESPN's public ATP/WTA scoreboard endpoints, without credentials or a paid subscription. This unofficial integration has no availability guarantee and provides partial coverage. It republishes minimal factual match labels and derived research results, not page content, images or commentary. Tournament surface evidence comes from ATP/WTA links in `config/tournaments.json`; standard singles scoring is documented by [ATP/WTA](https://www.wtatennis.com/news/3043764/tennis-explained-learn-the-game).

No endorsement by these organizations is claimed. Access restrictions are respected; failed or blocked sources remain unavailable.
