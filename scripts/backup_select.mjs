import {validate} from '../site/forecast-state.mjs';

export const ENDPOINTS=Object.freeze([
  {name:'independent-results',url:'https://raw.githubusercontent.com/Ninjagorilla/Tennis-model/refs/heads/scan-results/public-results/latest.json'},
  {name:'pages-last-success',url:'https://ninjagorilla.github.io/Tennis-model/data/last-success.json'},
  {name:'pages-current',url:'https://ninjagorilla.github.io/Tennis-model/data/status.json'}
]);
export async function selectBackup({fetcher=fetch,now=Date.now(),sources=ENDPOINTS}={}){
  // Never allow caller-supplied arbitrary URL endpoints in production.
  const approved=new Map(ENDPOINTS.map(e=>[e.name,e.url]));
  const reports=[];
  const valid=[];
  for(const {name,url} of sources){
    if(approved.get(name)!==url){reports.push({name,status:'unapproved'});continue;}
    try {
      const response=await fetcher(url,{cache:'no-store',signal:AbortSignal.timeout(12000)});
      if(!response.ok)throw Error('HTTP_UNAVAILABLE');
      const body=await response.text();
      if(body.length>1500000)throw Error('OVERSIZED_SNAPSHOT');
      const doc=validate(JSON.parse(body),now);
      if(doc.prediction_status!=='available')throw Error('NO_PREDICTIONS');
      if(Date.parse(doc.expires_at)<=now){reports.push({name,status:'expired',generated_at:doc.generated_at});continue;}
      reports.push({name,status:'valid'});
      valid.push({name,generated_at:doc.generated_at,expires_at:doc.expires_at,matches:doc.matches.length});
    }catch{reports.push({name,status:'unavailable_or_invalid'});}
  }
  valid.sort((a,b)=>Date.parse(b.generated_at)-Date.parse(a.generated_at));
  return valid.length?{status:'verified_backup',...valid[0],sources:reports}
    :{status:'no_fresh_backup',sources:reports};
}
if(process.argv[1]&&import.meta.url===new URL('file://'+process.argv[1]).href){
  console.log(JSON.stringify(await selectBackup()));
}
