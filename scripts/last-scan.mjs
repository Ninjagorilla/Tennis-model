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
  let retained=lastUsable(...valid);
  // Third, independently published GitHub branch is used only if Pages and local
  // candidates fail. Preserve original generation/expiry, never mint new picks.
  if(enabled&&!retained){
    try{
      const url='https://raw.githubusercontent.com/Ninjagorilla/Tennis-model/refs/heads/scan-results/public-results/latest.json';
      const response=await fetcher(url,{cache:'no-store',signal:AbortSignal.timeout(15000)});
      if(!response.ok)throw Error('Independent results unavailable');
      const raw=await response.text();
      if(raw.length>1500000)throw Error('Independent result exceeds size limit');
      const backup=validate(JSON.parse(raw));
      retained=lastUsable(backup);
      if(!retained)throw Error('No verified independent results');
    }catch{recoveryFailed=true;}
  }
  // Leave the existing deployment intact rather than erase unknown prior picks.
  if(enabled&&!retained&&recoveryFailed)throw Error('Cannot safely recover previous results; keeping the existing deployed site.');
  return retained;
}
