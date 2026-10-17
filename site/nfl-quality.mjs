/** Research reporting only. Never auto-approve a model or imply prices are verified. */
export function auditProspective(p) {
 const count = Number.isInteger(p?.unique_games_graded) ? p.unique_games_graded : 0;
 const groups = p?.by_parameters && typeof p.by_parameters === 'object' ? Object.entries(p.by_parameters) : [];
 const rows=[];
 for(const [fingerprint,metrics] of groups){
   if(!/^[a-f0-9]{64}\|[a-f0-9]{64}$/.test(fingerprint)) continue;
   for(const market of ['game','team']){
     const loss=metrics?.[market+'_log_loss'];
     const brier=metrics?.[market+'_brier'];
     if(!loss||!brier) continue;
     const n=Math.min(loss.paired_games??0,brier.paired_games??0);
     const ll=loss.challenger_minus_baseline;
     const bs=brier.challenger_minus_baseline;
     const cis=[loss.paired_game_bootstrap_95pct,brier.paired_game_bootstrap_95pct];
     if(!Number.isInteger(n)||n<1||!Number.isFinite(ll)||!Number.isFinite(bs)) continue;
     const significant = n>=200 && cis.every(c=>Array.isArray(c)&&c.length===2&&c.every(Number.isFinite)&&c[1]<0);
     rows.push({fingerprint:fingerprint.slice(0,10)+'…', market, n, logLossDelta:ll, brierDelta:bs, significant,
       status:significant?'Candidate for manual subgroup review':n<200?'Insufficient prospective sample':'No clear paired improvement'});
   }
 }
 return {gradedGames:count,rows, approved:false,
   decision:'Promotion locked. Requires at least 200 independent graded games per parameter version, paired score improvement, subgroup review, and explicit human authorization.'};
}
export function inputQuality({rosterVerified=false,injuriesAsOfKickoff=false,participationVerified=false,marketRulesVerified=false,oddsTimestamped=false}={}){
 const checks={rosterVerified,injuriesAsOfKickoff,participationVerified,marketRulesVerified,oddsTimestamped};
 const complete=Object.values(checks).filter(Boolean).length;
 return {verified:complete,total:5,label:complete===5?'All listed checks verified':complete>=3?'Partially verified':'Insufficient verification',checks};
}
