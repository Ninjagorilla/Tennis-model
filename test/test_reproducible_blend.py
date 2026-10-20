"""Synthetic fixture tests for preregistered disjoint-window evaluator."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"scripts"/"reproducible_blend.py"
spec=importlib.util.spec_from_file_location("reproducible_blend",SOURCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BlendEvaluationTests(unittest.TestCase):
    def write_rows(self,root,rows):
        p=Path(root)/"predictions.csv"
        with p.open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]))
            writer.writeheader();writer.writerows(rows)
        return p

    def rows(self):
        out=[]
        for tour in ("ATP","WTA"):
            for yr in (2023,2024,2025,2026):
                for i in range(3):
                    out.append({"fixture_id":f"{tour}-{yr}-{i}","tour":tour,
                       "played_at":f"{yr}-06-10T12:00:00Z",
                       "observed_at":f"{yr}-06-09T12:00:00Z",
                       "y":str(i%2),"p_elo":".45","p_sr":".55",
                       "vintage_sha256":"f"*64})
        return out

    def test_disjoint_per_tour_windows(self):
        with tempfile.TemporaryDirectory() as d:
            result=module.evaluate(self.write_rows(d,self.rows()))
        self.assertEqual(set(result["tours"]),{"ATP","WTA"})
        for tour in ("ATP","WTA"):
            self.assertEqual(result["tours"][tour]["test"]["blend"]["n"],3)
            self.assertFalse(result["tours"][tour]["promotion_authorized"])

    def test_same_day_observation_rejected(self):
        rows=self.rows()
        rows[0]["observed_at"]=rows[0]["played_at"]
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"PREDICTION_NOT_PRIOR_DAY"):
                module.evaluate(self.write_rows(d,rows))

    def test_duplicate_fixture_rejected(self):
        rows=self.rows();rows.append(rows[0].copy())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"DUPLICATE_FIXTURE"):
                module.evaluate(self.write_rows(d,rows))


if __name__=="__main__":
    unittest.main()
