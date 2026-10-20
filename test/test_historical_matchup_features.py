import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from historical_matchup_features import history_features,physical_traits
from matchup_intelligence_v2 import shadow

FIX={"source_match_id":"actual-fixture","starts_at":"2026-10-20T10:00:00Z","surface":"Hard"}
def construct(path,day="2026-08-12",retrieved="2026-10-19T10:00:00+00:00"):
    path.write_bytes(b"test checked archive")
    source={"url":"https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/atp/atp_matches_2026.csv",
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "local_file":str(path),"retrieved_at":retrieved}
    rows=[];points=[]
    for i in range(4):
        # a beats b in 3 out of 4 direct matches.
        winner="A" if i<3 else "B";loser="B" if i<3 else "A"
        mid="old-"+str(i)
        rows.append({"match_id":mid,"date":day,"temporal_precision":"TOURNAMENT_START_ONLY",
                     "winner_id":winner,"loser_id":loser,"surface":"hard"})
        for server,recv,won in [("A","B",65),("B","A",57)]:
            points.append({"match_id":mid,"server_id":server,"receiver_id":recv,
                           "serve_points_total":"100","serve_points_won":str(won)})
    return {"results":rows,"points":points,"sources":[source]}
class HistoricalIntegrationTests(unittest.TestCase):
 def test_verified_measured_surface_style_and_head_to_head(self):
    with tempfile.TemporaryDirectory() as d:
        data=construct(Path(d)/"archive.csv")
        evidence,summary=history_features(data,"A","B",FIX)
        self.assertEqual(set(evidence),{"surface","style","h2h"})
        self.assertEqual(evidence["h2h"]["raw"]["a"],0.75)
        self.assertEqual(summary["h2h_archive_wins"],{"a":3,"b":1})
        r=shadow(.58,FIX["starts_at"],FIX["source_match_id"],evidence)
        self.assertEqual(r["verified_features"],["h2h","style","surface"])
        self.assertIsNone(r["candidate_delta_pp"])
        self.assertEqual(r["baseline_p_a"],.58)
 def test_verified_hand_and_height_descriptors_are_not_probabilities(self):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"archive.csv";data=construct(p)
        csv="tourney_date,winner_id,loser_id,winner_hand,winner_ht,loser_hand,loser_ht\n"
        csv+=("20260812,A,B,R,185,L,180\n")*4
        p.write_text(csv)
        data["sources"][0]["sha256"]=hashlib.sha256(p.read_bytes()).hexdigest()
        physical=physical_traits(data,"ATP:A","ATP:B",FIX)
        self.assertEqual(physical["status"],"DESCRIPTIVE_NOT_PREDICTIVE")
        self.assertEqual(physical["players"]["a"]["height_cm"],185)
        self.assertEqual(physical["players"]["b"]["handedness"],"L")
 def test_unverified_supplemental_source_does_not_poison_pinned_history(self):
    with tempfile.TemporaryDirectory() as d:
        data=construct(Path(d)/"archive.csv")
        data["sources"].append({"url":"https://stats.tennismylife.org/data/2026.csv",
                                "sha256":"a"*64,"local_file":"missing-supplemental.csv"})
        data["results"].append({"match_id":"untrusted","date":"2026-09-01",
                                "temporal_precision":"TML_PUBLISHED_DATE_FIELD_NOT_INDEPENDENTLY_VERIFIED_MATCH_DAY",
                                "winner_id":"A","loser_id":"B","surface":"hard"})
        evidence,summary=history_features(data,"A","B",FIX)
        self.assertEqual(set(evidence),{"surface","style","h2h"})
        self.assertEqual(summary["h2h_completed_archive_matches"],4)
 def test_provenance_tamper_fails_closed(self):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"archive.csv";data=construct(p);p.write_text("modified")
        evidence,summary=history_features(data,"A","B",FIX)
        self.assertEqual(evidence,{})
        self.assertEqual(summary["status"],"ARCHIVE_PROVENANCE_UNAVAILABLE")
 def test_future_observation_fails_closed(self):
    with tempfile.TemporaryDirectory() as d:
        data=construct(Path(d)/"archive.csv",retrieved="2026-10-21T10:00:00+00:00")
        evidence,_=history_features(data,"A","B",FIX)
        self.assertFalse(evidence)
 def test_recent_proxy_event_is_not_point_in_time(self):
    with tempfile.TemporaryDirectory() as d:
        data=construct(Path(d)/"archive.csv",day="2026-10-15")
        evidence,summary=history_features(data,"A","B",FIX)
        self.assertFalse(evidence)
        self.assertEqual(summary["h2h_completed_archive_matches"],0)
 def test_identity_and_missing_archive(self):
    with self.assertRaises(ValueError):history_features({}, "A","A",FIX)
    evidence,_=history_features({"sources":[]}, "A","B",FIX)
    self.assertFalse(evidence)
if __name__=="__main__":unittest.main()
