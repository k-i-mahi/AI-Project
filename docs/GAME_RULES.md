# Game rules

Neon Pursuit is a two-player, turn-based **pursuit–evasion** game on a grid. It is
deterministic and has perfect information. One side is the **Hunter**, the other the
**Survivor**. Either side can be played by any AI algorithm or by a human.

## The arena

| Property | Default | Notes |
|---|---|---|
| Size | 21 × 15 tiles | including a solid border |
| Walls | ~24 % of the interior | short straight / L-shaped segments that never touch, leaving corridors open |
| Symmetry | left ↔ right mirrored walls | a balanced layout |
| Connectivity | guaranteed | only the largest connected region is kept |
| Spawns | **random** | never in a dead end, at least 12 steps apart (`max(8, (w + h) // 3)`) |

Every map is generated from a **seed**. The same seed always produces the same arena, the
same spawn positions, the same core spawn order and (with the same agents) the same match.
Every new game from the menu picks a random seed, so spawns change each time. A rematch
(`R`) keeps the seed; *New map* (`M`) rolls a new one.

## Turn structure

1. The **Survivor** moves.
2. The **Hunter** moves.

These two moves make up one *round*. On its turn a side may:

| Action | Effect |
|---|---|
| Wait | stay in place |
| Step N / E / S / W | move one tile |
| **Burst** N / E / S / W | move two tiles in a straight line (both must be open) |

A burst is called a **Dash** for the Survivor (7-round cooldown, costs 3 extra energy, needs more
than 3 energy) and a **Pounce** for the Hunter (9-round cooldown). A pounce captures the
Survivor if its *first* tile reaches it. The Survivor may never step onto, or dash through,
the Hunter's tile.

## Energy and cores

* Four **energy cores** are on the board at all times.
* Moving onto a core (including the mid-tile of a dash) collects it and restores **+15 energy**,
  capped at 45.
* The Survivor starts with **35 energy** and loses **1 per round**.
* Collected cores respawn from a deterministic sequence, never within 4 tiles of the Survivor.

## How a match ends

| Winner | Condition | Reason shown |
|---|---|---|
| Hunter | moves onto the Survivor's tile | *Captured* |
| Hunter | Survivor's energy reaches 0 | *Starved* |
| Survivor | collects **8 cores** (configurable 6–12) | *Escaped* |
| Survivor | lasts **160 rounds** | *Survived* |

Because energy keeps draining, the Survivor cannot just hide. It has to take risks to feed.
The Hunter has two ways to win: chase the Survivor down, or guard the cores until it starves.
Good agents use both.

## Configuration

All rules live in `neon_pursuit.engine.MatchConfig`:

```python
MatchConfig(
    width=21, height=15, seed=2026, wall_density=0.24,
    active_cores=4, cores_to_win=8, max_rounds=160,
    dash_cooldown=7, pounce_cooldown=9,
    start_energy=35, max_energy=45, core_energy=15, dash_energy=3,
)
```
