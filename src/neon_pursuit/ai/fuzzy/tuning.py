"""Genetic-algorithm tuning of the fuzzy controllers.

The rule *structure* stays hand-written; the GA evolves the membership-function
breakpoints and rule weights of one role's :class:`FuzzyGenome`.

* **Representation**: sorted breakpoints per input variable + one weight per rule.
* **Fitness**: win rate against a fixed panel of opponents (other algorithms),
  plus a small tie-breaker (cores collected for the Survivor, speed of victory
  for the Hunter). Every individual in a generation plays the *same* seeds
  (common random numbers), so differences come from the genome, not luck.
* **Selection**: tournament selection (k = 3) with elitism.
* **Variation**: uniform crossover per variable/rule, then Gaussian mutation
  scaled to each variable's range.

Matches run in parallel worker processes.
"""

from __future__ import annotations

import dataclasses
import os
import random
import statistics
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

from ...benchmark.runner import MatchSpec, play_match
from ...engine import MatchConfig, Role
from ...presets import Difficulty, settings_for
from ..base import AlgorithmId
from .controllers import FuzzyParams
from .genome import (
    HUNTER_RULES,
    HUNTER_VARIABLES,
    MANUAL_HUNTER,
    MANUAL_SURVIVOR,
    SURVIVOR_RULES,
    SURVIVOR_VARIABLES,
    FuzzyGenome,
    RuleSpec,
    VariableSpec,
    normalize_points,
)

DEFAULT_OPPONENTS: tuple[AlgorithmId, ...] = (
    AlgorithmId.GREEDY,
    AlgorithmId.FUZZY,
    AlgorithmId.MCTS,
    AlgorithmId.MINIMAX,
)


@dataclass(slots=True)
class TuningConfig:
    role: Role
    population: int = 16
    generations: int = 10
    games_per_opponent: int = 4
    opponents: tuple[AlgorithmId, ...] = DEFAULT_OPPONENTS
    #: Mutation step as a fraction of each variable's range.
    sigma: float = 0.08
    weight_sigma: float = 0.15
    mutation_rate: float = 0.35
    elite: int = 2
    tournament: int = 3
    seed: int = 7
    workers: int | None = None
    base_config: MatchConfig = field(default_factory=MatchConfig)


@dataclass(slots=True)
class GenerationStats:
    generation: int
    best: float
    mean: float
    best_genome: FuzzyGenome


def _spec_for(role: Role) -> tuple[dict[str, VariableSpec], tuple[RuleSpec, ...], FuzzyGenome]:
    if role is Role.SURVIVOR:
        return SURVIVOR_VARIABLES, SURVIVOR_RULES, MANUAL_SURVIVOR
    return HUNTER_VARIABLES, HUNTER_RULES, MANUAL_HUNTER


def mutate(genome: FuzzyGenome, role: Role, rng: random.Random, cfg: TuningConfig) -> FuzzyGenome:
    variables, rules, _ = _spec_for(role)
    bps = []
    for name, (low, high, _labels, _unit) in variables.items():
        span = high - low
        pts = [
            p + rng.gauss(0.0, cfg.sigma * span) if rng.random() < cfg.mutation_rate else p
            for p in genome.points(name)
        ]
        bps.append((name, normalize_points(name, variables[name], pts)))
    weights = []
    for rule_id, _clauses, _cons in rules:
        w = genome.weight(rule_id)
        if rng.random() < cfg.mutation_rate:
            w += rng.gauss(0.0, cfg.weight_sigma)
        weights.append((rule_id, round(min(1.0, max(0.05, w)), 4)))
    return FuzzyGenome(tuple(bps), tuple(weights))


def crossover(a: FuzzyGenome, b: FuzzyGenome, role: Role, rng: random.Random) -> FuzzyGenome:
    variables, rules, _ = _spec_for(role)
    bps = tuple((name, (a if rng.random() < 0.5 else b).points(name)) for name in variables)
    weights = tuple(
        (rule_id, (a if rng.random() < 0.5 else b).weight(rule_id)) for rule_id, _c, _k in rules
    )
    return FuzzyGenome(bps, weights)


