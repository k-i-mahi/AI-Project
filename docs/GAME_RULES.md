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
| Connectivity | guaranteed | only the largest connected floor region is kept |
| Spawns | **random** | never in a dead end, at least `max(8, (w + h) // 3)` = 12 path steps apart |

Every map is generated from a **seed**. The same seed always produces the same arena, the
same spawn positions, the same core spawn order and (with the same agents) the same match.
Every new game from the menu picks a random seed, so maps and spawns change each time.
Rematch (`R`) keeps the seed; *New map* (`M`) rolls a new one.

## Turn structure

1. The **Survivor** moves.
2. The **Hunter** moves.

These two moves make up one *round*. On its turn a side may:

| Action | Who | Effect |
|---|---|---|
| Wait | both | stay in place |
| Step N / E / S / W | both | move one tile |
| **Pounce** N / E / S / W | Hunter | move two tiles in a straight line (both open); captures if the first tile hits the Survivor. 9-round cooldown |
| **Blink Dash** N / E / S / W | Survivor | move two tiles in a straight line, and the middle tile may be a **wall** (it leaps over it). 7-round cooldown, costs 3 energy, needs more than 3 energy |
| **EMP Pulse** | Survivor | only when the Hunter is within 3 path steps: the Hunter is **stunned for 3 turns** (it may only wait). 18-round cooldown, costs 4 energy |

The Survivor may never step onto, or dash through, the Hunter's tile.

## Energy and cores

* Four **energy cores** are on the board at all times.
* Moving onto a core (including the middle tile of a dash) collects it and restores
  **+15 energy**, capped at 45.
* The Survivor starts with **35 energy** and loses **1 per round**.
* Collected cores respawn from a deterministic sequence, never within 4 steps of either player,
  and preferably **inside the Survivor's territory** (cells it reaches strictly before the
  Hunter). Without this rule a strong Hunter could win simply by camping between the Survivor
  and the food. The [benchmarks](BENCHMARKS.md) showed that happening before the rule existed.

## How a match ends

| Winner | Condition | Reason shown |
|---|---|---|
| Hunter | moves onto the Survivor's tile | *Captured* |
| Hunter | Survivor's energy reaches 0 | *Starved* |
| Survivor | collects **10 cores** (configurable 6–12) | *Escaped* |
| Survivor | lasts **160 rounds** | *Survived* |

## Configuration

All rules live in `neon_pursuit.engine.MatchConfig`:

```python
MatchConfig(
    width=21, height=15, seed=2026, wall_density=0.24,
    active_cores=4, cores_to_win=10, max_rounds=160,
    dash_cooldown=7, pounce_cooldown=9,
    start_energy=35, max_energy=45, core_energy=15, dash_energy=3,
    pulse_radius=3, pulse_stun=3, pulse_cooldown=18, pulse_energy=4,
)
```

## How the defaults were chosen

The rules were tuned from data, not by feel. Candidate rule sets were swept with mirror
matches (MCTS vs MCTS, Minimax vs Minimax, Fuzzy vs Fuzzy, …):

| Change | Effect |
|---|---|
| Original rules (fixed spawns, 8 cores) | Minimax Hunter won **100 %** against everyone |
| More energy, more cores, weaker pounce | Minimax Hunter still ≈ 94–100 %. The cause was core camping, not raw power |
| EMP pulse | Little change on its own. MCTS Survivors were walking into shallow traps (fixed separately) |
| Cores spawn in the Survivor's territory | Swung to Survivor-favoured (MCTS mirror 12 % Hunter) |
| … plus 10 cores to win | No algorithm wins every matchup; the game now leans toward the Survivor except against Minimax (see [BENCHMARKS.md](BENCHMARKS.md)) |

### Why not raise `cores_to_win` further?

A final sweep with the GA-tuned controllers (16 games per cell, Hunter win rate):

| cores_to_win | MCTS mirror | Minimax mirror | Fuzzy mirror | Minimax H vs MCTS S |
|---|---:|---:|---:|---:|
| **10** (default) | 31 % | 69 % | 0 % | 69 % |
| 12 | 44 % | 94 % | 0 % | 94 % |
| 14 | 44 % | 88 % | 0 % | 100 % |

A higher target helps weaker Hunters slightly, but it brings back Minimax dominance. The Fuzzy
mirror stays at 0 % whatever the setting. The remaining imbalance is therefore about *hunting
ability*, not the rules. A one-ply chaser (Fuzzy, Greedy) cannot corner an equally fast evader
on a map with cycles, the classic "cops and robbers on graphs" result. Search-based Hunters
can. Ten cores is the best compromise.
