import pandas as pd
from .data import write
def aggregate(data):
    records=[];qb_records=[]
    cols=['game_id','posteam','defteam','epa','pass','rush','qb_kneel','qb_spike','qb_dropback','sack','success','yards_gained','yardline_100','passer_player_id']
    for source in sorted(data.glob('pbp_*.parquet')):
        year=int(source.stem.split('_')[-1])
        p=pd.read_parquet(data/f'pbp_{year}.parquet',columns=cols)
        p=p[p.epa.notna() & ((p['pass']==1)|(p.rush==1)) & (p.qb_kneel!=1)&(p.qb_spike!=1)].copy()
        p['explosive']=((p['pass']==1)&(p.yards_gained>=15))|((p.rush==1)&(p.yards_gained>=10))
        for (gid,t),g in p.groupby(['game_id','posteam']):
            pa=g[g.qb_dropback.eq(1)];ru=g[g.rush.eq(1)];rz=g[g.yardline_100.le(20)]
            records.append({'game_id':gid,'team':t,'epa':float(g.epa.mean()),'pass_epa':float(pa.epa.mean()) if len(pa) else None,'rush_epa':float(ru.epa.mean()) if len(ru) else None,'success':float(g.success.mean()),'explosive':float(g.explosive.mean()),'sack_rate':float(pa.sack.mean()) if len(pa) else None,'redzone_success':float(rz.success.mean()) if len(rz) else None,'plays':len(g)})
        for (gid,q),g in p[p.qb_dropback.eq(1)&p.passer_player_id.notna()].groupby(['game_id','passer_player_id']):
            qb_records.append({'game_id':gid,'qb_id':q,'n':len(g),'sum_epa':float(g.epa.sum())})
    write(data/'team_game_aggregates.json',records);write(data/'qb_game_aggregates.json',qb_records)
    return records,qb_records

