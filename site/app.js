import {validate,hasResults,newest,lastUsable} from './forecast-state.mjs';
export function createDashboard({document,fetch,storage,now=Date.now}){
const $=id=>document.getElementById(id),roles=['champion','challenger','experimental'];
const names={champion:'SR-Elo 1.0',challenger:'SR-GLM 0.2',experimental:'v3.4-A'};
const dates={champion:'State · Oct 5, 2026',challenger:'State · Sep 26, 2026',experimental:'Fit · Oct 10, 2026'};
let snapshot=null,latest=null,saved=null,selected='all',view='all',busy=false,feedback='';
const cacheKey='courtside-tennis-scans-v1';
function el(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;}
function date(s){return new Date(s).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});}
function render(){
  const d=snapshot;if(!d)return;const expired=now()>=Date.parse(d.expires_at),query=$('search').value.trim().toLowerCase();
  const upcoming=d.matches.filter(e=>Date.parse(e.starts_at)>now());
  const fallback=latest && d.generated_at!==latest.generated_at;
  $('headline').textContent=fallback?'Latest scan has no picks · showing the last successful scan':expired?'Saved scan · update delayed':hasResults(d)?'The latest forecasts are ready':'This scan produced no picks';
  $('notice-detail').textContent=`Results from ${date(d.generated_at)}${expired?' · older than 90 minutes; saved research, not current forecasts':''}. ${fallback?`Latest attempt: ${date(latest.generated_at)} (${latest.prediction_status}). `:''}Refresh checks published results; it does not start the models.`;
  $('refresh-status').textContent=feedback;
  $('match-count').textContent=d.matches.length;$('model-count').textContent=d.models.filter(m=>m.cloud_status==='verified').length+' / 3';$('updated').textContent=date(d.generated_at);
  $('scan-summary').textContent=`${d.matches.length} matches in this scan · ${upcoming.length} have a future scheduled start. Match status is not live.`;
  $('coverage').textContent=d.coverage.note+(d.coverage.conflicting_matches?' '+d.coverage.conflicting_matches+' conflicting fixtures withheld.':'')+(d.coverage.metadata_tournaments?' '+d.coverage.metadata_tournaments+' tournament records refreshed.':'')+(d.coverage.unknown_tournaments?.length?' Additional tournaments withheld: '+d.coverage.unknown_tournaments.join(', ')+'.':'')+(d.coverage.sources?.some(s=>s.status!=='ok')?' Some fixture sources could not be reached.':'');
  const list=$('match-list');list.replaceChildren();
  const visible=(view==='upcoming'?upcoming:d.matches).filter(e=>(selected==='all'||selected==='wta125'&&e.regime.startsWith('wta125')||selected==='ATP'&&e.tour==='ATP'&&!e.regime.startsWith('challenger')||selected==='challenger'&&e.regime.startsWith('challenger')||selected==='WTA'&&e.tour==='WTA'&&!e.regime.startsWith('wta125'))&&[e.name_a,e.name_b,e.tournament].some(v=>v.toLowerCase().includes(query))).sort((a,b)=>Date.parse(a.starts_at)-Date.parse(b.starts_at));
  if(!visible.length)list.append(el('div',d.matches.length?'No matches match these filters. Choose All matches and All scan results, or clear the search.':'No verified fixtures were scored in this scan. Source coverage may be incomplete. Refresh will check for a newer scan.','empty'));
  else for(const e of visible){
    const card=el('article','','match');const info=el('div','','match-info');info.append(el('p',`${e.regime.startsWith('wta125')?'WTA 125':e.regime.startsWith('challenger')?'ATP Challenger':e.tour} · ${e.surface} · ${e.round}`,'eyebrow'),el('h3',e.tournament),el('p',date(e.starts_at)+' · estimated start','fine'));
    info.append(el('p',Date.parse(e.starts_at)<=now()?'Scheduled start passed · saved pre-match result':expired?'Saved pre-match result · scan is stale':'Pre-match result · scheduled start is an estimate','match-state'));
    const players=el('div','','players');players.append(el('p','A  '+e.name_a),el('p','B  '+e.name_b));info.append(players);card.append(info);
    for(const role of roles){const r=e.results[role],col=el('div','','forecast');col.append(el('span',names[role],'model-name'));
      if(r.status==='ok'){col.append(el('span',r.p_a===r.p_b?'No preference':`Pick: ${r.p_a>r.p_b?e.name_a:e.name_b}`,'pick'),el('strong',(100*r.p_a).toFixed(1)+'% / '+(100*r.p_b).toFixed(1)+'%'),el('small','A / B · '+r.state_date));}
      else{col.append(el('strong','Unavailable','missing'),el('small',(r.reason||'Execution unavailable').replaceAll('_',' ').toLowerCase()));}card.append(col);
    }card.append(explain(e));list.append(card);
  }
  $('model-cards').replaceChildren();for(const m of d.models){const c=el('article','','model-card');c.append(el('p',m.id==='experimental'?'EXPERIMENTAL':m.id.toUpperCase(),'eyebrow'),el('h3',m.name),el('p',m.cloud_status==='verified'?`${m.preflight.passed}/4 verification checks passed`:'Verification unavailable'),el('p',dates[m.id],'fine'),el('p',`${m.predictions} results in this scan`,'fine'));$('model-cards').append(c);}
  $('limitations').replaceChildren(...d.limitations.map(t=>el('li',t)));
}

