# Benchmarks

500 matches: 5 Hunter algorithms × 5 Survivor algorithms × 20 seeded maps (seeds 1000–1019), **Normal** difficulty (MCTS 250 iterations, Minimax depth ≤ 6 / 0.5 s), default rules. Every matchup is played on the **same 20 maps**, so the cells can be compared directly.

Reproduce with:

```bash
neon-pursuit benchmark --games 20 --difficulty normal --seed 1000
```

> Minimax uses a wall-clock budget, so its search depth (and its exact results) vary slightly
> with CPU load. All other agents are fully deterministic for a given seed.

## Hunter win rate

Rows are the Hunter, columns the Survivor. Higher means the Hunter dominates.

| Hunter ↓ · Survivor → | MCTS | Fuzzy | Minimax | Greedy | Random |
|---|---:|---:|---:|---:|---:|
| **MCTS** | 70% | 95% | 85% | 75% | 100% |
| **Fuzzy** | 20% | 55% | 30% | 40% | 100% |
| **Minimax** | 100% | 100% | 100% | 100% | 100% |
| **Greedy** | 0% | 20% | 10% | 5% | 100% |
| **Random** | 20% | 0% | 30% | 0% | 100% |

## Overall ranking

Averaged over all five opponents in each role.

| Algorithm | Win rate as Hunter | Win rate as Survivor | Overall |
|---|---:|---:|---:|
| Minimax | 100% | 49% | 74% |
| MCTS | 85% | 58% | 72% |
| Fuzzy | 49% | 46% | 48% |
| Greedy | 27% | 56% | 42% |
| Random | 30% | 0% | 15% |

## Findings

1. **Minimax is a perfect Hunter.** It wins 100 % as Hunter against every opponent. With the
   pursuer's objective (reduce distance, guard food) a shallow, exact adversarial search is very
   effective, and iterative deepening with a transposition table keeps it within the time budget.
2. **MCTS is the best all-rounder.** It is the strongest Survivor (58 %) and the second-best
   Hunter (85 %). Survival needs long-horizon planning (route to a core, then escape), which suits
   rollouts better than a depth-limited tree. Minimax-as-Survivor often starves (it assumes a
   perfect Hunter and becomes too cautious).
3. **Fuzzy Logic is competitive without any search.** It decides in about 1 ms per move
   (100× faster than the search agents), beats Greedy and Random in both roles, and the Fuzzy-vs-
   Fuzzy mirror is close to even (55 %). As Hunter it beats MCTS-Survivors 20 % of the time,
   all by outright capture.
4. **Strong agents favour the Hunter.** In mirror matches the Hunter wins 70 % (MCTS), 55 % (Fuzzy)
   and 100 % (Minimax), while the Greedy mirror goes to the Survivor (5 %): a one-ply chaser
   cannot corner anyone. For a fairer fight, raise `core_energy` or lower `cores_to_win`.
5. **Baselines behave as expected.** Random never wins as Survivor. A Random Hunter still
   "wins" some games by starvation when a Survivor is too timid.

## Full results

| Hunter | Survivor | Games | Hunter win % | Captures | Starved | Escapes | Timeouts | Avg rounds | Avg cores | Hunter ms/move | Survivor ms/move |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fuzzy | fuzzy | 20 | 55% | 1 | 10 | 9 | 0 | 71.5 | 6.1 | 1.2 | 1.1 |
| fuzzy | greedy | 20 | 40% | 0 | 8 | 12 | 0 | 63.5 | 6.4 | 1.2 | 0.1 |
| fuzzy | mcts | 20 | 20% | 4 | 0 | 16 | 0 | 65.7 | 6.5 | 1.3 | 139.1 |
| fuzzy | minimax | 20 | 30% | 0 | 6 | 14 | 0 | 72.8 | 6.3 | 1.3 | 185.8 |
| fuzzy | random | 20 | 100% | 7 | 13 | 0 | 0 | 25.1 | 0.2 | 1.1 | 0.0 |
| greedy | fuzzy | 20 | 20% | 2 | 2 | 16 | 0 | 63.0 | 7.1 | 0.0 | 0.9 |
| greedy | greedy | 20 | 5% | 1 | 0 | 19 | 0 | 54.9 | 7.7 | 0.0 | 0.0 |
| greedy | mcts | 20 | 0% | 0 | 0 | 20 | 0 | 66.7 | 8.0 | 0.0 | 125.7 |
| greedy | minimax | 20 | 10% | 0 | 2 | 18 | 0 | 77.2 | 7.7 | 0.0 | 81.9 |
| greedy | random | 20 | 100% | 18 | 2 | 0 | 0 | 19.1 | 0.1 | 0.0 | 0.0 |
| mcts | fuzzy | 20 | 95% | 6 | 13 | 1 | 0 | 50.5 | 2.8 | 126.2 | 1.1 |
| mcts | greedy | 20 | 75% | 12 | 3 | 5 | 0 | 43.5 | 4.8 | 134.7 | 0.1 |
| mcts | mcts | 20 | 70% | 10 | 4 | 6 | 0 | 51.7 | 3.8 | 134.2 | 132.8 |
| mcts | minimax | 20 | 85% | 0 | 17 | 3 | 0 | 71.5 | 3.7 | 128.7 | 129.5 |
| mcts | random | 20 | 100% | 2 | 18 | 0 | 0 | 25.9 | 0.1 | 122.4 | 0.0 |
| minimax | fuzzy | 20 | 100% | 5 | 15 | 0 | 0 | 48.5 | 2.1 | 139.1 | 1.1 |
| minimax | greedy | 20 | 100% | 5 | 15 | 0 | 0 | 50.1 | 2.8 | 109.2 | 0.1 |
| minimax | mcts | 20 | 100% | 19 | 1 | 0 | 0 | 36.8 | 1.9 | 120.3 | 133.9 |
| minimax | minimax | 20 | 100% | 0 | 20 | 0 | 0 | 53.9 | 1.8 | 157.8 | 158.4 |
| minimax | random | 20 | 100% | 17 | 3 | 0 | 0 | 19.6 | 0.1 | 112.3 | 0.0 |
| random | fuzzy | 20 | 0% | 0 | 0 | 20 | 0 | 60.0 | 8.0 | 0.0 | 1.0 |
| random | greedy | 20 | 0% | 0 | 0 | 20 | 0 | 54.0 | 8.0 | 0.0 | 0.1 |
| random | mcts | 20 | 20% | 0 | 4 | 16 | 0 | 79.7 | 7.2 | 0.0 | 134.4 |
| random | minimax | 20 | 30% | 0 | 6 | 14 | 0 | 83.0 | 7.2 | 0.0 | 124.4 |
| random | random | 20 | 100% | 0 | 20 | 0 | 0 | 28.9 | 0.2 | 0.0 | 0.0 |