def _specs(
    genomes: Sequence[FuzzyGenome], cfg: TuningConfig, seed_base: int, games: int
) -> list[MatchSpec]:
    specs: list[MatchSpec] = []
    for genome in genomes:
        settings = settings_for(Difficulty.EASY)
        settings.fuzzy = FuzzyParams(
            jitter=0.01,
            profile="manual",
            survivor_genome=genome if cfg.role is Role.SURVIVOR else None,
            hunter_genome=genome if cfg.role is Role.HUNTER else None,
        )
        for opponent in cfg.opponents:
            for i in range(games):
                match_cfg = _with_seed(cfg.base_config, seed_base + i)
                if cfg.role is Role.SURVIVOR:
                    specs.append(MatchSpec(opponent, AlgorithmId.FUZZY, match_cfg, settings))
                else:
                    specs.append(MatchSpec(AlgorithmId.FUZZY, opponent, match_cfg, settings))
    return specs


def _with_seed(config: MatchConfig, seed: int) -> MatchConfig:
    return dataclasses.replace(config, seed=seed)


def evaluate_population(
    genomes: Sequence[FuzzyGenome],
    cfg: TuningConfig,
    seed_base: int,
    pool: ProcessPoolExecutor | None = None,
    games: int | None = None,
) -> list[float]:
    """Fitness of each genome (higher is better)."""
    n = games or cfg.games_per_opponent
    specs = _specs(genomes, cfg, seed_base, n)
    results = (
        list(pool.map(play_match, specs, chunksize=4)) if pool else [play_match(s) for s in specs]
    )
    per = len(cfg.opponents) * n
    scores = []
    for i in range(len(genomes)):
        chunk = results[i * per : (i + 1) * per]
        wins = sum(r.winner == cfg.role.value for r in chunk) / per
        if cfg.role is Role.SURVIVOR:
            bonus = statistics.fmean(r.cores for r in chunk) / cfg.base_config.cores_to_win
        else:
            bonus = 1.0 - statistics.fmean(r.rounds for r in chunk) / cfg.base_config.max_rounds
        scores.append(wins + 0.05 * bonus)
    return scores


def _tournament(
    population: Sequence[FuzzyGenome], scores: Sequence[float], k: int, rng: random.Random
) -> FuzzyGenome:
    contenders = rng.sample(range(len(population)), k)
    return population[max(contenders, key=lambda i: scores[i])]


def evolve(
    cfg: TuningConfig, on_generation: Callable[[GenerationStats], None] | None = None
) -> tuple[FuzzyGenome, list[GenerationStats]]:
    rng = random.Random(cfg.seed)
    _, _, manual = _spec_for(cfg.role)
    population = [manual] + [mutate(manual, cfg.role, rng, cfg) for _ in range(cfg.population - 1)]
    history: list[GenerationStats] = []
    workers = cfg.workers if cfg.workers is not None else max(1, (os.cpu_count() or 2) - 1)
    best_genome, best_score = manual, -1.0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for gen in range(cfg.generations):
            scores = evaluate_population(population, cfg, 100_000 + gen * 1_000, pool)
            ranked = sorted(zip(scores, range(len(population)), strict=True), reverse=True)
            top_score, top_index = ranked[0]
            if top_score > best_score:
                best_score, best_genome = top_score, population[top_index]
            stats = GenerationStats(gen, top_score, statistics.fmean(scores), population[top_index])
            history.append(stats)
            if on_generation:
                on_generation(stats)

            nxt = [population[i] for _, i in ranked[: cfg.elite]]
            while len(nxt) < cfg.population:
                child = crossover(
                    _tournament(population, scores, cfg.tournament, rng),
                    _tournament(population, scores, cfg.tournament, rng),
                    cfg.role,
                    rng,
                )
                nxt.append(mutate(child, cfg.role, rng, cfg))
            population = nxt

        # Final selection on fresh seeds avoids the "winner's curse" of noisy fitness.
        finalists: list[FuzzyGenome] = [manual]
        for g in [best_genome, *[h.best_genome for h in history[-4:]], *population[: cfg.elite]]:
            if g not in finalists:
                finalists.append(g)
        validation = evaluate_population(
            finalists, cfg, 900_000, pool, games=cfg.games_per_opponent * 3
        )
    winner = max(range(len(finalists)), key=lambda i: validation[i])
    return finalists[winner], history
