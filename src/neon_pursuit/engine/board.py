"""Procedural arena generation and precomputed path data."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from .rng import make_rng
from .types import MatchConfig

UNREACHABLE = 0xFFFF

#: Direction deltas indexed 1..4 = N, E, S, W (index 0 = stay in place).
DIR_DX: tuple[int, ...] = (0, 0, 1, 0, -1)
DIR_DY: tuple[int, ...] = (0, -1, 0, 1, 0)


@dataclass(slots=True, frozen=True)
class GameMap:
    """Immutable board shared by every state of a match.

    Cells are addressed by a single integer ``cell = y * width + x``. Two lookup
    tables are precomputed so that agents never run path-finding at decision
    time:

    * ``dist`` — all-pairs shortest-path distances (BFS, 4-neighbourhood),
      flattened as ``dist[a * size + b]``.
    * ``step`` — ``step[cell * 5 + d]`` is the neighbour in direction ``d``
      (1..4) or ``-1`` when blocked; ``step[cell * 5]`` is the cell itself.
    """

    width: int
    height: int
    walls: bytes
    floor_cells: tuple[int, ...]
    dist: tuple[int, ...]
    step: tuple[int, ...]
    hunter_spawn: int
    survivor_spawn: int
    #: Deterministic order in which cores appear.
    core_sequence: tuple[int, ...]

    @property
    def size(self) -> int:
        return self.width * self.height

    def distance(self, a: int, b: int) -> int:
        return self.dist[a * self.width * self.height + b]

    def xy(self, cell: int) -> tuple[int, int]:
        return cell % self.width, cell // self.width

    def cell(self, x: int, y: int) -> int:
        return y * self.width + x

    def is_wall(self, cell: int) -> bool:
        return self.walls[cell] == 1

    def neighbours(self, cell: int) -> list[int]:
        base = cell * 5
        return [n for n in self.step[base + 1 : base + 5] if n >= 0]


def bfs(walls: bytearray | bytes, width: int, height: int, source: int) -> list[int]:
    """Single-source BFS over floor tiles; returns a distance per cell."""
    out = [UNREACHABLE] * (width * height)
    if walls[source]:
        return out
    out[source] = 0
    queue: deque[int] = deque([source])
    while queue:
        c = queue.popleft()
        x, y = c % width, c // width
        nd = out[c] + 1
        for k in range(1, 5):
            nx, ny = x + DIR_DX[k], y + DIR_DY[k]
            if 0 <= nx < width and 0 <= ny < height:
                n = ny * width + nx
                if not walls[n] and out[n] == UNREACHABLE:
                    out[n] = nd
                    queue.append(n)
    return out


@lru_cache(maxsize=32)
def generate_map(config: MatchConfig) -> GameMap:
    """Build a left-right mirrored arena with random spawns from ``config.seed``.

    1. Scatter short wall segments over the left half.
    2. Mirror them onto the right half so the layout is balanced.
    3. Keep only the largest connected floor region (connectivity repair).
    4. Precompute distance/step tables.
    5. Pick random spawns (see :func:`choose_spawns`) and the core spawn sequence.
    """
    width, height = config.width, config.height
    size = width * height
    walls = bytearray(size)
    rng = make_rng(config.seed, 1)

    for x in range(width):
        walls[x] = walls[(height - 1) * width + x] = 1
    for y in range(height):
        walls[y * width] = walls[y * width + width - 1] = 1

    half = (width + 1) // 2
    target = round((half - 1) * (height - 2) * config.wall_density)
    placed = guard = 0
    while placed < target and guard < 4_000:
        guard += 1
        # Straight or L-shaped segment; never touching another obstacle (8-neighbourhood),
        # which keeps corridors open and produces evenly spread "pillars".
        horizontal = rng.random() < 0.5
        length = 2 + rng.randrange(3)
        x0 = 2 + rng.randrange(max(1, half - 2))
        y0 = 2 + rng.randrange(max(1, height - 4))
        cells = [(x0 + i, y0) if horizontal else (x0, y0 + i) for i in range(length)]
        if rng.random() < 0.35:
            lx, ly = cells[-1]
            cells += [(lx, ly + 1)] if horizontal else [(lx + 1, ly)]
        if any(not (2 <= x < half and 2 <= y < height - 2) for x, y in cells):
            continue
        own = set(cells)
        blocked = any(
            walls[(y + dy) * width + (x + dx)] and (x + dx, y + dy) not in own
            for x, y in cells
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if x + dx < half
        )
        if blocked:
            continue
        for x, y in cells:
            walls[y * width + x] = 1
        placed += len(cells)

    for y in range(height):
        for x in range(half):
            walls[y * width + (width - 1 - x)] = walls[y * width + x]

    _keep_largest_region(walls, width, height)

    floor = tuple(c for c in range(size) if not walls[c])

    dist = [UNREACHABLE] * (size * size)
    for src in floor:
        dist[src * size : (src + 1) * size] = bfs(walls, width, height, src)

    step = [-1] * (size * 5)
    for c in floor:
        step[c * 5] = c
        x, y = c % width, c // width
        for d in range(1, 5):
            n = (y + DIR_DY[d]) * width + (x + DIR_DX[d])
            if not walls[n]:
                step[c * 5 + d] = n

    hunter_spawn, survivor_spawn = choose_spawns(floor, dist, step, width, height, config.seed)

    core_rng = make_rng(config.seed, 2)
    candidates = [
        c
        for c in floor
        if dist[hunter_spawn * size + c] >= 3 and dist[survivor_spawn * size + c] >= 3
    ]
    sequence: list[int] = []
    for _ in range(4):
        batch = candidates[:]
        core_rng.shuffle(batch)
        sequence.extend(batch)

    return GameMap(
        width=width,
        height=height,
        walls=bytes(walls),
        floor_cells=floor,
        dist=tuple(dist),
        step=tuple(step),
        hunter_spawn=hunter_spawn,
        survivor_spawn=survivor_spawn,
        core_sequence=tuple(sequence),
    )


def _keep_largest_region(walls: bytearray, width: int, height: int) -> None:
    """Seal every floor region except the largest one, so all floor is mutually reachable."""
    size = width * height
    seen = [False] * size
    best: list[int] = []
    for start in range(size):
        if walls[start] or seen[start]:
            continue
        dist = bfs(walls, width, height, start)
        region = [c for c in range(size) if dist[c] != UNREACHABLE]
        for c in region:
            seen[c] = True
        if len(region) > len(best):
            best = region
    keep = set(best)
    for c in range(size):
        if not walls[c] and c not in keep:
            walls[c] = 1


def choose_spawns(
    floor: tuple[int, ...],
    dist: list[int],
    step: list[int],
    width: int,
    height: int,
    seed: int,
) -> tuple[int, int]:
    """Pick random, fair starting cells for ``(hunter, survivor)``.

    Both spawns have at least two open neighbours (never a dead end) and are at
    least ``max(8, (width + height) // 3)`` path steps apart, so neither side
    starts within striking range. The choice is derived from the seed, so a
    rematch on the same seed reproduces it exactly.
    """
    size = width * height
    rng = make_rng(seed, 3)
    open_cells = [c for c in floor if sum(1 for d in range(1, 5) if step[c * 5 + d] >= 0) >= 2]
    pool = open_cells or list(floor)
    survivor = rng.choice(pool)
    min_sep = max(8, (width + height) // 3)
    far = [c for c in pool if min_sep <= dist[survivor * size + c] != UNREACHABLE]
    if far:
        hunter = rng.choice(far)
    else:  # tiny maps: fall back to the farthest reachable cell
        hunter = max(pool, key=lambda c: dist[survivor * size + c] % UNREACHABLE)
    return hunter, survivor
