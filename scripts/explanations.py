"""Allowlisted numeric evidence from the model's actual explanation methods."""
import math
COMMON=('serve_a','serve_b','minimum_points')
FIELDS={
 'champion':COMMON+('sr_p_a','elo_p_a','elo_weight','rating_a','rating_b','without_current_form_p_a'),
 'challenger':COMMON+('raw_serve_a','raw_serve_b','calibration_scale','form_beta','a_global_serve','a_surface_serve','a_global_return','a_surface_return','b_global_serve','b_surface_serve','b_global_return','b_surface_return'),
 'experimental':('baseline_p_a','dynamic_change_pp','serve_a','serve_b','elo_weight','a_serve_logit_shift','a_return_logit_shift','b_serve_logit_shift','b_return_logit_shift','a_effective_serve_points','a_effective_return_points','b_effective_serve_points','b_effective_return_points')
}
def sanitize(role,value):
    if not isinstance(value,dict):return {}
    return {k:float(value[k]) for k in FIELDS.get(role,()) if type(value.get(k)) in (int,float) and math.isfinite(value[k])}
def native_sr(base):
    return {'serve_a':base['point_probability_calibrated_a'],'serve_b':base['point_probability_calibrated_b'],'minimum_points':base['minimum_historical_points']}
def champion(out):
    sr=out['serve_return_component'];elo=out['elo_component']
    return sanitize('champion',{**native_sr(sr),'sr_p_a':sr['distribution']['p_a'],'elo_p_a':elo['p_a'],'elo_weight':elo['weight'],'rating_a':elo['rating_a'],'rating_b':elo['rating_b'],'without_current_form_p_a':out['ablations']['without_current_state']})
def challenger(out):
    d={**native_sr(out),'raw_serve_a':out['point_probability_raw_a'],'raw_serve_b':out['point_probability_raw_b'],'calibration_scale':out['calibration_scale'],'form_beta':out['form_beta']}
    for side in ('a','b'):
        for term in ('global_serve','surface_serve','global_return','surface_return'):d[side+'_'+term]=out[side+'_components'][term]
    return sanitize('challenger',d)
def experimental(out):
    d={'baseline_p_a':out['reference_p_a'],'dynamic_change_pp':100*(out['p_a']-out['reference_p_a']),'serve_a':out['service_probabilities']['sr_a'],'serve_b':out['service_probabilities']['sr_b'],'elo_weight':out['service_probabilities']['elo_weight']}
    for side in ('a','b'):
        for term in ('serve','return'):
            d[side+'_'+term+'_logit_shift']=out['player_'+side][term+'_logit_shift']
            d[side+'_effective_'+term+'_points']=out['player_'+side]['effective_exposure'][term]
    return sanitize('experimental',d)