function explain(e){
  const box=el('details','','breakdown');box.append(el('summary','Why these forecasts?'));
  const body=el('div','','breakdown-grid'),pct=n=>(100*n).toFixed(1)+'%',num=n=>Number(n).toFixed(3);
  for(const role of roles){const result=e.results[role],x=result.explanation,panel=el('div');panel.append(el('h4',names[role]));
    if(result.status!=='ok'||!x||!Object.keys(x).length||!(role==='champion'?['sr_p_a','elo_p_a','elo_weight','rating_a','rating_b']:role==='challenger'?['serve_a','serve_b','a_surface_serve','b_surface_serve','minimum_points']:['baseline_p_a','dynamic_change_pp','serve_a','serve_b']).every(k=>Number.isFinite(x[k])))panel.append(el('p','No detailed result available.'));
    else if(role==='champion'){
      panel.append(el('p',`Player A: serve/return component ${pct(x.sr_p_a)}; Elo component ${pct(x.elo_p_a)}. The Elo component carries ${pct(x.elo_weight)} of the final blend.`));
      panel.append(el('p',`Surface-adjusted Elo ratings: A ${Math.round(x.rating_a)}, B ${Math.round(x.rating_b)}. Final chance for A: ${pct(result.p_a)}.`));
    }else if(role==='challenger'){
      panel.append(el('p',`Estimated service-point win rates after calibration and form adjustment: A ${pct(x.serve_a)}, B ${pct(x.serve_b)}.`));
      panel.append(el('p',`Surface serve terms: A ${num(x.a_surface_serve)}, B ${num(x.b_surface_serve)} in log-odds. Minimum historical point exposure: ${Math.round(x.minimum_points)}.`));
    }else{
      panel.append(el('p',`Player A's baseline: ${pct(x.baseline_p_a)}. Recent-form adjustments changed it by ${x.dynamic_change_pp>=0?'+':''}${x.dynamic_change_pp.toFixed(2)} percentage points, giving ${pct(result.p_a)}.`));
      panel.append(el('p',`Adjusted service-point win rates: A ${pct(x.serve_a)}, B ${pct(x.serve_b)}. Experimental, uncalibrated model.`));
    }body.append(panel);
  }
  box.append(body,el('p','A / B follow the player order above. Point-winning rates differ from match-winning chances; the scoring model converts between them. These figures come from this execution, not a narrative guess.','fine'));
  return box;
}

function cache(){try{storage?.setItem(cacheKey,JSON.stringify({latest,saved}));}catch{/* Storage can be disabled or full. */}}
function restore(){
  try{const c=JSON.parse(storage?.getItem(cacheKey)||'null');if(c){
    try{latest=validate(c.latest,now());}catch{/* Try the independent successful scan. */}
    try{saved=validate(c.saved,now());}catch{/* Latest scan may still be usable. */}
    snapshot=lastUsable(latest,saved)||latest;feedback='Showing saved results while checking for updates.';render();
  }}catch{/* Ignore corrupt or incompatible cache. */}
}
async function readScan(path){
  const r=await fetch(`${path}?t=${now()}`,{cache:'no-store',signal:AbortSignal.timeout(15000)});
  if(!r.ok)throw Error('Could not download scan');
  const text=await r.text();if(text.length>1500000)throw Error('Scan too large');
  const d=JSON.parse(text);return d===null?null:validate(d,now());
}
async function load(){
  if(busy)return;
  busy=true;const b=$('refresh');b.disabled=true;b.textContent='Checking…';b.setAttribute('aria-busy','true');
  feedback='Checking for a newer published scan…';$('refresh-status').textContent=feedback;
  const before=latest?.generated_at;
  try{
    const [current,backup]=await Promise.allSettled([readScan('data/status.json'),readScan('data/last-success.json')]);
    if(backup.status==='fulfilled')saved=lastUsable(saved,backup.value);
    if(current.status!=='fulfilled'||!current.value)throw Error('Latest scan unavailable');
    const incoming=current.value;
    latest=newest(latest,incoming);saved=lastUsable(saved,latest,snapshot);
    snapshot=lastUsable(latest,saved)||latest;
    feedback=Date.parse(incoming.generated_at)<Date.parse(latest.generated_at)?'The server returned an older scan; keeping the newer saved results.':before===latest.generated_at?'Checked just now · no newer scan published. Your saved results are still shown.':'Updated just now · latest published scan loaded.';
    cache();render();
  }catch{
    snapshot=lastUsable(snapshot,saved)||snapshot||latest;
    feedback=snapshot?'Refresh failed · keeping saved results. Check your connection and try again.':'Results could not be loaded. Try Refresh or open the public scan record below.';
    if(snapshot){cache();render();}
    else{$('headline').textContent='Scan unavailable';$('notice-detail').textContent='No saved results are available on this device.';$('refresh-status').textContent=feedback;$('match-list').replaceChildren(el('div','No scan could be loaded. The latest run and public scan record below can help diagnose the issue.','empty'));}
  }finally{busy=false;b.disabled=false;b.textContent='Refresh';b.setAttribute('aria-busy','false');}
}
$('refresh').addEventListener('click',load);$('search').addEventListener('input',render);
for(const b of document.querySelectorAll('[data-tour]'))b.addEventListener('click',()=>{selected=b.dataset.tour;for(const x of document.querySelectorAll('[data-tour]'))x.setAttribute('aria-pressed',String(x===b));render();});
for(const b of document.querySelectorAll('[data-view]'))b.addEventListener('click',()=>{view=b.dataset.view;for(const x of document.querySelectorAll('[data-view]'))x.setAttribute('aria-pressed',String(x===b));render();});
restore();
return {load,render};
}
if(typeof document!=='undefined'){
  let storage;try{storage=window.localStorage;}catch{/* Private browsing may disable storage. */}
  const app=createDashboard({document,fetch:window.fetch.bind(window),storage});
  setInterval(app.render,30000);setInterval(app.load,300000);app.load();
}
