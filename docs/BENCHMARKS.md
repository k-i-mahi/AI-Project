# Benchmarks

500 matches: 5 Hunter algorithms × 5 Survivor algorithms × 20 seeded maps (seeds 1000–1019), **Normal** difficulty (MCTS 250 iterations, Minimax 6 000 nodes), default rules, GA-tuned fuzzy controllers. Every matchup is played on the **same 20 maps**. All search budgets are counted in
iterations / nodes, so results are reproducible regardless of CPU load.

Reproduce with:

```bash
neon-pursuit benchmark --games 20 --difficulty normal --seed 1000 --workers 6
```

## Hunter win rate

Rows are the Hunter, columns the Survivor. Higher means the Hunter dominates. 95 % Wilson
intervals for every cell are in the full table below (with 20 games a cell's interval is
roughly ±20 points, so small differences are not significant).

| Hunter ↓ · Survivor → | MCTS | Fuzzy | Minimax | Greedy | Random |
|---|---:|---:|---:|---:|---:|
| **MCTS** | 35% | 15% | 30% | 30% | 100% |
| **Fuzzy** | 10% | 10% | 25% | 5% | 100% |
| **Minimax** | 85% | 40% | 90% | 40% | 100% |
| **Greedy** | 0% | 5% | 0% | 5% | 100% |
| **Random** | 0% | 0% | 0% | 0% | 100% |

## Overall ranking

Pooled over all five opponents in each role (100 games per role, 200 per algorithm).

| Algorithm | Win rate as Hunter | Win rate as Survivor | Overall | 95% CI (overall) |
|---|---:|---:|---:|---:|
| Minimax | 71% | 71% | **71%** | 64%–77% |
| MCTS | 42% | 74% | **58%** | 51%–65% |
| Fuzzy | 30% | 86% | **58%** | 51%–65% |
| Greedy | 22% | 84% | **53%** | 46%–60% |
| Random | 20% | 0% | **10%** | 7%–15% |

## Genetic-algorithm validation

The fuzzy controllers were tuned on different seeds (and Easy-budget opponents), then compared
with the hand-made parameters on **held-out maps** at Normal difficulty, 20 games per row:

| Matchup (held-out seeds 20000–20019, Normal) | Hand-made fuzzy | GA-tuned fuzzy |
|---|---:|---:|
| Fuzzy **Hunter** vs MCTS: Hunter win rate ↑ | 0 % | **15 %** |
| Fuzzy **Hunter** vs Minimax: Hunter win rate ↑ | 0 % | **25 %** |
| Fuzzy **Hunter** vs Greedy: Hunter win rate ↑ | 0 % | 0 % |
| MCTS Hunter vs Fuzzy **Survivor**: Hunter win rate ↓ | 60 % | **25 %** |
| Minimax Hunter vs Fuzzy **Survivor**: Hunter win rate ↓ | 100 % | **60 %** |
| Greedy Hunter vs Fuzzy **Survivor**: Hunter win rate ↓ | 20 % | **15 %** |

## Findings

1. **No algorithm is unbeatable anymore.** Before the rule changes, Minimax won 100 % of its
   games as Hunter. It is still the best overall (71 %) and the only reliable Hunter, but it
   loses 60 % of its hunts against the GA-tuned fuzzy Survivor.
2. **The GA-tuned fuzzy controller is the best Survivor** (86 % survival) and ties MCTS overall
   (58 %), while deciding in about 0.6 ms per move against 85–140 ms for MCTS and Minimax. Tuning
   lifted it from below the Greedy baseline to joint second place.
3. **MCTS is a strong Survivor (74 %) but a modest Hunter (42 %).** Capturing an evader takes
   precise tactics, which exact search (Minimax) does better than sampled rollouts.
4. **The final rules lean towards the Survivor** against every Hunter except Minimax: the MCTS
   mirror goes 35 % to the Hunter, the Fuzzy mirror 10 %. This is the cost of removing the
   core-camping exploit. Raising `cores_to_win` shifts the balance back toward the Hunter if a
   closer fight is wanted.
5. **Baselines behave as expected.** Random never survives, and a Random or Greedy Hunter
   almost never catches anything competent.

