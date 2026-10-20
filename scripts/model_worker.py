"""Separate model execution; public output contains only a strict result projection."""
import hashlib,json,math,sys
import explanations
from matchup_intelligence_v2 import shadow
from historical_matchup_features import history_features,physical_traits
from quality import normalize
from datetime import date
from pathlib import Path
def main():
    role,root,input_path,output_path=sys.argv[1:5];root=Path(root)
    doc=json.loads(Path(input_path).read_text());cutoff=date.fromisoformat(doc['as_of']);cache={}
    if role in ('champion','challenger'):
        sys.path.insert(0,str(root/'native'))
        from tennis_ops.common import filehash,digest,key
        from tennis_ops.champion import ChampionModel
        from tennis_sr.core import ServeReturnModel
        reg=json.loads((root/'native/registration.json').read_text())
    elif role=='experimental':
        base=root/'experimental/TennisEngine_V3_4_A';sys.path.insert(0,str(base))
        from tennis_engine import automatic as auto
        from tennis_engine.models import load_artifact,sha256_data
        from tennis_engine.dynamic_form import build_dynamic_projection,prepare_form_history,VERSION
        from tennis_engine.scoring import simulate
        if VERSION!='V3.4-A_EXPERIMENTAL_DYNAMIC_RESIDUALS_1':raise ValueError('EXPERIMENTAL_IDENTITY_MISMATCH')
        def offline(tour,year,cache,refresh_hours=24,kind='main'):
            stem=f'{tour}_matches_{year}' if kind=='main' else f'{tour}_matches_qual_{"chall" if tour=="atp" else "itf"}_{year}'
            p=Path(cache)/'raw'/(stem+'.csv');meta=p.with_suffix('.source.json')
            if not auto._cached_file_is_valid(p,meta,kind,stem):raise ValueError('INVALID_PINNED_SOURCE')
            return p,json.loads(meta.read_text())
        auto._get_file=offline
    else:raise ValueError('UNKNOWN_MODEL')
    with Path(output_path).open('w',encoding='utf8') as out:
        for i,e in enumerate(doc['events']):
            row={'index':i,'model':role}
            try:
                tour=e['tour']
                if role=='champion':
                    if tour not in cache:cache[tour]=ChampionModel(reg,tour)
                    m=cache[tour]
                    if any(m.elo['counts'].get(e['player_'+side],0)<=0 for side in ('a','b')):raise ValueError('PLAYER_HISTORY_MISSING')
                    result=m.predict(e);p=result['p_a'];state=result['state_observed_at'];identity=result['model_id'];artifact=result['artifact_sha256'];explanation=explanations.champion(result['breakdown'])
                elif role=='challenger':
                    r=reg['models'][tour+'_SR_CORE_REGISTERED'];path=root/'native'/r['artifact']
                    if r['role']!='CHALLENGER_CORE' or r['tour']!=tour or filehash(path/'model.json')!=r['metadata_sha256'] or filehash(path/'weights.json')!=r['weights_sha256']:raise ValueError('CHALLENGER_ARTIFACT_MISMATCH')
                    if tour not in cache:cache[tour]=ServeReturnModel.load(path)
                    m=cache[tour]
                    if not m.fit_receipt.get('optimizer_success') or any(e['player_'+s] not in m.players for s in ('a','b')):raise ValueError('PLAYER_HISTORY_MISSING')
                    detail=m.explain(e);p=detail['distribution']['p_a'];state=r['as_of'];identity=r['model_id'];artifact=digest({'weights':r['weights_sha256'],'metadata':r['metadata_sha256']});explanation=explanations.challenger(detail)
                else:
                    if tour not in cache:
                        data=auto.load_archive(tour,list(range(2023,2027)),base/'data_cache',include_qual=True)
                        pkg=load_artifact(base/'data_cache/models'/f'{tour.lower()}_research_2023_2026.json')
                        cache[tour]=(pkg,data,prepare_form_history(data,cutoff))
                    pkg,data,prepared=cache[tour];ids=[]
                    for side in ('a','b'):
                        name=e['name_'+side]
                        # Only audited aliases, not fuzzy or forced player matching.
                        verified_aliases={'shi han':'Han Shi','catherine mcnally':'Caty McNally'}
                        candidate=verified_aliases.get(normalize(name),name)
                        pid,_=auto.resolve_name(candidate,data['names'])
                        normalized=auto.VERIFIED_NAME_ALIASES.get((auto.norm(candidate),tour),auto.norm(candidate))
                        if normalized not in {auto.norm(v) for v in data['names'][pid]}:raise ValueError('EXACT_PLAYER_IDENTITY_REQUIRED')
                        auto.player_diagnostics(pid,data,e['surface'].lower());ids.append(pid)
                    if ids[0]==ids[1] or e['deciding_tiebreak_target']!=7:raise ValueError('UNSUPPORTED_FIXTURE')
                    fixture={'match_id':e['source_match_id'],'tour':tour,'surface':e['surface'].lower(),'level':{'main':'MAIN','challenger':'CHALLENGER','wta125':'WTA125','main_qualifying':'QUALIFYING','challenger_qualifying':'QUALIFYING','wta125_qualifying':'QUALIFYING'}[e['regime']],'format':'bo'+str(e['best_of']),'player_a_id':ids[0],'player_b_id':ids[1],'tournament_id':e.get('tournament_key','UNKNOWN'),'start_at':cutoff.isoformat()+'T00:00:00Z','status':'RESEARCH_MATCHUP'}
                    r=build_dynamic_projection(fixture,pkg,data,cutoff,prepared=prepared);seed=int(hashlib.sha256(json.dumps(fixture,sort_keys=True).encode()).hexdigest()[:8],16)
                    probs=r['service_probabilities'];n=100000
                    mc=simulate(probs['sr_a'],probs['sr_b'],probs['elo_bridge_a'],probs['elo_bridge_b'],probs['elo_weight'],e['best_of'],n,seed)
                    if abs(mc['p_a']-r['p_a'])>6*max(mc['mc_se'],1/(2*n)**.5)+.002:raise ValueError('MC_EXACT_DISAGREEMENT')
                    p=r['p_a'];state=pkg['trained_through'];identity='EXPERIMENTAL_MATCHUP_INTELLIGENCE_V2_0_1';artifact=sha256_data(pkg);explanation=explanations.experimental(r)
                    try:
                        evidence,history_readiness=history_features(data,ids[0],ids[1],e)
                        v2=shadow(p,e['starts_at'],e['source_match_id'],evidence)
                        v2['history_readiness']=history_readiness
                    except Exception:
                        # Auxiliary data must NEVER block the frozen experimental forecast.
                        v2=shadow(p,e['starts_at'],e['source_match_id'],{})
                        v2['history_readiness']={'status':'HISTORICAL_ADAPTER_UNAVAILABLE'}
                    try:v2['physical_traits']=physical_traits(data,ids[0],ids[1],e)
                    except Exception:v2['physical_traits']={'status':'PHYSICAL_ADAPTER_UNAVAILABLE','players':{}}
                if not math.isfinite(p) or not 0<=p<=1:raise ValueError('INVALID_PROBABILITY')
                if date.fromisoformat(state[:10])>cutoff:raise ValueError('FUTURE_MODEL_STATE')
                row['result']={'p_a':float(p),'p_b':1-float(p),'model_id':identity,'state_date':state[:10],'artifact_sha256':artifact,'research_only':True,'explanation':explanation}
                if role=='experimental':row['result']['v2_readiness']=v2
            except Exception as exc:
                # Do not expose raw tracebacks or arbitrary source strings in public output.
                row['error']='MODEL_INPUT_OR_EXECUTION_FAILED' if not isinstance(exc,ValueError) else str(exc).split(':')[0][:80]
                if not all(c.isupper() or c.isdigit() or c=='_' for c in row['error']):row['error']='MODEL_INPUT_OR_EXECUTION_FAILED'
            out.write(json.dumps(row,allow_nan=False)+'\n');out.flush()
if __name__=='__main__':main()
