import test from 'node:test';import assert from 'node:assert/strict';
import {retainLastScan} from '../scripts/last-scan.mjs';
import {blank} from '../site/forecast-state.mjs';
// Shared fixture without importing dashboard tests.
function good(at){const s=blank();s.generated_at=at;s.expires_at=new Date(Date.parse(at)+5400000).toISOString();s.prediction_status='available';for(const m of s.models){m.preflight.passed=4;m.cloud_status='verified';}s.matches=[{tour:'ATP',regime:'main',surface:'Hard',tournament:'Test',round:'Final',name_a:'One Player',name_b:'Two Player',starts_at:at,results:Object.fromEntries(s.models.map(m=>[m.id,{status:'ok',p_a:.6,p_b:.4,artifact_sha256:'a'.repeat(64),state_date:'2026-10-05',research_only:true}]))}];return s;}
test('failed deployment scan carries forward newest validated successful scan',async()=>{
  const old=good('2026-10-16T20:00:00Z'),recent=good('2026-10-17T20:00:00Z');const result=await retainLastScan(blank(),{enabled:true,fetcher:async url=>({ok:true,text:async()=>JSON.stringify(url.includes('last-success')?old:recent)})});assert.equal(result.generated_at,recent.generated_at);
});
test('network and invalid backup failures never break a usable current scan',async()=>{
  const current=good('2026-10-17T20:00:00Z');assert.equal(await retainLastScan(current,{enabled:true,fetcher:async()=>{throw Error('offline');}}),current);assert.equal(await retainLastScan(blank(),{previous:[{prediction_status:'available'}]}),null);
});
test('local and PR builds make no outbound retention requests',async()=>{
  let calls=0;await retainLastScan(blank(),{fetcher:async()=>{calls++;}});assert.equal(calls,0);
});
test('failed current scan plus unreachable backup prevents erasing the deployed results',async()=>{
  await assert.rejects(retainLastScan(blank(),{enabled:true,fetcher:async()=>{throw Error('offline');}}),/keeping the existing deployed site/);
});

test('independent GitHub results recover when both Pages endpoints are down',async()=>{
  const preserved=good('2026-10-17T20:00:00Z');
  let calls=0;
  const recovered=await retainLastScan(blank(),{enabled:true,fetcher:async url=>{
    calls++;
    if(!url.includes('raw.githubusercontent.com'))throw Error('Pages offline');
    return {ok:true,text:async()=>JSON.stringify(preserved)};
  }});
  assert.equal(recovered.generated_at,preserved.generated_at);
  assert.ok(calls>=3);
});
test('unverified independent branch cannot replace a failed deployment',async()=>{
  await assert.rejects(retainLastScan(blank(),{enabled:true,fetcher:async url=>{
    if(!url.includes('raw.githubusercontent.com'))throw Error('Pages offline');
    return {ok:true,text:async()=>'{"prediction_status":"available"}'};
  }}),/keeping the existing deployed site/);
});
