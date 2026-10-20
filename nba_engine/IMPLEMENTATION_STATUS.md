# NBA research integration status

## Added
- Coherent research possession simulator with shared shooter usage, made-shot assists, defensive rebounds, turnover events and deterministic runs.
- Player points, rebounds, assists, threes, turnovers and PRA Monte Carlo distributions.
- Platt calibration on historical prior-only labels and rolling out-of-sample shadow comparison.
- Conservation and leakage unit tests.

## Critical limitations
- Possession simulator is simplified: no on-court five-man substitutions, offensive boards/second chances, free throws, fouls, overtime or explicit end-game tactics. Ties remain unresolved and must NOT be called final win probabilities.
- Team scores do not yet feed the legacy game model; this is an isolated challenger module.
- Market comparison is evaluation-only and must not train the independent fundamental model.
- API token, NBA historical dataset, verified pre-tipoff injuries and closing lines are not connected.
- No calibrated fitted parameters or measured accuracy; CI execution pending.
- Do not merge, deploy, or promote until complete simulation and prospective evaluation pass.

## Research references
NBA stats glossary: https://www.nba.com/stats/help/glossary
NBA play-by-play v3: https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/playbyplayv3.md
