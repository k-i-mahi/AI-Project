# The AI algorithms

Every agent implements one interface (`neon_pursuit.ai.base.Agent`):

```python
class Agent(ABC):
    def decide(self, state: GameState) -> Decision: ...      # timed wrapper
    def choose(self, state: GameState) -> tuple[Action, Insight]: ...
```

A `Decision` carries the chosen action, the time spent thinking and an **`Insight`**: a
structured explanation that the in-game "brain" panels render live (MCTS visit counts, fuzzy
rule firing, minimax scores, predicted path). Any algorithm can play **either role**. The role
only changes the point of view.

All agents share two precomputed tables from the map, so they never path-find at decision time:

* `dist[a * size + b]`: all-pairs shortest-path distance (one BFS per floor cell).
* `step[cell * 5 + d]`: the neighbour in direction `d`, or `-1` if blocked.

---

## 1. Monte Carlo Tree Search (UCT)

`src/neon_pursuit/ai/mcts.py`

MCTS builds an asymmetric search tree by repeatedly simulating the future. Each iteration has
four phases:

1. **Selection**: from the root, follow the child that maximises the UCT score

   $$\text{UCT}(child) = \frac{Q}{N} + c\sqrt{\frac{\ln N_{parent}}{N}}$$

   where *Q/N* is the child's mean reward for the player who moved into it and *c* = 1.2.
2. **Expansion**: add one untried action as a new node.
3. **Simulation**: play an ε-greedy rollout (ε = 0.2) for up to 14 plies. The default policy
   uses the greedy chaser/forager below, so rollouts are realistic rather than random. If the
   rollout is cut short, the static evaluation function scores the position.
4. **Backpropagation**: add the result to every node on the path. The reward is flipped
   (*v* for the Survivor, *1 − v* for the Hunter), so one tree serves both players of this
   alternating, zero-sum game.

The move played is the **most-visited** root child (more robust than the highest mean).

| Difficulty | Iterations | Time cap |
|---|---|---|
| Easy | 80 | 0.4 s |
| Normal | 250 | 0.9 s |
| Hard | 900 | 2.5 s |

**In the brain panel:** visits per action, estimated win rate, tree depth, and the principal
variation (most-visited line) drawn on the board as a dotted path.

---

## 2. Fuzzy Logic Controller (Mamdani)

`src/neon_pursuit/ai/fuzzy/system.py` (generic engine) and `.../fuzzy/controllers.py` (rule bases)

The fuzzy agent does **not search**. For every legal action it measures a few crisp features of
the position the action leads to. It runs those through a Mamdani inference system and plays
the action with the highest *desirability*.

### Inference pipeline

1. **Fuzzification**: each input is mapped onto linguistic terms with trapezoidal / triangular
   membership functions.
2. **Rule evaluation**: AND = `min`, OR = `max`, multiplied by an optional rule weight.
3. **Implication & aggregation**: each consequent term is clipped at its rule strength (min),
   and all clipped sets are merged with `max`.
4. **Defuzzification**: the **centroid** of the aggregated set (sampled at 101 points).

### Design lesson: use fuzzy partitions

With Mamdani + centroid, a rule base where only *one* output term fires always defuzzifies to
that term's centre, however weakly it fires. Early versions of this agent therefore saw no
difference between being 6 or 9 tiles from a core and wandered aimlessly. The fix: every input
uses a **Ruspini partition**. Adjacent terms overlap and their memberships sum to 1 everywhere
(a unit test checks this). Neighbouring tiles then always produce slightly different outputs, so
the controller has a direction to follow.

### Survivor rule base (4 inputs, 13 rules)

| Input | Meaning | Terms |
|---|---|---|
| `danger` | Hunter moves needed to reach the tile (a ready pounce counts as 2) | critical · near · safe |
| `core` | distance to the nearest *safe* core (see below) | close · mid · far |
| `space` | Voronoi territory share after the move | cornered · limited · open |
| `energy` | energy after the move / max | low · medium · high |

```
S1  IF danger critical                         THEN avoid
S2  IF danger near AND space cornered          THEN avoid
S3  IF danger near AND core close              THEN good
S7  IF danger safe AND core close              THEN excellent
S11 IF energy low  AND core close              THEN excellent
S13 IF energy low  AND core far                THEN avoid
…   (13 rules in total, see controllers.py)
```

**Feature engineering:** `core` is not the raw distance to the nearest core. It uses
`safe_core_distance`: cores the Hunter would reach first are charged an extra
`6 × energy_ratio` tiles. A well-fed Survivor avoids guarded cores. A starving one gambles,
because the penalty shrinks toward 0.

### Hunter rule base (4 inputs, 11 rules)

| Input | Meaning | Terms |
|---|---|---|
| `gap` | effective moves to reach the Survivor | striking · close · distant |
| `squeeze` | Survivor's Voronoi territory share | cornered · limited · open |
| `intercept` | my distance to the Survivor's target core minus its distance | ahead · level · behind |
| `prey_energy` | Survivor energy / max | starving · fed |

The Hunter learns two styles from its rules: close in and squeeze, or get *ahead* on the
Survivor's next core and starve it out (`H9: IF prey_energy starving AND intercept ahead THEN
excellent`).

**In the brain panel:** each input's membership degrees, the strongest rules with their firing
strength, the aggregated output curve and its centroid.

---

## 3. Minimax with α-β pruning

`src/neon_pursuit/ai/minimax.py`

A classic adversarial search that assumes the opponent always plays its best reply.

* **Negamax** formulation: values are always from the side-to-move's point of view.
* **Alpha-beta pruning** skips branches that cannot change the decision.
* **Iterative deepening** searches depth 1, 2, 3, … until the time budget runs out. The best
  move of each iteration is searched first in the next one, which sharply increases cut-offs.
* **Move ordering** tries approach moves first (Hunter) or retreat moves first (Survivor).
* **Transposition table** stores values keyed by the state, with EXACT / LOWER / UPPER bound
  flags so pruned values are never reused as exact.
* Terminal values are scaled by remaining depth so it prefers quicker wins and slower losses.

**In the brain panel:** depth reached, nodes searched, pruning cut-offs and per-action scores.

---

## 4. Shared static evaluation

`src/neon_pursuit/ai/heuristics.py`. Used at MCTS rollout cut-offs and minimax leaves. It returns
the Survivor's prospects in [0, 1] (the Hunter uses `1 − v`):

| Feature | Weight |
|---|---|
| safety: `1 − exp(−(threat − 1) / 2.5)` | 0.28 |
| Voronoi territory share | 0.14 |
| progress: cores collected / cores needed | 0.28 |
| closeness of nearest safe core (weight grows with hunger) | 0.12 + 0.14·hunger |
| energy | 0.10 |

If the Survivor cannot reach any core before its energy runs out, the value is multiplied
by 0.3.

---

## 5. Baselines

* **Greedy Pathfinder**: one-ply lookahead on BFS distances. The Hunter steps along the
  shortest path to the Survivor (it saves the pounce unless it lands a capture). The Survivor
  keeps its distance and detours for cores, more boldly the hungrier it is. It is also the
  MCTS rollout policy.
* **Random Walker**: uniformly random legal moves. It sets the performance floor.

A sophisticated algorithm only matters if it beats these. See [BENCHMARKS.md](BENCHMARKS.md).
