# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.1.1] - 2026-10-04

### Fixed
- *How It Works* screen: content overlapped the panels and the Back button; redesigned into
  rules / algorithms / controls sections, with a UI test that fails on any overflow.
- F11 fullscreen: replaced `pygame.display.toggle_fullscreen()` (which warned and re-created
  the window on Windows) with an explicit toggle that restores the previous window size.

## [1.1.0] - 2026-10-04

A review-driven release: benchmarks showed the Minimax Hunter winning 100 % of games and the
fuzzy controller ranking below the Greedy baseline. This release fixes the causes.

### Added
- **Survivor abilities**: *Blink Dash* (the dash may leap over one wall tile) and *EMP Pulse*
  (stuns a Hunter within 3 tiles for 3 turns; 18-round cooldown, 4 energy). All agents use them.
- **Genetic-algorithm tuning** of the fuzzy controllers (`neon-pursuit tune`): evolves
  membership breakpoints and rule weights with tournament selection, crossover, mutation,
  elitism, common random numbers and held-out final selection. Tuned genomes ship in
  `tuned.json`; `--fuzzy-profile manual|tuned` compares them.
- **Algorithm picker** for every mode: Watch AI Duel, Play as Survivor and Play as Hunter.
- **Random, fair spawns** derived from the seed; every new game uses a random seed.
- **95 % Wilson confidence intervals** in benchmark reports.
- Headless **UI smoke tests** for every screen; UI code now counts toward coverage.

### Changed
- Cores respawn inside the Survivor's territory when possible, so camping the food no longer wins.
- 10 cores to win by default (chosen from balance sweeps).
- Minimax stops on a **node budget** and MCTS on an iteration budget, so results no longer
  depend on CPU load.
- MCTS screens root moves for decisive / anti-decisive moves (fixes one-move blunders).
- Parallel jobs default to `min(8, CPUs - 1)` workers to stay within memory.

### Fixed
- A GA loophole where the tuned Survivor ignored "capture next move"; now a hard constraint.
- Setup screen and `play --cores` defaulted to 8 cores while the engine default is 10.
- Added the `py.typed` marker promised by the *Typing :: Typed* classifier; package-data tests.

## [1.0.0] - 2026-10-04

### Added
- Deterministic pursuit–evasion engine: seeded, mirrored, connectivity-checked arenas;
  energy and core economy; Dash / Pounce burst moves; event stream for the UI.
- AI agents that can play either role: Monte Carlo Tree Search (UCT), Mamdani Fuzzy Logic
  controller, Minimax with alpha-beta / iterative deepening / transposition table,
  Greedy pathfinder and Random baselines.
- Explainable decisions: every agent returns an `Insight` rendered live in "brain" panels.
- Pygame-ce front-end: neon renderer with glow, particles, trails and screen shake;
  territory, hunter-reach and plan overlays; human play; resolution-independent scaling.
- Benchmark Lab (in-game heatmap) and `neon-pursuit benchmark` CLI with CSV / JSON / Markdown export.
- Easy / Normal / Hard difficulty presets.
- Test suite, strict mypy, ruff, pre-commit, GitHub Actions CI (3 OSes × 3 Python versions) and release workflow.
