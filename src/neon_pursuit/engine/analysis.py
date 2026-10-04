"""Board-analysis features shared by heuristics, fuzzy controllers and overlays."""

from __future__ import annotations

import math

from .board import UNREACHABLE, GameMap
from .types import GameState


def nearest_core(game_map: GameMap, state: GameState, cell: int) -> tuple[int, float]:
    """Return ``(core_cell, distance)`` of the closest active core (``(-1, inf)`` if none)."""
    best, best_d = -1, math.inf
    base = cell * game_map.width * game_map.height
    dist = game_map.dist
    for core in state.cores:
        if core >= 0:
            d = dist[base + core]
            if d < best_d:
                best, best_d = core, d
    return best, best_d


#: Extra distance charged for a core the Hunter would reach first.
CONTESTED_CORE_PENALTY = 6


def safe_core_distance(
    game_map: GameMap,
    cores: tuple[int, ...] | list[int],
    survivor: int,
    hunter: int,
    penalty: float = CONTESTED_CORE_PENALTY,
) -> float:
    """Distance from ``survivor`` to the nearest core it reaches *before* the Hunter.

    Cores the Hunter would reach first (or tie) are still considered, but are
    charged ``penalty`` extra tiles (default :data:`CONTESTED_CORE_PENALTY`) so an
    evader does not fixate on a guarded core. Returns ``inf`` when no core is active.
    """
    size = game_map.width * game_map.height
    dist = game_map.dist
    sb, hb = survivor * size, hunter * size
    best = math.inf
    for core in cores:
        if core < 0:
            continue
        ds = dist[sb + core]
        cost = ds if ds < dist[hb + core] else ds + penalty
        best = min(best, cost)
    return best


def survivor_territory(game_map: GameMap, hunter: int, survivor: int) -> int:
    """Voronoi territory: floor cells the Survivor reaches strictly before the Hunter.

    Ties go to the Hunter, since contact means capture. A shrinking territory is
    the classic signal that an evader is being cornered.
    """
    size = game_map.width * game_map.height
    dist = game_map.dist
    hb, sb = hunter * size, survivor * size
    count = 0
    for c in game_map.floor_cells:
        ds = dist[sb + c]
        if ds != UNREACHABLE and ds < dist[hb + c]:
            count += 1
    return count


def territory_fraction(game_map: GameMap, hunter: int, survivor: int) -> float:
    return survivor_territory(game_map, hunter, survivor) / max(1, len(game_map.floor_cells))


def territory_owner_map(game_map: GameMap, hunter: int, survivor: int) -> dict[int, int]:
    """Per-floor-cell owner: 1 = Survivor, 2 = Hunter (used by the overlay)."""
    return {
        c: 1 if game_map.distance(survivor, c) < game_map.distance(hunter, c) else 2
        for c in game_map.floor_cells
    }


def threat_distance(game_map: GameMap, state: GameState, survivor_cell: int | None = None) -> int:
    """How many Hunter moves away the Survivor is.

    A ready pounce counts as two tiles; each remaining stun turn adds one move.
    """
    cell = state.survivor if survivor_cell is None else survivor_cell
    d = game_map.distance(state.hunter, cell)
    if state.pounce_cooldown == 0 and d >= 2:
        d -= 1
    return d + state.hunter_stun


def degree(game_map: GameMap, cell: int) -> int:
    """Number of open neighbours (0..4) — a cheap local mobility signal."""
    base = cell * 5
    return sum(1 for n in game_map.step[base + 1 : base + 5] if n >= 0)
