from __future__ import annotations

import pytest

from neon_pursuit.engine import GameMap, GameState, MatchConfig, generate_map, initial_state


@pytest.fixture
def config() -> MatchConfig:
    return MatchConfig(seed=2026)


@pytest.fixture
def game_map(config: MatchConfig) -> GameMap:
    return generate_map(config)


@pytest.fixture
def state(game_map: GameMap, config: MatchConfig) -> GameState:
    return initial_state(game_map, config)


def open_cell_with_free_line(game_map: GameMap, length: int = 4) -> int:
    """A floor cell with ``length`` free tiles to its east (for hand-built scenarios)."""
    for c in game_map.floor_cells:
        x, y = game_map.xy(c)
        if x + length >= game_map.width:
            continue
        if all(not game_map.is_wall(game_map.cell(x + i, y)) for i in range(length + 1)):
            return c
    raise AssertionError("no open corridor found")
