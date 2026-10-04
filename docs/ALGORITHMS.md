# The AI algorithms

Six AI techniques are used in this project:

| # | Technique | Where | Role in the game |
|---|---|---|---|
| 1 | Monte Carlo Tree Search (UCT) | `ai/mcts.py` | plays either side |
| 2 | Mamdani Fuzzy Logic | `ai/fuzzy/` | plays either side |
| 3 | Minimax + α-β pruning | `ai/minimax.py` | plays either side |
| 4 | Greedy best-first (BFS distances) | `ai/simple.py` | baseline, MCTS rollout policy |
| 5 | Random | `ai/simple.py` | baseline |
| 6 | **Genetic Algorithm** | `ai/fuzzy/tuning.py` | *optimises* the fuzzy controllers offline |

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

Difficulty presets (`presets.py`) set the search budgets:

| Difficulty | MCTS iterations | Minimax node budget / max depth | Fuzzy |
|---|---|---|---|
| Easy | 80 | 1 500 / 4 | jitter 0.06 (makes small mistakes) |
| Normal | 250 | 6 000 / 8 | jitter 0.01 |
| Hard | 900 | 20 000 / 12 | deterministic |

Budgets are counted in **iterations / nodes, not milliseconds**, so a decision never depends on
CPU load and benchmarks are reproducible.

---

## 1. Monte Carlo Tree Search (UCT)

MCTS builds an asymmetric search tree by repeatedly simulating the future. Each iteration has
four phases:

1. **Selection**: from the root, follow the child that maximises

   $$\text{UCT}(child) = \frac{Q}{N} + c\sqrt{\frac{\ln N_{parent}}{N}}, \qquad c = 1.2$$

2. **Expansion**: add one untried action as a new node.
3. **Simulation**: an ε-greedy rollout (ε = 0.2, greedy chaser/forager policy) for up to 14
   plies, then the static evaluation scores the position.
4. **Backpropagation**: the reward is *v* for nodes the Survivor moved into and *1 − v* for
   the Hunter's, so one tree serves both players of this alternating, zero-sum game.

The move played is the **most-visited** root child.

**Decisive / anti-decisive screening.** Benchmarks showed a classic MCTS weakness. With ~10
moves at the root and noisy rollouts, the Survivor sometimes stepped next to the Hunter and lost
on the spot ("shallow traps"). Before searching, the root is now screened:

* if a move **wins immediately**, play it;
* discard moves after which the opponent has an **immediate win**, unless no safe move exists.

---

## 2. Fuzzy Logic Controller (Mamdani)

`ai/fuzzy/system.py` is a generic inference engine. `ai/fuzzy/genome.py` holds the rule bases,
and `ai/fuzzy/controllers.py` the agent.

The fuzzy agent does **not search**. For every legal action it measures crisp features of the
position the action leads to, runs them through Mamdani inference and plays the action with the
highest defuzzified *desirability*. It decides in about **1 ms**, roughly 100× faster than the
search agents.

### Inference pipeline

1. **Fuzzification**: trapezoidal / triangular membership functions.
2. **Rule evaluation**: AND = `min`, scaled by the rule's weight.
3. **Implication & aggregation**: clip each consequent at its rule strength, merge with `max`.
4. **Defuzzification**: the **centroid** of the aggregated set (101 samples).

### Fuzzy partitions

With Mamdani + centroid, a rule base where only *one* output term fires always defuzzifies to
that term's centre, however weakly it fires. The first version therefore could not tell 6 tiles
from 9 and wandered. Every input is now a **Ruspini partition**: adjacent terms overlap and sum
to 1 everywhere, so moving one tile always changes the output. Partitions are generated from
breakpoints `a ≤ b ≤ c`:

```
term 1: trapezoid(low, low, a, b)   term 2: triangle(a, b, c)   term 3: trapezoid(b, c, high, high)
```

### Survivor rule base (4 inputs, 13 rules)

| Input | Meaning | Terms |
|---|---|---|
| `danger` | Hunter moves needed to reach the tile (ready pounce = 2 tiles, each stun turn +1) | critical · near · safe |
| `core` | distance to the nearest *safe* core | close · mid · far |
| `space` | Voronoi territory share after the move | cornered · limited · open |
| `energy` | energy after the move / max | low · medium · high |

```
S1  IF danger critical                  THEN avoid
S2  IF danger near AND space cornered   THEN avoid
S3  IF danger near AND core close       THEN good
S7  IF danger safe AND core close       THEN excellent
S11 IF energy low  AND core close       THEN excellent
S13 IF energy low  AND core far         THEN avoid
…   (13 rules in total, see genome.py)
```

