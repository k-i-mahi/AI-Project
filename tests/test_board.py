from __future__ import annotations

import pytest

from neon_pursuit.engine import UNREACHABLE, GameMap, MatchConfig, generate_map
from neon_pursuit.engine.board import bfs


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 2026, 99_999])
def test_maps_are_connected_and_mirrored(seed: int) -> None:
    m = generate_map(MatchConfig(seed=seed))
    # Every floor cell is reachable from every other.
    for c in m.floor_cells:
        assert m.distance(m.hunter_spawn, c) != UNREACHABLE
    # Left-right mirror symmetry keeps the arena fair.
    for y in range(m.height):
        for x in range(m.width):
            assert m.walls[m.cell(x, y)] == m.walls[m.cell(m.width - 1 - x, y)]


def test_generation_is_deterministic() -> None:
    a = generate_map(MatchConfig(seed=123))
    b = generate_map(MatchConfig(seed=123, wall_density=0.24))
    c = generate_map(MatchConfig(seed=124))
    assert a.walls == b.walls
    assert a.core_sequence == b.core_sequence
    assert a.walls != c.walls


def test_border_is_solid(game_map: GameMap) -> None:
    w, h = game_map.width, game_map.height
    for x in range(w):
        assert game_map.is_wall(game_map.cell(x, 0))
        assert game_map.is_wall(game_map.cell(x, h - 1))
    for y in range(h):
        assert game_map.is_wall(game_map.cell(0, y))
        assert game_map.is_wall(game_map.cell(w - 1, y))


@pytest.mark.parametrize("seed", range(25))
def test_spawns_are_random_but_fair(seed: int) -> None:
    m = generate_map(MatchConfig(seed=seed))
    assert m.hunter_spawn != m.survivor_spawn
    for spawn in (m.hunter_spawn, m.survivor_spawn):
        assert not m.is_wall(spawn)
        assert len(m.neighbours(spawn)) >= 2  # never starts in a dead end
    min_sep = max(8, (m.width + m.height) // 3)
    assert m.distance(m.hunter_spawn, m.survivor_spawn) >= min_sep


def test_spawns_vary_with_seed_and_repeat_for_same_seed() -> None:
    spawns = {
        (
            generate_map(MatchConfig(seed=s)).hunter_spawn,
            generate_map(MatchConfig(seed=s)).survivor_spawn,
        )
        for s in range(10)
    }
    assert len(spawns) >= 8
    a = generate_map(MatchConfig(seed=77))
    generate_map.cache_clear()
    b = generate_map(MatchConfig(seed=77))
    assert (a.hunter_spawn, a.survivor_spawn) == (b.hunter_spawn, b.survivor_spawn)


def test_distance_table_matches_bfs(game_map: GameMap) -> None:
    src = game_map.floor_cells[len(game_map.floor_cells) // 2]
    ref = bfs(game_map.walls, game_map.width, game_map.height, src)
    for c in game_map.floor_cells:
        assert game_map.distance(src, c) == ref[c]
        assert game_map.distance(src, c) == game_map.distance(c, src)


def test_step_table(game_map: GameMap) -> None:
    for c in game_map.floor_cells:
        assert game_map.step[c * 5] == c
        for n in game_map.neighbours(c):
            assert game_map.distance(c, n) == 1


def test_core_sequence_avoids_spawns(game_map: GameMap) -> None:
    assert game_map.core_sequence
    for c in game_map.core_sequence:
        assert not game_map.is_wall(c)
        assert game_map.distance(game_map.hunter_spawn, c) >= 3


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        MatchConfig(width=5)
    with pytest.raises(ValueError):
        MatchConfig(cores_to_win=0)
    with pytest.raises(ValueError):
        MatchConfig(start_energy=99, max_energy=10)
