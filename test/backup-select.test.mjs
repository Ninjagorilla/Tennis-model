import test from 'node:test';
import assert from 'node:assert/strict';
import {blank} from '../site/forecast-state.mjs';
import {selectBackup,ENDPOINTS} from '../scripts/backup_select.mjs';
const now=Date.parse('2026-10-19T02:00:00Z');
function sample(generated='2026-10-19T01:30:00Z'){
  const s=blank();s.generated_at=generated;s.expires_at=new Date(Date.parse(generated)+5400000).toISOString();
  s.prediction_status='available';s.models=s.models.map(m=>({...m,preflight:{passed:4,total:4},cloud_status:'verified',predictions:1}));
  s.matches=[{tour:'ATP',regime:'main',surface:'Hard',name_a:'Player One',name_b:'Player Two',
    starts_at:'2026-10-19T05:00:00Z',tournament:'Tournament',round:'Round 1',
    results:Object.fromEntries(['champion','challenger','experimental'].map(role=>[role,{
      status:'ok',p_a:.6,p_b:.4,artifact_sha256:'a'.repeat(64),state_date:'2026-10-05',research_only:true
    }]))}];
  return s;
}
const responses=(map)=>async(url)=>({ok:map[url]!==undefined,text:async()=>map[url]});
test('chooses fresher valid backup and never alters run timestamp',async()=>{
 const map={[ENDPOINTS[0].url]:JSON.stringify(sample('2026-10-19T01:10:00Z')),
            [ENDPOINTS[1].url]:JSON.stringify(sample('2026-10-19T01:40:00Z'))};
 const r=await selectBackup({now,fetcher:responses(map)});
 assert.equal(r.status,'verified_backup');assert.equal(r.name,'pages-last-success');
 assert.equal(r.generated_at,'2026-10-19T01:40:00Z');
});
test('rejects expired backup even with available prediction status',async()=>{
 const map={[ENDPOINTS[0].url]:JSON.stringify(sample('2026-10-18T20:00:00Z'))};
 const r=await selectBackup({now,fetcher:responses(map)});
 assert.equal(r.status,'no_fresh_backup');assert.ok(r.sources.some(x=>x.status==='expired'));
});
test('rejects corrupted and blocked snapshots',async()=>{
 const broken=sample();broken.prediction_status='blocked';
 const map={[ENDPOINTS[0].url]:JSON.stringify(broken),[ENDPOINTS[1].url]:'NOT_JSON'};
 const r=await selectBackup({now,fetcher:responses(map)});
 assert.equal(r.status,'no_fresh_backup');
});
test('refuses unapproved backup domains',async()=>{
 let calls=0;
 const r=await selectBackup({now,sources:[{name:'independent-results',url:'https://evil.example/test'}],fetcher:async()=>{calls++;throw Error();}});
 assert.equal(r.status,'no_fresh_backup');assert.equal(calls,0);
});
