"""Regression tests for fail-closed Champion player history and BO5 Elo semantics.

Run under the existing native tennis pytest environment. These tests do not
mutate any registered model files or authorize promotion.
"""
import math
from types import SimpleNamespace
import pytest

from tennis_ops.champion import ChampionModel


def model_with_elo():
    model = object.__new__(ChampionModel)
    model.elo = {
        "global": {"ATP:a": 1620.0, "ATP:b": 1500.0},
        "counts": {"ATP:a": 6, "ATP:b": 4},
    }
    model.surfaces = {}
    return model


def fixture(best_of=3):
    return {"player_a": "ATP:a", "player_b": "ATP:b",
            "surface": "Hard", "best_of": best_of}


def test_unknown_player_fails_closed_without_neutral_elo():
    model = model_with_elo()
    model.elo["global"].pop("ATP:b")
    with pytest.raises(ValueError, match="MISSING_ESTABLISHED_ELO_HISTORY"):
        model.elo_probability(fixture())


def test_no_prior_matches_fails_closed():
    model = model_with_elo()
    model.elo["counts"]["ATP:a"] = 0
    with pytest.raises(ValueError, match="MISSING_ESTABLISHED_ELO_HISTORY"):
        model.elo_probability(fixture())


def test_bo5_does_not_double_convert_match_level_elo():
    model = model_with_elo()
    p3, _, _ = model.elo_probability(fixture(3))
    p5, _, _ = model.elo_probability(fixture(5))
    assert math.isclose(p3, p5, rel_tol=0, abs_tol=1e-12)
    assert p3 > .5
