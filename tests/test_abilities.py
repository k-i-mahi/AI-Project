"""Survivor abilities (EMP pulse, Blink Dash) and the territory-aware core spawns."""

from __future__ import annotations

import dataclasses

from neon_pursuit.engine import (
    Action,
    GameEvent,
    GameMap,
    GameState,
    MatchConfig,
    PulseEvent,
    Role,
    apply_action,
    can_pulse,
    is_legal,
    legal_actions,
    path_of,
    threat_distance,
)

from .conftest import open_cell_with_free_line


def _near(game_map: GameMap, state: GameState, gap: int = 2) -> GameState:
    """Survivor with the Hunter ``gap`` tiles east in an open corridor."""
    start = open_cell_with_free_line(game_map, length=4)
    hunter = start
    for _ in range(gap):
        hunter = game_map.step[hunter * 5 + 2]
    return dataclasses.replace(state, survivor=start, hunter=hunter)


def test_pulse_only_in_range(game_map: GameMap, config: MatchConfig, state: GameState) -> None:
    assert not is_legal(game_map, state, Action.PULSE, config)  # spawns are far apart
    near = _near(game_map, state)
    assert can_pulse(game_map, config, near)
    assert Action.PULSE in legal_actions(game_map, near, config)


def test_pulse_stuns_hunter_and_costs_energy(
    game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    near = _near(game_map, state)
    events: list[GameEvent] = []
    after = apply_action(game_map, config, near, Action.PULSE, events)
    assert any(isinstance(e, PulseEvent) for e in events)
    assert after.survivor == near.survivor
    assert after.energy == near.energy - config.pulse_energy
    assert after.pulse_cooldown == config.pulse_cooldown
    assert after.hunter_stun == config.pulse_stun
    # A stunned Hunter may only wait, for exactly `pulse_stun` turns.
    s = after
    for _ in range(config.pulse_stun):
        assert legal_actions(game_map, s, config) == [Action.WAIT]
        s = apply_action(game_map, config, s, Action.WAIT)  # hunter waits
        s = apply_action(game_map, config, s, Action.WAIT)  # survivor
    assert len(legal_actions(game_map, s, config)) > 1


def test_pulse_unavailable_on_cooldown_or_low_energy(
    game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    near = _near(game_map, state)
    assert not can_pulse(game_map, config, dataclasses.replace(near, pulse_cooldown=3))
    assert not can_pulse(game_map, config, dataclasses.replace(near, energy=config.pulse_energy))
    assert not can_pulse(game_map, config, dataclasses.replace(near, hunter_stun=1))


def test_stun_counts_as_distance(game_map: GameMap, state: GameState) -> None:
    near = _near(game_map, state, gap=3)
    assert threat_distance(game_map, dataclasses.replace(near, hunter_stun=2)) == (
        threat_distance(game_map, near) + 2
    )


def test_blink_dash_leaps_over_one_wall(
    game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    """Find a floor-wall-floor line and check the Survivor (only) can blink across it."""
    for c in game_map.floor_cells:
        x, y = game_map.xy(c)
        if x + 2 >= game_map.width - 1:
            continue
        wall, beyond = game_map.cell(x + 1, y), game_map.cell(x + 2, y)
        if game_map.is_wall(wall) and not game_map.is_wall(beyond):
            break
    else:  # pragma: no cover - every generated map has pillars
        raise AssertionError("no blinkable wall found")
    s = dataclasses.replace(state, survivor=c, hunter=game_map.survivor_spawn)
    if s.hunter in (c, beyond):
        s = dataclasses.replace(s, hunter=game_map.hunter_spawn)
    assert path_of(game_map, s, Role.SURVIVOR, Action.BURST_EAST) == [c, beyond]
    after = apply_action(game_map, config, s, Action.BURST_EAST)
    assert after.survivor == beyond
    assert after.dash_cooldown == config.dash_cooldown
    assert after.energy == s.energy - config.dash_energy
    # The Hunter's pounce cannot do the same.
    hunter_turn = dataclasses.replace(
        s, hunter=c, survivor=game_map.survivor_spawn, to_move=Role.HUNTER
    )
    if hunter_turn.survivor != beyond:
        assert path_of(game_map, hunter_turn, Role.HUNTER, Action.BURST_EAST) is None


def test_cores_respawn_in_survivor_territory(
    game_map: GameMap, config: MatchConfig, state: GameState
) -> None:
    start = open_cell_with_free_line(game_map)
    east = game_map.step[start * 5 + 2]
    cores = (east, *[-1] * (config.active_cores - 1))
    s = dataclasses.replace(state, survivor=start, cores=cores)
    after = apply_action(game_map, config, s, Action.EAST)
    for core in after.cores:
        assert core >= 0
        assert game_map.distance(after.survivor, core) < game_map.distance(after.hunter, core)


def test_pulse_action_metadata() -> None:
    assert not Action.PULSE.is_burst
    assert Action.PULSE.direction == 0
    assert Action.PULSE.label == "EMP Pulse"
