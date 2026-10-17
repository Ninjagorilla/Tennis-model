export function validateNFL(s,now=Date.now()){
 if(s.schema_version!==1||!['verified','offline_diagnostic','blocked','not_run'].includes(s.execution_status))throw Error('Invalid NFL status');
 const start=Date.parse(s.generated_at),end=Date.parse(s.expires_at);
 if(!Number.isFinite(start)||start>now+300000||end-start!==5400000)throw Error('Invalid NFL clock');
 if(s.publication_approved!==false||s.prediction_status!=='gated'||!Array.isArray(s.games)||s.games.length!==0)throw Error('NFL publication gate bypass');
 if(s.engine_version!=='NFL-v9.1-integrated-1'||s.first_td_version!=='NFL-First-TD-Research-0.2.1')throw Error('NFL model identity mismatch');
 if(!Number.isInteger(s.paper_games)||s.paper_games<0||s.paper_games>32||!Array.isArray(s.fixtures)||s.fixtures.length>32)throw Error('Invalid NFL coverage');
 const ids=new Set();for(const g of s.fixtures){if(!/^\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}$/.test(g.event_id)||ids.has(g.event_id)||!Number.isFinite(Date.parse(g.starts_at))||!Object.keys(g).every(k=>['event_id','home','away','starts_at'].includes(k)))throw Error('Invalid NFL fixture');ids.add(g.event_id);}
 if(s.validation?.promotion_approved!==false||s.validation?.prospective_games_graded!==0)throw Error('NFL release evidence requires review');
 return s;
}