How the rules got here (and why) is documented in [GAME_RULES.md](GAME_RULES.md#how-the-defaults-were-chosen).

## Full results

| Hunter | Survivor | Games | Hunter win % | 95% CI | Captures | Starved | Escapes | Timeouts | Avg rounds | Avg cores | Hunter ms/move | Survivor ms/move |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fuzzy | fuzzy | 20 | 10% | 3%-30% | 2 | 0 | 18 | 0 | 47.6 | 9.6 | 0.6 | 0.5 |
| fuzzy | greedy | 20 | 5% | 1%-24% | 0 | 1 | 19 | 0 | 60.1 | 9.8 | 0.6 | 0.0 |
| fuzzy | mcts | 20 | 10% | 3%-30% | 1 | 1 | 18 | 0 | 65.0 | 9.2 | 0.7 | 86.5 |
| fuzzy | minimax | 20 | 25% | 11%-47% | 1 | 4 | 15 | 0 | 82.3 | 9.1 | 0.7 | 137.8 |
| fuzzy | random | 20 | 100% | 84%-100% | 17 | 3 | 0 | 0 | 18.7 | 0.3 | 0.6 | 0.0 |
| greedy | fuzzy | 20 | 5% | 1%-24% | 1 | 0 | 19 | 0 | 48.4 | 9.8 | 0.0 | 0.4 |
| greedy | greedy | 20 | 5% | 1%-24% | 1 | 0 | 19 | 0 | 50.2 | 9.9 | 0.0 | 0.0 |
| greedy | mcts | 20 | 0% | 0%-16% | 0 | 0 | 20 | 0 | 68.5 | 10.0 | 0.0 | 88.4 |
| greedy | minimax | 20 | 0% | 0%-16% | 0 | 0 | 20 | 0 | 73.9 | 10.0 | 0.0 | 114.2 |
| greedy | random | 20 | 100% | 84%-100% | 19 | 1 | 0 | 0 | 16.9 | 0.3 | 0.0 | 0.0 |
| mcts | fuzzy | 20 | 15% | 5%-36% | 3 | 0 | 17 | 0 | 49.1 | 9.4 | 83.2 | 0.6 |
| mcts | greedy | 20 | 30% | 15%-52% | 4 | 2 | 14 | 0 | 55.1 | 9.1 | 80.7 | 0.0 |
| mcts | mcts | 20 | 35% | 18%-57% | 1 | 6 | 13 | 0 | 75.8 | 7.7 | 84.7 | 85.6 |
| mcts | minimax | 20 | 30% | 15%-52% | 0 | 6 | 14 | 0 | 86.0 | 8.8 | 82.9 | 124.7 |
| mcts | random | 20 | 100% | 84%-100% | 12 | 8 | 0 | 0 | 19.0 | 0.3 | 77.8 | 0.0 |
| minimax | fuzzy | 20 | 40% | 22%-61% | 3 | 5 | 12 | 0 | 55.0 | 8.2 | 122.8 | 0.5 |
| minimax | greedy | 20 | 40% | 22%-61% | 2 | 6 | 12 | 0 | 63.8 | 8.2 | 123.0 | 0.0 |
| minimax | mcts | 20 | 85% | 64%-95% | 7 | 10 | 3 | 0 | 71.0 | 5.4 | 130.7 | 84.7 |
| minimax | minimax | 20 | 90% | 70%-97% | 0 | 18 | 2 | 0 | 78.0 | 4.8 | 137.6 | 140.7 |
| minimax | random | 20 | 100% | 84%-100% | 15 | 5 | 0 | 0 | 20.4 | 0.3 | 125.2 | 0.0 |
| random | fuzzy | 20 | 0% | 0%-16% | 0 | 0 | 20 | 0 | 45.8 | 10.0 | 0.0 | 0.5 |
| random | greedy | 20 | 0% | 0%-16% | 0 | 0 | 20 | 0 | 45.9 | 10.0 | 0.0 | 0.0 |
| random | mcts | 20 | 0% | 0%-16% | 0 | 0 | 20 | 0 | 63.6 | 10.0 | 0.0 | 94.9 |
| random | minimax | 20 | 0% | 0%-16% | 0 | 0 | 20 | 0 | 57.9 | 10.0 | 0.0 | 132.3 |
| random | random | 20 | 100% | 84%-100% | 0 | 20 | 0 | 0 | 30.0 | 0.4 | 0.0 | 0.0 |
