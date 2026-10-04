"""Headless match execution and parallel tournaments."""

from __future__ import annotations

import dataclasses
import math
import os
import statistics
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field

from ..ai import AgentSettings, AlgorithmId, create_agent
from ..engine import MatchConfig, Role, Status, WinReason, apply_action, generate_map, initial_state
from ..engine.rng import derive_seed


@dataclass(slots=True, frozen=True)
class MatchSpec:
    hunter: AlgorithmId
    survivor: AlgorithmId
    config: MatchConfig
    settings: AgentSettings = field(default_factory=AgentSettings)


@dataclass(slots=True, frozen=True)
class MatchResult:
    hunter: str
    survivor: str
    seed: int
    winner: str
    reason: str
    rounds: int
    cores: int
    hunter_ms: float
    survivor_ms: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def play_match(spec: MatchSpec) -> MatchResult:
    """Play one complete match without any rendering."""
    cfg = spec.config
    game_map = generate_map(cfg)
    agents = {
        Role.HUNTER: create_agent(
            spec.hunter, Role.HUNTER, game_map, cfg, derive_seed(cfg.seed, 11), spec.settings
        ),
        Role.SURVIVOR: create_agent(
            spec.survivor, Role.SURVIVOR, game_map, cfg, derive_seed(cfg.seed, 22), spec.settings
        ),
    }
    think: dict[Role, list[float]] = {Role.HUNTER: [], Role.SURVIVOR: []}
    state = initial_state(game_map, cfg)
    while not state.is_terminal:
        decision = agents[state.to_move].decide(state)
        think[state.to_move].append(decision.elapsed_ms)
        state = apply_action(game_map, cfg, state, decision.action)

    winner = Role.HUNTER if state.status is Status.HUNTER_WIN else Role.SURVIVOR
    return MatchResult(
        hunter=spec.hunter.value,
        survivor=spec.survivor.value,
        seed=cfg.seed,
        winner=winner.value,
        reason=(state.win_reason or WinReason.SURVIVED).value,
        rounds=state.round,
        cores=state.cores_collected,
        hunter_ms=statistics.fmean(think[Role.HUNTER]) if think[Role.HUNTER] else 0.0,
        survivor_ms=statistics.fmean(think[Role.SURVIVOR]) if think[Role.SURVIVOR] else 0.0,
    )


def build_specs(
    matchups: Iterable[tuple[AlgorithmId, AlgorithmId]],
    games: int,
    base_config: MatchConfig,
    settings: AgentSettings | None = None,
) -> list[MatchSpec]:
    """One spec per (matchup, game); game ``i`` uses seed ``base_seed + i`` for every matchup."""
    s = settings or AgentSettings()
    specs = []
    for hunter, survivor in matchups:
        for i in range(games):
            cfg = dataclasses.replace(base_config, seed=base_config.seed + i)
            specs.append(MatchSpec(hunter, survivor, cfg, s))
    return specs


#: Upper bound on default worker processes: each holds its own map caches, and
#: unbounded pools exhausted memory on a 16 GB machine during long runs.
MAX_DEFAULT_WORKERS = 8


def default_workers() -> int:
    """CPU count minus one, capped at :data:`MAX_DEFAULT_WORKERS`."""
    return max(1, min(MAX_DEFAULT_WORKERS, (os.cpu_count() or 2) - 1))


def run_tournament(
    specs: list[MatchSpec],
    workers: int | None = None,
    on_result: Callable[[MatchResult, int, int], None] | None = None,
) -> list[MatchResult]:
    """Run specs in parallel processes (or inline when ``workers == 1``)."""
    total = len(specs)
    results: list[MatchResult] = []
    n_workers = workers if workers is not None else default_workers()
    if n_workers <= 1:
        for spec in specs:
            result = play_match(spec)
            results.append(result)
            if on_result:
                on_result(result, len(results), total)
        return results
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        futures = [pool.submit(play_match, spec) for spec in specs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result:
                on_result(result, len(results), total)
    return results


@dataclass(slots=True)
class MatchupSummary:
    hunter: str
    survivor: str
    games: int
    hunter_wins: int
    survivor_wins: int
    captures: int
    escapes: int
    timeouts: int
    avg_rounds: float
    avg_cores: float
    hunter_ms: float
    survivor_ms: float

    @property
    def hunter_win_rate(self) -> float:
        return self.hunter_wins / self.games if self.games else 0.0

    @property
    def hunter_win_ci(self) -> tuple[float, float]:
        """95 % Wilson score interval for the Hunter win rate."""
        return wilson_interval(self.hunter_wins, self.games)


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    Unlike the normal approximation it stays inside [0, 1] and behaves well for
    small samples and extreme rates (0 % / 100 %), which benchmarks hit often.
    """
    if trials == 0:
        return (0.0, 1.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarise(results: list[MatchResult]) -> list[MatchupSummary]:
    groups: dict[tuple[str, str], list[MatchResult]] = {}
    for r in results:
        groups.setdefault((r.hunter, r.survivor), []).append(r)
    out = []
    for (hunter, survivor), rs in groups.items():
        out.append(
            MatchupSummary(
                hunter=hunter,
                survivor=survivor,
                games=len(rs),
                hunter_wins=sum(r.winner == Role.HUNTER.value for r in rs),
                survivor_wins=sum(r.winner == Role.SURVIVOR.value for r in rs),
                captures=sum(r.reason == WinReason.CAPTURED.value for r in rs),
                escapes=sum(r.reason == WinReason.CORES_COLLECTED.value for r in rs),
                timeouts=sum(r.reason == WinReason.SURVIVED.value for r in rs),
                avg_rounds=statistics.fmean(r.rounds for r in rs),
                avg_cores=statistics.fmean(r.cores for r in rs),
                hunter_ms=statistics.fmean(r.hunter_ms for r in rs),
                survivor_ms=statistics.fmean(r.survivor_ms for r in rs),
            )
        )
    return out
