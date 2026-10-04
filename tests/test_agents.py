from __future__ import annotations

import dataclasses
import random

import pytest

from neon_pursuit.ai import (
    ALGORITHMS,
    AgentSettings,
    AlgorithmId,
    MctsParams,
    MinimaxParams,
    create_agent,
    evaluate,
)
from neon_pursuit.engine import (
    Action,
    GameMap,
    GameState,
    MatchConfig,
    Role,
    Status,
    apply_action,
    legal_actions,
)

from .conftest import open_cell_with_free_line

# Budgets only: wall-clock limits are set far out of reach so results never depend on how
# fast (or how loaded) the machine is. A 200 ms limit once made CI flaky under coverage.
FAST = AgentSettings(
    mcts=MctsParams(iterations=60, rollout_depth=8, time_limit_ms=120_000),
    minimax=MinimaxParams(max_depth=3, node_budget=2_000, time_limit_ms=120_000),
)


def _random_states(
    game_map: GameMap, config: MatchConfig, start: GameState, n: int
) -> list[GameState]:
    rng = random.Random(5)
    out: list[GameState] = []
    s = start
    while len(out) < n:
        if s.is_terminal:
            s = start
        out.append(s)
        s = apply_action(game_map, config, s, rng.choice(legal_actions(game_map, s, config)))
    return out


@pytest.mark.parametrize("algorithm", list(AlgorithmId))
def test_agents_return_legal_actions(
    algorithm: AlgorithmId, game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    agents = {
        role: create_agent(algorithm, role, game_map, config, seed=3, settings=FAST)
        for role in Role
    }
    for s in _random_states(game_map, config, state, 12):
        decision = agents[s.to_move].decide(s)
        assert decision.action in legal_actions(game_map, s, config)
        assert decision.elapsed_ms >= 0
        assert decision.insight.summary
        assert decision.insight.algorithm is algorithm


@pytest.mark.parametrize("algorithm", list(AlgorithmId))
def test_agents_are_deterministic(
    algorithm: AlgorithmId, game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    a = create_agent(algorithm, Role.SURVIVOR, game_map, config, seed=9, settings=FAST)
    b = create_agent(algorithm, Role.SURVIVOR, game_map, config, seed=9, settings=FAST)
    assert a.decide(state).action == b.decide(state).action


def test_agent_refuses_wrong_turn(game_map: GameMap, config: MatchConfig, state: GameState) -> None:
    agent = create_agent(AlgorithmId.GREEDY, Role.HUNTER, game_map, config)
    with pytest.raises(ValueError):
        agent.decide(state)  # Survivor to move


@pytest.mark.parametrize("algorithm", [AlgorithmId.MCTS, AlgorithmId.MINIMAX, AlgorithmId.GREEDY])
def test_search_hunters_take_immediate_capture(
    algorithm: AlgorithmId, game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = dataclasses.replace(state, hunter=start, survivor=east, to_move=Role.HUNTER)
    agent = create_agent(algorithm, Role.HUNTER, game_map, config, seed=1, settings=FAST)
    action = agent.decide(s).action
    after = apply_action(game_map, config, s, action)
    assert after.status is Status.HUNTER_WIN


@pytest.mark.parametrize("algorithm", [AlgorithmId.MCTS, AlgorithmId.MINIMAX, AlgorithmId.GREEDY])
def test_survivors_avoid_walking_into_the_hunter(
    algorithm: AlgorithmId, game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    start = open_cell_with_free_line(game_map, length=4)
    east2 = game_map.step[game_map.step[start * 5 + 2] * 5 + 2]
    s = dataclasses.replace(state, survivor=start, hunter=east2, pounce_cooldown=5)
    agent = create_agent(algorithm, Role.SURVIVOR, game_map, config, seed=1, settings=FAST)
    action = agent.decide(s).action
    assert action is not Action.EAST


def test_mcts_insight(game_map: GameMap, config: MatchConfig, state: GameState) -> None:
    agent = create_agent(AlgorithmId.MCTS, Role.SURVIVOR, game_map, config, seed=1, settings=FAST)
    insight = agent.decide(state).insight
    visits = [a.visits or 0 for a in insight.actions]
    assert sum(visits) > 0
    assert visits == sorted(visits, reverse=True)
    assert any(k == "Iterations" for k, _ in insight.stats)


def test_minimax_insight(game_map: GameMap, config: MatchConfig, state: GameState) -> None:
    agent = create_agent(
        AlgorithmId.MINIMAX, Role.SURVIVOR, game_map, config, seed=1, settings=FAST
    )
    insight = agent.decide(state).insight
    assert insight.actions
    assert all(0.0 <= a.score <= 1.0 for a in insight.actions)
    assert insight.plan


def test_evaluate_bounds_and_terminals(
    game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    v = evaluate(game_map, config, state)
    assert 0.0 <= v <= 1.0
    assert evaluate(game_map, config, dataclasses.replace(state, status=Status.HUNTER_WIN)) == 0.0
    assert evaluate(game_map, config, dataclasses.replace(state, status=Status.SURVIVOR_WIN)) == 1.0
    starving = dataclasses.replace(state, energy=1)
    assert evaluate(game_map, config, starving) < v


def test_registry_covers_every_algorithm() -> None:
    assert set(ALGORITHMS) == set(AlgorithmId)
    for info in ALGORITHMS.values():
        assert info.name and info.description and info.highlights
