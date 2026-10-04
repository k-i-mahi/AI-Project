from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from neon_pursuit.engine import (
    Action,
    CaptureEvent,
    CoreCollectedEvent,
    GameEvent,
    GameMap,
    GameState,
    IllegalActionError,
    MatchConfig,
    Role,
    Status,
    WinReason,
    apply_action,
    is_legal,
    legal_actions,
    path_of,
)

from .conftest import open_cell_with_free_line


def test_initial_state(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    assert state.to_move is Role.SURVIVOR
    assert state.status is Status.PLAYING
    assert state.energy == config.start_energy
    active = [c for c in state.cores if c >= 0]
    assert len(active) == config.active_cores
    assert len(set(active)) == len(active)
    assert state.hunter == game_map.hunter_spawn


def test_wait_is_always_legal(state: GameState, game_map: GameMap) -> None:
    assert Action.WAIT in legal_actions(game_map, state)


def test_turns_alternate_and_round_advances(
    state: GameState, game_map: GameMap, config: MatchConfig
) -> None:
    s1 = apply_action(game_map, config, state, Action.WAIT)
    assert s1.to_move is Role.HUNTER and s1.round == 0
    s2 = apply_action(game_map, config, s1, Action.WAIT)
    assert s2.to_move is Role.SURVIVOR and s2.round == 1
    assert s2.energy == state.energy - 1


def test_illegal_actions_raise(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    illegal = [a for a in Action if not is_legal(game_map, state, a)]
    assert illegal, "spawn should be next to the border wall"
    with pytest.raises(IllegalActionError):
        apply_action(game_map, config, state, illegal[0])


def _scenario(game_map: GameMap, state: GameState, **changes: Any) -> GameState:
    return dataclasses.replace(state, **changes)


def test_survivor_cannot_step_onto_hunter(state: GameState, game_map: GameMap) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = _scenario(game_map, state, survivor=start, hunter=east)
    assert not is_legal(game_map, s, Action.EAST)
    assert not is_legal(game_map, s, Action.BURST_EAST)


def test_hunter_capture(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = _scenario(game_map, state, hunter=start, survivor=east, to_move=Role.HUNTER)
    events: list[GameEvent] = []
    end = apply_action(game_map, config, s, Action.EAST, events)
    assert end.status is Status.HUNTER_WIN
    assert end.win_reason is WinReason.CAPTURED
    assert any(isinstance(e, CaptureEvent) for e in events)


def test_pounce_captures_on_first_tile(
    state: GameState, game_map: GameMap, config: MatchConfig
) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = _scenario(game_map, state, hunter=start, survivor=east, to_move=Role.HUNTER)
    assert path_of(game_map, s, Role.HUNTER, Action.BURST_EAST) == [start, east]
    end = apply_action(game_map, config, s, Action.BURST_EAST)
    assert end.status is Status.HUNTER_WIN


def test_pounce_respects_cooldown(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    start = open_cell_with_free_line(game_map)
    s = _scenario(
        game_map, state, hunter=start, to_move=Role.HUNTER, survivor=game_map.survivor_spawn
    )
    after = apply_action(game_map, config, s, Action.BURST_EAST)
    assert after.pounce_cooldown == config.pounce_cooldown - 1
    blocked = _scenario(game_map, after, to_move=Role.HUNTER)
    assert not is_legal(game_map, blocked, Action.BURST_EAST)


def test_dash_costs_energy_and_cooldown(
    state: GameState, game_map: GameMap, config: MatchConfig
) -> None:
    start = open_cell_with_free_line(game_map)
    s = _scenario(game_map, state, survivor=start, cores=tuple([-1] * config.active_cores))
    after = apply_action(game_map, config, s, Action.BURST_EAST)
    assert after.survivor == game_map.step[game_map.step[start * 5 + 2] * 5 + 2]
    assert after.energy == state.energy - config.dash_energy
    assert after.dash_cooldown == config.dash_cooldown
    low = _scenario(game_map, s, energy=3)
    assert not is_legal(game_map, low, Action.BURST_EAST)


def test_core_collection_refills_energy_and_respawns(
    state: GameState, game_map: GameMap, config: MatchConfig
) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    cores = (east, *[-1] * (config.active_cores - 1))
    s = _scenario(game_map, state, survivor=start, cores=cores, energy=10)
    events: list[GameEvent] = []
    after = apply_action(game_map, config, s, Action.EAST, events)
    assert after.cores_collected == 1
    assert after.energy == 10 + config.core_energy
    assert any(isinstance(e, CoreCollectedEvent) for e in events)
    assert east not in after.cores
    assert all(c >= 0 for c in after.cores)  # every slot refilled
    # Respawn is deterministic.
    again = apply_action(game_map, config, s, Action.EAST)
    assert again.cores == after.cores


def test_dash_collects_cores_on_both_tiles(
    state: GameState, game_map: GameMap, config: MatchConfig
) -> None:
    start = open_cell_with_free_line(game_map)
    mid = game_map.step[start * 5 + 2]
    end = game_map.step[mid * 5 + 2]
    cores = (mid, end, *[-1] * (config.active_cores - 2))
    s = _scenario(game_map, state, survivor=start, cores=cores)
    after = apply_action(game_map, config, s, Action.BURST_EAST)
    assert after.cores_collected == 2


def test_energy_is_capped(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = _scenario(
        game_map, state, survivor=start, cores=(east, -1, -1, -1), energy=config.max_energy
    )
    assert apply_action(game_map, config, s, Action.EAST).energy == config.max_energy


def test_win_by_cores(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    s = _scenario(
        game_map,
        state,
        survivor=start,
        cores=(east, -1, -1, -1),
        cores_collected=config.cores_to_win - 1,
    )
    after = apply_action(game_map, config, s, Action.EAST)
    assert after.status is Status.SURVIVOR_WIN
    assert after.win_reason is WinReason.CORES_COLLECTED
    assert after.is_terminal
    assert legal_actions(game_map, after) == []
    with pytest.raises(IllegalActionError):
        apply_action(game_map, config, after, Action.WAIT)


def test_starvation(state: GameState, game_map: GameMap, config: MatchConfig) -> None:
    s = _scenario(game_map, state, to_move=Role.HUNTER, energy=1)
    after = apply_action(game_map, config, s, Action.WAIT)
    assert after.status is Status.HUNTER_WIN
    assert after.win_reason is WinReason.STARVED


def test_survive_until_round_limit(state: GameState, game_map: GameMap) -> None:
    config = MatchConfig(seed=2026, max_rounds=3)
    s = state
    for _ in range(3):
        s = apply_action(game_map, config, s, Action.WAIT)
        s = apply_action(game_map, config, s, Action.WAIT)
    assert s.status is Status.SURVIVOR_WIN
    assert s.win_reason is WinReason.SURVIVED


def test_state_key_is_hashable_and_distinct(
    state: GameState, game_map: GameMap, config: MatchConfig
) -> None:
    other = apply_action(game_map, config, state, Action.WAIT)
    assert state.key() != other.key()
    assert {state.key(): 1}[state.key()] == 1


def test_action_properties() -> None:
    assert Action.BURST_WEST.is_burst and not Action.WEST.is_burst
    assert Action.BURST_SOUTH.direction == Action.SOUTH.direction == 3
    assert Action.WAIT.direction == 0
    assert Action.NORTH.label == "North" and Action.BURST_EAST.label == "Burst East"
    assert Role.HUNTER.opponent is Role.SURVIVOR
