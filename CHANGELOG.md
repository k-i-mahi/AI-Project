# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
