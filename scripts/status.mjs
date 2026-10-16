export const identities={champion:'SR-Elo 1.0',challenger:'SR-GLM 0.2',experimental:'v3.4-A'};
const roles=Object.keys(identities);
export function validate(s,now=Date.now()){
  if(s.schema_version!==2||!['available','unavailable','blocked'].includes(s.prediction_status)||!Array.isArray(s.matches)||s.matches.length>500)throw Error('Invalid snapshot');
  const generated=Date.parse(s.generated_at),expiry=Date.parse(s.expires_at);
  if(!Number.isFinite(generated)||generated>now+300000||!Number.isFinite(expiry)||expiry-generated!==90*60000)throw Error('Invalid freshness');
  if(!Array.isArray(s.models)||s.models.length!==3||new Set(s.models.map(m=>m.id)).size!==3)throw Error('Invalid registry');
  for(const m of s.models)if(identities[m.id]!==m.name||m.preflight.total!==4||!Number.isInteger(m.preflight.passed)||m.preflight.passed<0||m.preflight.passed>4||!['verified','unavailable'].includes(m.cloud_status)||m.cloud_status==='verified'&&m.preflight.passed!==4)throw Error('Unverified model');
  for(const e of s.matches){
    if(!Number.isFinite(Date.parse(e.starts_at))||!['ATP','WTA'].includes(e.tour)||!['main','wta125','challenger','main_qualifying','challenger_qualifying','wta125_qualifying'].includes(e.regime)||!['Hard','Clay','Grass'].includes(e.surface)||typeof e.name_a!=='string'||typeof e.name_b!=='string')throw Error('Invalid fixture');
    for(const role of roles){const r=e.results[role];if(!r||!['ok','unavailable'].includes(r.status))throw Error('Missing model result');if(r.status==='ok'){
      if(s.models.find(m=>m.id===role).cloud_status!=='verified'||!Number.isFinite(r.p_a)||r.p_a<0||r.p_a>1||!Number.isFinite(r.p_b)||Math.abs(r.p_a+r.p_b-1)>1e-9||!/^[a-f0-9]{64}$/.test(r.artifact_sha256)||!/^\d{4}-\d{2}-\d{2}$/.test(r.state_date)||Date.parse(r.state_date)>generated||r.research_only!==true)throw Error('Invalid probability evidence');
    }}
  }
  const any=s.matches.some(e=>roles.some(r=>e.results[r].status==='ok'));
  if((s.prediction_status==='available')!==any)throw Error('Inconsistent prediction status');
  return s;
}
export function blank(){const now=new Date();return {schema_version:2,generated_at:now.toISOString(),expires_at:new Date(+now+90*60000).toISOString(),prediction_status:'blocked',build:{},models:roles.map(id=>({id,name:identities[id],preflight:{passed:0,total:4},cloud_status:'unavailable',predictions:0})),matches:[],coverage:{coverage:'unavailable',note:'No execution snapshot supplied. Predictions are withheld.'},limitations:['No inference was performed in this build.']};}
