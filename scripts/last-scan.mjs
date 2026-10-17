import {validate,lastUsable} from '../site/forecast-state.mjs';

// Read only this site's public, validated results. Never carry raw model inputs.
export async function retainLastScan(current,{fetcher=fetch,enabled=false,previous=[]}={}){
  const candidates=[current,...previous];
  let recoveryFailed=false;
  if(enabled){
    const recovered=await Promise.allSettled(['status.json','last-success.json'].map(async name=>{
      const response=await fetcher(`https://ninjagorilla.github.io/Tennis-model/data/${name}?t=${Date.now()}`,{cache:'no-store',signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw Error('Previous scan unavailable');
      const raw=await response.text();if(raw.length>1500000)throw Error('Previous scan too large');
      return JSON.parse(raw);
    }));
    candidates.push(...recovered.filter(r=>r.status==='fulfilled').map(r=>r.value));
    recoveryFailed=recovered.some(r=>r.status==='rejected');
  }
  const valid=[];
  for(const c of candidates){try{valid.push(validate(c));}catch{if(c!==null)recoveryFailed=true;}}
  const retained=lastUsable(...valid);
  // Leave the existing deployment intact rather than erase unknown prior picks.
  if(enabled&&!retained&&recoveryFailed)throw Error('Cannot safely recover previous results; keeping the existing deployed site.');
  return retained;
}
