from __future__ import annotations

import dataclasses

import pytest

from neon_pursuit.ai.fuzzy import (
    FuzzyAgent,
    FuzzySystem,
    LinguisticVariable,
    Trapezoid,
    hunter_system,
    survivor_system,
    triangle,
    when,
)
from neon_pursuit.engine import Action, GameMap, GameState, MatchConfig, Role, legal_actions

from .conftest import open_cell_with_free_line


def test_trapezoid_membership() -> None:
    mf = Trapezoid(0, 2, 4, 6)
    assert mf(-1) == 0.0
    assert mf(1) == pytest.approx(0.5)
    assert mf(3) == 1.0
    assert mf(5) == pytest.approx(0.5)
    assert mf(7) == 0.0
    tri = triangle(0, 5, 10)
    assert tri(5) == 1.0
    assert tri(2.5) == pytest.approx(0.5)


def test_shoulders() -> None:
    left = Trapezoid(0, 0, 1, 3)
    right = Trapezoid(5, 8, 10, 10)
    assert left(0) == 1.0
    assert right(10) == 1.0


@pytest.mark.parametrize("system", [survivor_system(), hunter_system()], ids=["survivor", "hunter"])
def test_inputs_form_fuzzy_partitions(system: FuzzySystem) -> None:
    """Memberships of every input should sum to ~1 across its universe (Ruspini partition)."""
    for var in system.inputs.values():
        steps = 60
        for i in range(steps + 1):
            x = var.low + (var.high - var.low) * i / steps
            total = sum(var.fuzzify(x).values())
            assert total == pytest.approx(1.0, abs=1e-6), (var.name, x, var.fuzzify(x))


def test_single_rule_defuzzifies_to_term_centre() -> None:
    inp = LinguisticVariable("x", 0, 1, {"hi": Trapezoid(0, 0, 1, 1)})
    out = LinguisticVariable("y", 0, 1, {"mid": triangle(0.25, 0.5, 0.75)})
    system = FuzzySystem([inp], out, [when(("x", "hi"), then="mid", rule_id="R1")])
    assert system.evaluate({"x": 0.3}).output == pytest.approx(0.5, abs=1e-3)


def test_overlapping_terms_interpolate() -> None:
    inp = LinguisticVariable(
        "x", 0, 10, {"lo": Trapezoid(0, 0, 0, 10), "hi": Trapezoid(0, 10, 10, 10)}
    )
    out = LinguisticVariable(
        "y", 0, 1, {"bad": Trapezoid(0, 0, 0.2, 0.5), "good": Trapezoid(0.5, 0.8, 1, 1)}
    )
    rules = [
        when(("x", "lo"), then="bad", rule_id="A"),
        when(("x", "hi"), then="good", rule_id="B"),
    ]
    system = FuzzySystem([inp], out, rules)
    outputs = [system.evaluate({"x": float(x)}).output for x in range(11)]
    assert outputs == sorted(outputs)
    assert outputs[0] < 0.3
    assert outputs[-1] > 0.7


def test_rule_strength_uses_min_for_and() -> None:
    a = LinguisticVariable("a", 0, 1, {"t": Trapezoid(0, 1, 1, 1)})
    b = LinguisticVariable("b", 0, 1, {"t": Trapezoid(0, 1, 1, 1)})
    out = LinguisticVariable("y", 0, 1, {"z": triangle(0, 0.5, 1)})
    system = FuzzySystem([a, b], out, [when(("a", "t"), ("b", "t"), then="z", rule_id="R")])
    result = system.evaluate({"a": 0.8, "b": 0.3})
    assert result.rule_strengths[0][1] == pytest.approx(0.3)


def test_no_rule_fires_returns_midpoint() -> None:
    inp = LinguisticVariable("x", 0, 1, {"hi": Trapezoid(0.9, 1, 1, 1)})
    out = LinguisticVariable("y", 0, 1, {"z": triangle(0, 0.1, 0.2)})
    system = FuzzySystem([inp], out, [when(("x", "hi"), then="z", rule_id="R")])
    assert system.evaluate({"x": 0.0}).output == pytest.approx(0.5)


def test_validation_rejects_unknown_terms() -> None:
    inp = LinguisticVariable("x", 0, 1, {"hi": Trapezoid(0, 1, 1, 1)})
    out = LinguisticVariable("y", 0, 1, {"z": triangle(0, 0.5, 1)})
    with pytest.raises(ValueError):
        FuzzySystem([inp], out, [when(("x", "nope"), then="z", rule_id="R")])
    with pytest.raises(ValueError):
        FuzzySystem([inp], out, [when(("x", "hi"), then="nope", rule_id="R")])
    with pytest.raises(ValueError):
        FuzzySystem([inp], out, [when(("q", "hi"), then="z", rule_id="R")])


def test_survivor_never_steps_into_capture(
    game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    """With the Hunter two tiles east, moving east must score as 'avoid'."""
    start = open_cell_with_free_line(game_map)
    east2 = game_map.step[game_map.step[start * 5 + 2] * 5 + 2]
    s = dataclasses.replace(state, survivor=start, hunter=east2, pounce_cooldown=5)
    agent = FuzzyAgent(Role.SURVIVOR, game_map, config, seed=1)
    feats = agent.features(s, Action.EAST)
    assert feats["danger"] <= 1
    assert agent.system.evaluate(feats).output < 0.25
    decision = agent.decide(s)
    assert decision.action is not Action.EAST
    assert decision.insight.fuzzy_inputs and decision.insight.fuzzy_rules
    assert decision.action in legal_actions(game_map, s, config)


def test_hunter_takes_the_capture(game_map: GameMap, config: MatchConfig, state: GameState) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = dataclasses.replace(state, hunter=start, survivor=east, to_move=Role.HUNTER)
    decision = FuzzyAgent(Role.HUNTER, game_map, config, seed=1).decide(s)
    assert decision.action in (Action.EAST, Action.BURST_EAST)
