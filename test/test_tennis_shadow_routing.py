"""Verify that WTA blends cannot be served through the public Champion slot."""
import math
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from tennis_shadow_routing import apply_wta_shadow_guard


def game(tour="WTA", champion=None, challenger=None):
    return {"tour": tour, "results": {
        "champion": champion if champion is not None else
            {"status": "ok", "p_a": 0.8, "p_b": 0.2, "model_id": "unvalidated-blend"},
        "challenger": challenger if challenger is not None else
            {"status": "ok", "p_a": 0.62, "p_b": 0.38, "model_id": "SR-CHALLENGER"},
        "experimental": {"status": "unavailable"}}}


class WtaShadowRoutingTests(unittest.TestCase):
    def test_wta_never_serves_blend_as_champion(self):
        g = apply_wta_shadow_guard(game())
        self.assertEqual(g["results"]["champion"]["status"], "unavailable")
        self.assertTrue(g["wta_blend_shadow"]["not_for_action"])
        self.assertFalse(g["wta_blend_shadow"]["historical_metrics_citable"])
        self.assertAlmostEqual(g["wta_blend_shadow"]["p_a"], 0.8)

    def test_research_challenger_used_when_valid(self):
        g = apply_wta_shadow_guard(game())
        self.assertEqual(g["wta_selected"]["role"], "SR_CHALLENGER_RESEARCH")
        self.assertTrue(g["wta_selected"]["research_only"])
        self.assertAlmostEqual(g["wta_selected"]["p_a"], 0.62)

    def test_no_challenger_does_not_fall_back_to_blend(self):
        g = apply_wta_shadow_guard(game(challenger={"status": "unavailable"}))
        self.assertEqual(g["wta_selected"]["role"], "NO_FORECAST")
        self.assertIsNone(g["wta_selected"]["p_a"])
        self.assertEqual(g["results"]["champion"]["status"], "unavailable")

    def test_nan_challenger_abstains(self):
        g = apply_wta_shadow_guard(game(challenger={"status": "ok",
            "p_a": float("nan"), "p_b": 0.4, "model_id": "bad"}))
        self.assertEqual(g["wta_selected"]["role"], "NO_FORECAST")

    def test_atp_unchanged(self):
        source = game("ATP")
        out = apply_wta_shadow_guard(source)
        self.assertIs(out, source)
        self.assertEqual(out["results"]["champion"]["status"], "ok")
        self.assertNotIn("wta_selected", out)

    def test_shadow_is_a_copy_not_registry_mutation(self):
        source = game()
        original = source["results"]["champion"]
        result = apply_wta_shadow_guard(source)
        self.assertIsNot(result["wta_blend_shadow"], original)
        self.assertNotIn("not_for_action", original)


if __name__ == "__main__":
    unittest.main()
