<div align="center">

# NEON PURSUIT

**Hunter vs Survivor: an adversarial AI arena where Monte Carlo Tree Search, Fuzzy Logic and Minimax fight it out, and you can watch them think.**

[![CI](https://github.com/k-i-mahi/AI-Project/actions/workflows/ci.yml/badge.svg)](https://github.com/k-i-mahi/AI-Project/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-3776AB?logo=python&logoColor=white)
![pygame-ce](https://img.shields.io/badge/pygame--ce-2.5-29E8FF)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![mypy](https://img.shields.io/badge/mypy-strict-2A6DB2)
[![License: MIT](https://img.shields.io/badge/license-MIT-FFD640.svg)](LICENSE)

<img src="docs/images/match_mcts_vs_fuzzy.png" alt="MCTS Hunter vs Fuzzy Logic Survivor, with live AI brain panels" width="100%">

</div>

---

## Contents

- [About](#about)
- [Features](#features)
- [Quick start](#quick-start)
- [How to play](#how-to-play)
- [The AI](#the-ai)
- [Benchmark results](#benchmark-results)
- [Command line](#command-line)
- [Architecture](#architecture)
- [Development](#development)
- [Roadmap](#roadmap)
- [License](#license)

## About

Neon Pursuit is a turn-based **pursuit–evasion game** built as an Artificial Intelligence
course project. Two agents share a procedurally generated neon arena:

- the **Hunter** 🔺 tries to catch the Survivor, or to guard the energy cores until it starves;
- the **Survivor** 🔵 has to keep collecting cores to stay alive, without ever stepping into
  the Hunter's reach.

Each side can be driven by a different AI technique: **Monte Carlo Tree Search**, a
**Mamdani Fuzzy Logic controller**, **Minimax with α-β pruning**, or Greedy and Random
baselines. You can also take control of either side yourself. Every decision is explained live
on screen: you see MCTS visit counts, fuzzy rules firing and the defuzzified output, and the
minimax search depth.

## Features

- 🧠 **Five AI algorithms, any role.** Each one can play Hunter *or* Survivor through a single
  `Agent` interface.
- 🔍 **Explainable AI panels.** Live telemetry for every decision: per-action scores,
  fuzzification bars, rule activations, the centroid plot and the predicted path.
- 🎮 **Play against the AI.** Keyboard or mouse controls, with the legal moves highlighted.
- 🗺️ **Fair, reproducible arenas.** Seeded maps are mirrored left to right and checked for
  connectivity; every match can be replayed exactly from its seed.
- 🧪 **Benchmark Lab.** Run AI-vs-AI tournaments in parallel processes and get a win-rate
  heatmap, plus CSV, JSON and Markdown export.
- ✨ **Polished visuals.** Glow and particle effects, motion trails, screen shake, and Voronoi
  territory and hunter-reach overlays. Runs at 60 FPS and scales to any window size or full
  screen.
- ✅ **Engineered like production code.** Strict mypy, ruff, a pytest suite, pre-commit, and CI
  on 3 operating systems × 3 Python versions.

<table>
<tr>
<td width="50%"><img src="docs/images/menu.png" alt="Main menu with live demo"></td>
<td width="50%"><img src="docs/images/setup.png" alt="Custom match setup"></td>
</tr>
<tr>
<td><img src="docs/images/match_overlays.png" alt="Territory overlay and fuzzy brain panel"></td>
<td><img src="docs/images/benchmark.png" alt="Benchmark Lab heatmap"></td>
</tr>
</table>

## Quick start

Requires **Python 3.11+**.

```bash
git clone https://github.com/k-i-mahi/AI-Project.git
cd AI-Project
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e .
neon-pursuit            # or: python -m neon_pursuit
```

From the menu choose **Watch AI Duel** (MCTS vs Fuzzy Logic), **Play as Survivor**,
**Play as Hunter**, **Custom Match**, or **Benchmark Lab**.

## How to play

| | Hunter 🔺 | Survivor 🔵 |
|---|---|---|
| **Goal** | Capture the Survivor, or starve it | Collect 8 cores, or last 160 rounds |
| **Burst move** | *Pounce*: 2 tiles, 9-round cooldown | *Dash*: 2 tiles, 7-round cooldown, costs 3 energy |
| **Pressure** | Can win by guarding cores | Loses 1 energy per round; each core gives +15 |

The Survivor moves first, then the Hunter; together these make one round. Full rules:
[docs/GAME_RULES.md](docs/GAME_RULES.md).

| Keys | Action |
|---|---|
| `WASD` / arrow keys | move one tile (when you control a side) |
| `Shift` + direction | Dash / Pounce |
| `Space` | wait |
| Click a highlighted ring | move there |
| `P` · `N` | pause · step one move |
| `L` · `T` · `H` | toggle AI-plan · territory · hunter-reach overlays |
| `+` / `-` | simulation speed (0.5× – 8×) |
| `R` · `M` · `Esc` · `F11` | rematch · new map · menu · fullscreen |

## The AI

| Algorithm | Family | How it decides |
|---|---|---|
| **Monte Carlo Tree Search** | Stochastic search | UCT selection, ε-greedy rollouts with a heuristic cut-off, plays the most-visited move |
| **Fuzzy Logic Controller** | Soft computing | 4 fuzzified inputs, 11–13 Mamdani rules, centroid defuzzification; scores every candidate move |
| **Minimax + α-β** | Adversarial search | Negamax, iterative deepening under a time budget, move ordering, transposition table with bound flags |
| **Greedy Pathfinder** | Baseline | One-ply lookahead on precomputed BFS distances |
| **Random Walker** | Baseline | Uniformly random legal moves |

Some details worth knowing:

- **The fuzzy controllers use fuzzy *partitions*.** With Mamdani + centroid, a single active
  output term always defuzzifies to its own centre, which made the first version blind to
  distance. With overlapping inputs whose memberships sum to 1 everywhere (a unit test checks
  this), every step closer to a goal changes the output.
- **Contested-core awareness.** The Survivor's notion of "nearest core" adds a penalty for
  cores the Hunter would reach first. The penalty shrinks as the Survivor gets hungrier, so a
  starving Survivor takes the gamble.
- **One tree, two players.** MCTS backs up `v` for the Survivor and `1 − v` for the Hunter,
  so a single tree handles this alternating zero-sum game.

The full write-up, with formulas and rule bases, is in [docs/ALGORITHMS.md](docs/ALGORITHMS.md).

## Benchmark results

500 matches: 5 Hunter algorithms × 5 Survivor algorithms × 20 seeded maps (seeds 1000–1019), **Normal** difficulty (MCTS 250 iterations, Minimax depth ≤ 6 / 0.5 s), default rules.
Hunter win rate (rows: Hunter, columns: Survivor):

| Hunter ↓ · Survivor → | MCTS | Fuzzy | Minimax | Greedy | Random |
|---|---:|---:|---:|---:|---:|
| **MCTS** | 70% | 95% | 85% | 75% | 100% |
| **Fuzzy** | 20% | 55% | 30% | 40% | 100% |
| **Minimax** | 100% | 100% | 100% | 100% | 100% |
| **Greedy** | 0% | 20% | 10% | 5% | 100% |
| **Random** | 20% | 0% | 30% | 0% | 100% |

| Algorithm | Win rate as Hunter | Win rate as Survivor | Overall |
|---|---:|---:|---:|
| Minimax | 100% | 49% | 74% |
| MCTS | 85% | 58% | 72% |
| Fuzzy | 49% | 46% | 48% |
| Greedy | 27% | 56% | 42% |
| Random | 30% | 0% | 15% |

**Takeaways:** Minimax is a flawless Hunter. MCTS is the strongest Survivor and the best
all-rounder. The Fuzzy Logic controller beats both baselines while deciding in about 1 ms
(no search). Analysis and the full per-matchup table are in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Command line

```bash
neon-pursuit                                        # open the game
neon-pursuit play --hunter mcts --survivor human    # jump straight into a match
neon-pursuit play --hunter human --survivor fuzzy --difficulty hard --seed 7
neon-pursuit simulate --hunter mcts --survivor fuzzy --seed 42 --render   # terminal only
neon-pursuit benchmark --games 20 --difficulty normal --out results       # tournament + export
```

Algorithms: `mcts`, `fuzzy`, `minimax`, `greedy`, `random` (plus `human` for `play`).
Difficulties: `easy`, `normal`, `hard`. Run `neon-pursuit <command> --help` for every option.

## Architecture

```
src/neon_pursuit/
├── engine/      pure, deterministic rules · map generation · board analysis (no pygame)
├── ai/          MCTS · minimax · fuzzy/ (engine + controllers) · baselines · heuristics
├── benchmark/   parallel tournaments · CSV/JSON/Markdown reports
├── game/        pygame-ce UI · scenes · renderer · brain panels · AI worker process
├── presets.py   Easy / Normal / Hard search budgets
└── cli.py       `neon-pursuit` entry point
```

The engine and AI never import pygame, so they are unit-tested, benchmarked headlessly and
run in a separate worker process. The UI stays at 60 FPS while an agent thinks. Diagrams and
design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

```bash
pip install -e ".[dev]"
pre-commit install

pytest --cov                            # tests + coverage
ruff check src tests scripts            # lint
ruff format src tests scripts           # format
mypy                                    # strict type checking
python scripts/capture_screenshots.py   # re-render docs/images headlessly
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, including how to add a new algorithm.

## Roadmap

- [ ] Partial observability (fog of war) with belief-state agents
- [ ] Reinforcement-learning agent (tabular Q-learning / DQN) trained against the existing ones
- [ ] Genetic-algorithm tuning of the fuzzy membership functions
- [ ] Replay files and a timeline scrubber
- [ ] Sound design and a packaged Windows executable

## License

Released under the [MIT License](LICENSE).
Bundled fonts are licensed under the SIL Open Font License
([Orbitron](src/neon_pursuit/assets/fonts/OFL-Orbitron.txt),
[Rajdhani](src/neon_pursuit/assets/fonts/OFL-Rajdhani.txt),
[JetBrains Mono](src/neon_pursuit/assets/fonts/OFL-JetBrainsMono.txt)).
