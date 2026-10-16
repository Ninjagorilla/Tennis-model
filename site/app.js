const $=id=>document.getElementById(id),roles=['champion','challenger','experimental'];
const names={champion:'SR-Elo 1.0',challenger:'SR-GLM 0.2',experimental:'v3.4-A'};
const dates={champion:'State · Oct 5, 2026',challenger:'State · Sep 26, 2026',experimental:'Fit · Oct 10, 2026'};
let snapshot=null,selected='all';
function el(tag,text,cls){const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e;}
function date(s){return new Date(s).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});}
function validate(d){
  if(d.schema_version!==2||!Array.isArray(d.matches)||!Array.isArray(d.models)||d.models.length!==3||new Set(d.models.map(m=>m.id)).size!==3||d.models.some(m=>names[m.id]!==m.name)||!Number.isFinite(Date.parse(d.generated_at))||Date.parse(d.generated_at)>Date.now()+300000||Date.parse(d.expires_at)-Date.parse(d.generated_at)!==5400000)throw Error('Invalid snapshot');
  for(const e of d.matches)for(const role of roles){const r=e.results[role];if(r.status==='ok'&&(!Number.isFinite(r.p_a)||r.p_a<0||r.p_a>1||!Number.isFinite(r.p_b)||Math.abs(r.p_a+r.p_b-1)>1e-9||d.models.find(m=>m.id===role).preflight.passed!==4))throw Error('Invalid result');}
}
function render(){
  const d=snapshot;if(!d)return;const expired=Date.now()>=Date.parse(d.expires_at),query=$('search').value.trim().toLowerCase();
  const upcoming=d.matches.filter(e=>Date.parse(e.starts_at)>Date.now());
  $('headline').textContent=expired?'Scan expired · forecasts withheld':d.prediction_status==='available'?'The latest forecasts are ready':'Forecasts unavailable in this scan';
  $('notice-detail').textContent=expired?'The next successful scan will restore current forecasts. Check the latest run below.':`Scanned ${date(d.generated_at)} · scheduled updates each hour · partial coverage`;
  $('match-count').textContent=expired?'—':upcoming.length;$('model-count').textContent=d.models.filter(m=>m.cloud_status==='verified').length+' / 3';$('updated').textContent=date(d.generated_at);
  $('coverage').textContent=d.coverage.note+(d.coverage.conflicting_matches?' '+d.coverage.conflicting_matches+' conflicting fixtures withheld.':'')+(d.coverage.metadata_tournaments?' '+d.coverage.metadata_tournaments+' tournament records refreshed.':'')+(d.coverage.unknown_tournaments?.length?' Additional tournaments withheld: '+d.coverage.unknown_tournaments.join(', ')+'.':'')+(d.coverage.sources?.some(s=>s.status!=='ok')?' Some fixture sources could not be reached.':'');
  const list=$('match-list');list.replaceChildren();
  const visible=upcoming.filter(e=>(selected==='all'||selected==='wta125'&&e.regime.startsWith('wta125')||selected==='ATP'&&e.tour==='ATP'&&!e.regime.startsWith('challenger')||selected==='challenger'&&e.regime.startsWith('challenger')||selected==='WTA'&&e.tour==='WTA'&&!e.regime.startsWith('wta125'))&&[e.name_a,e.name_b,e.tournament].some(v=>v.toLowerCase().includes(query))).sort((a,b)=>Date.parse(a.starts_at)-Date.parse(b.starts_at));
  if(expired||!visible.length)list.append(el('div',expired?'Waiting for a fresh scan. No expired probabilities are displayed.':'No upcoming matches match this view. Coverage may be incomplete.','empty'));
  else for(const e of visible){
    const card=el('article','','match');const info=el('div','','match-info');info.append(el('p',`${e.regime.startsWith('wta125')?'WTA 125':e.regime.startsWith('challenger')?'ATP Challenger':e.tour} · ${e.surface} · ${e.round}`,'eyebrow'),el('h3',e.tournament),el('p',date(e.starts_at)+' · estimated start','fine'));
    const players=el('div','','players');players.append(el('p','A  '+e.name_a),el('p','B  '+e.name_b));info.append(players);card.append(info);
    for(const role of roles){const r=e.results[role],col=el('div','','forecast');col.append(el('span',names[role],'model-name'));
      if(r.status==='ok'){col.append(el('strong',(100*r.p_a).toFixed(1)+'% / '+(100*r.p_b).toFixed(1)+'%'),el('small','A / B · '+r.state_date));}
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
    if(result.status!=='ok'||!x||!Object.keys(x).length)panel.append(el('p','No detailed result available.'));
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

async function load(){const b=$('refresh');b.disabled=true;try{const r=await fetch('data/status.json?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Fetch failed');const d=await r.json();validate(d);snapshot=d;render();}catch{snapshot=null;$('headline').textContent='Scan unavailable · forecasts withheld';$('notice-detail').textContent='The results could not be loaded or verified. Try refresh or check the latest run.';$('match-list').replaceChildren();$('model-cards').replaceChildren();$('match-count').textContent='—';$('model-count').textContent='—';}finally{b.disabled=false;}}
$('refresh').addEventListener('click',load);$('search').addEventListener('input',render);for(const b of document.querySelectorAll('[data-tour]'))b.addEventListener('click',()=>{selected=b.dataset.tour;for(const x of document.querySelectorAll('[data-tour]'))x.setAttribute('aria-pressed',String(x===b));render();});
setInterval(render,30000);setInterval(load,300000);load();
