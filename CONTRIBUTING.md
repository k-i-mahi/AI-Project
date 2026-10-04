# Contributing

Thanks for your interest in improving Neon Pursuit!

## Development setup

```bash
git clone https://github.com/k-i-mahi/AI-Project.git
cd AI-Project
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Quality gates

Every pull request must pass the same checks as CI:

```bash
ruff check src tests scripts          # lint
ruff format --check src tests scripts # formatting
mypy                                  # strict type checking
pytest --cov                          # tests + coverage
```

## Guidelines

- **Keep the engine pure.** `engine/`, `ai/` and `benchmark/` must not import pygame.
- **Stay deterministic.** Never use the global `random` module or wall-clock time in game
  logic. Create seeded RNGs with `engine.rng.make_rng(seed, salt)`.
- **Explain decisions.** New agents should return a meaningful `Insight` so the brain
  panels can visualise them. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#adding-a-new-algorithm).
- **Benchmark changes to AI behaviour.** Include before/after numbers from
  `neon-pursuit benchmark` in the PR description.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:`, `chore:`).

## Reporting issues

Please include the algorithms, difficulty and **map seed**. Matches are reproducible, so
those three usually pin down a bug exactly.