**Contested cores.** `core` uses `safe_core_distance`: a core the Hunter would reach first is
charged `6 × energy_ratio` extra tiles. A fed Survivor avoids guarded cores; a starving one
gambles.

**EMP pulse.** The pulse action is scored like any other move: the stun adds 3 to `danger`, so it
wins exactly when the Hunter is about to strike. A small crisp penalty keeps it for real danger.

### Hunter rule base (4 inputs, 11 rules)

| Input | Meaning | Terms |
|---|---|---|
| `gap` | effective moves to reach the Survivor | striking · close · distant |
| `squeeze` | Survivor's Voronoi territory share | cornered · limited · open |
| `intercept` | my distance to the Survivor's target core − its distance | ahead · level · behind |
| `prey_energy` | Survivor energy / max | starving · fed |

---

## 3. Minimax with α-β pruning

* **Negamax**: values are always from the side-to-move's point of view.
* **Alpha-beta pruning** with **move ordering** (approach first for the Hunter, retreat first for
  the Survivor).
* **Iterative deepening** under a **node budget**: depth 1, 2, 3, … until the budget runs out;
  the deepest *completed* iteration is played. The previous iteration's best move is searched
  first, which sharply increases cut-offs.
* **Transposition table** keyed by the full state, storing EXACT / LOWER / UPPER bound flags so
  pruned values are never reused as exact.
* Terminal values are scaled by remaining depth, so it prefers quicker wins and slower losses.

---

## 4. Shared static evaluation

`ai/heuristics.py`. Used at MCTS rollout cut-offs and minimax leaves. It returns the Survivor's
prospects in [0, 1] (the Hunter uses `1 − v`):

| Feature | Weight |
|---|---|
| safety `1 − exp(−(threat − 1) / 2.5)` (stun turns count as distance) | 0.28 |
| Voronoi territory share | 0.14 |
| progress: cores collected / cores needed | 0.28 |
| closeness of the nearest safe core (weight grows with hunger) | 0.12 + 0.14·hunger |
| energy | 0.10 |

If the Survivor cannot reach any core before its energy runs out, the value is multiplied by 0.3.

---

## 5. Baselines

* **Greedy**: one-ply lookahead on BFS distances. The Hunter steps along the shortest path; the
  Survivor keeps its distance, detours for cores (more boldly when hungry) and fires the EMP
  when the Hunter is about to strike. It is also the MCTS rollout policy.
* **Random**: uniformly random legal moves.

---

## 6. Genetic Algorithm: tuning the fuzzy controllers

`ai/fuzzy/tuning.py`, run with `neon-pursuit tune`.

Hand-picking membership functions is guesswork. The GA keeps the **rule structure** (still human
written and explainable) and evolves the **numbers**: every input's partition breakpoints plus
one weight per rule (a `FuzzyGenome`).

| Component | Choice |
|---|---|
| Representation | breakpoints per input (sorted, clamped, min spacing 1 % of range) + rule weights ∈ [0.05, 1] |
| Initial population | the hand-made genome + 15 mutants |
| Fitness | win rate vs a panel of opponents (Greedy, Fuzzy, MCTS, Minimax at Easy budget) + small tie-breaker |
| Noise control | every genome in a generation plays the **same seeds** (common random numbers) |
| Selection | tournament (k = 3) + elitism (2) |
| Variation | uniform crossover per variable / rule, Gaussian mutation scaled to the variable's range |
| Final pick | the finalists are re-tested on **fresh seeds** (3× games), which avoids the winner's curse |
| Validation | tuned vs hand-made on **held-out maps** at Normal difficulty ([BENCHMARKS.md](BENCHMARKS.md)) |

**Domain constraints.** In its first run the GA found a loophole. It shrank the Survivor's
"critical" danger term below one move, so stepping next to the Hunter no longer looked bad.
Rare enough in training games to go unpunished, it is plainly wrong. The constraint
`danger ≤ 1 ⇒ fully critical` is now enforced on every genome
(`genome.MIN_FIRST_BREAKPOINT`), and a regression test guards it. This shows that an optimiser
needs the designer's knowledge as constraints, not just a fitness score.

The winning genomes are shipped in `ai/fuzzy/tuned.json` and used by default
(`FuzzyParams.profile = "tuned"`). The brain panel shows whether a controller runs *GA-tuned* or
*hand-made* parameters.
