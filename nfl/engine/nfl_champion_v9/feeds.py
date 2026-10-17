"""Current fixture and roster adapters with explicit freshness and source evidence."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import json, urllib.request
import pandas as pd
from .data import now, write, sha, validate_schedule


def kickoff(row):
    return datetime.fromisoformat(str(row.gameday)+'T'+str(row.gametime)).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()


def status_receipt(event_id):
    url='https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
    with urllib.request.urlopen(url,timeout=30) as response:schedule=pd.read_csv(response)
    validate_schedule(schedule);r=schedule[schedule.game_id.eq(event_id)]
    if len(r)!=1:raise ValueError('Fixture absent or ambiguous in current source')
    r=r.iloc[0];kick=kickoff(r);at=now()
    status='final' if pd.notna(r.home_score) else ('scheduled' if at<kick else 'started_or_unverified')
    return {'event_id':event_id,'status':status,'kickoff_utc':kick,'status_checked_at_utc':at,'source_refs':[url],'status_limit':'Schedule feed; no independently corroborated play-status source'}


def slate(snapshot,as_of=None):
    snapshot=Path(snapshot);at=as_of or now();schedule=validate_schedule(pd.read_csv(snapshot/'games.csv'))
    rows=[]
    for _,r in schedule.iterrows():
        if pd.notna(r.home_score):continue
        kick=kickoff(r)
        if kick<=at:continue
        if (datetime.fromisoformat(kick)-datetime.fromisoformat(at)).total_seconds()>7*86400:continue
        rows.append({'event_id':r.game_id,'season':int(r.season),'week':int(r.week),'home':r.home_team,'away':r.away_team,'kickoff_utc':kick,'as_of_utc':at,'home_qb_id':str(r.home_qb_id) if pd.notna(r.home_qb_id) else None,'away_qb_id':str(r.away_qb_id) if pd.notna(r.away_qb_id) else None,'rest_diff':float(r.home_rest-r.away_rest),'neutral_site':r.location=='Neutral','source_refs':['nflverse schedule snapshot'],'context':{'qb_source':'Schedule entry is provisional, not confirmed starter','roof':str(r.roof)}})
    return sorted(rows,key=lambda r:r['kickoff_utc'])


def roster_inputs(snapshot,game):
    path=Path(snapshot)/'rosters.parquet'
    if not path.exists():return game,['Roster feed unavailable']
    roster=pd.read_parquet(path)
    needed={'team','gsis_id','full_name','position','status'}
    if needed-set(roster):raise ValueError('Roster schema mismatch '+str(needed-set(roster)))
    rosters={};warnings=[]
    manifest_path=Path(snapshot)/'availability_manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        for item in manifest:
            if item['name'] in ['rosters','injuries']:
                if item['status']!='SUCCESS':warnings.append(item['name']+': feed unavailable')
                elif (datetime.fromisoformat(game['as_of_utc'])-datetime.fromisoformat(item['retrieved_at'])).total_seconds()>172800:warnings.append(item['name']+': source older than 48 hours')
    injuries_path=Path(snapshot)/'injuries.parquet';injuries=pd.read_parquet(injuries_path) if injuries_path.exists() else None
    for team in [game['home'],game['away']]:
        r=roster[roster.team.eq(team)&roster.gsis_id.notna()&roster.position.isin(['QB','RB','FB','WR','TE'])].copy()
        if r.gsis_id.duplicated().any():raise ValueError('Ambiguous roster IDs')
        by_id={}
        if injuries is not None and {'gsis_id','week','report_status','team'}.issubset(injuries):
            sub=injuries[injuries.team.eq(team)&injuries.week.eq(game['week'])]
            if 'date_modified' in sub:sub=sub.sort_values('date_modified')
            by_id=sub.drop_duplicates('gsis_id',keep='last').set_index('gsis_id').report_status.to_dict()
        rows=[]
        for _,p in r.iterrows():
            status=str(by_id.get(p.gsis_id,'' )).lower()
            designation='out' if status=='out' or str(p.status).upper() in ['RES','CUT','RET','DEV','INA'] else ('questionable' if status in ['questionable','doubtful'] else 'unknown')
            rows.append({'player_id':p.gsis_id,'name':p.full_name,'status':designation})
        rosters[team]=rows
        warnings.append(team+': roster membership is not game-day active confirmation; questionable players need explicit scenarios')
    return game|{'rosters':rosters,'roster_checked_at_utc':now()},warnings
