"""Fuzzy genomes and the genetic-algorithm operators."""

from __future__ import annotations

import random

import pytest

from neon_pursuit.ai import AlgorithmId
from neon_pursuit.ai.fuzzy import (
    MANUAL_HUNTER,
    MANUAL_SURVIVOR,
    FuzzyGenome,
    FuzzyParams,
    genome_for,
)
from neon_pursuit.ai.fuzzy.genome import (
    HUNTER_VARIABLES,
    SURVIVOR_VARIABLES,
    partition,
)
from neon_pursuit.ai.fuzzy.tuning import TuningConfig, crossover, evaluate_population, mutate
from neon_pursuit.engine import MatchConfig, Role


@pytest.mark.parametrize(
    ("variables", "genome"),
    [(SURVIVOR_VARIABLES, MANUAL_SURVIVOR), (HUNTER_VARIABLES, MANUAL_HUNTER)],
)
def test_genome_partitions_sum_to_one(variables: dict, genome: FuzzyGenome) -> None:  # type: ignore[type-arg]
    for name, spec in variables.items():
        var = partition(name, spec, genome.points(name))
        for i in range(41):
            x = var.low + (var.high - var.low) * i / 40
            assert sum(var.fuzzify(x).values()) == pytest.approx(1.0, abs=1e-6)


def test_genome_json_round_trip() -> None:
    g = FuzzyGenome(MANUAL_SURVIVOR.breakpoints, (("S1", 0.5),))
    back = FuzzyGenome.from_json(g.to_json())
    assert back == g
    assert back.weight("S1") == 0.5
    assert back.weight("S2") == 1.0


def test_explicit_genome_overrides_profile() -> None:
    custom = FuzzyGenome(MANUAL_HUNTER.breakpoints, (("H1", 0.3),))
    assert genome_for(Role.HUNTER, FuzzyParams(hunter_genome=custom)) is custom
    assert genome_for(Role.SURVIVOR, FuzzyParams(profile="manual")) is MANUAL_SURVIVOR


@pytest.mark.parametrize("role", list(Role))
def test_mutation_and_crossover_keep_genomes_valid(role: Role) -> None:
    rng = random.Random(1)
    cfg = TuningConfig(role=role, mutation_rate=1.0, sigma=0.5)
    variables = SURVIVOR_VARIABLES if role is Role.SURVIVOR else HUNTER_VARIABLES
    base = MANUAL_SURVIVOR if role is Role.SURVIVOR else MANUAL_HUNTER
    child = crossover(mutate(base, role, rng, cfg), mutate(base, role, rng, cfg), role, rng)
    for name, (low, high, labels, _unit) in variables.items():
        pts = child.points(name)
        assert len(pts) == len(labels)
        assert list(pts) == sorted(pts)
        assert all(low <= p <= high for p in pts)
    assert all(0.05 <= w <= 1.0 for _, w in child.weights)


def test_evaluate_population_scores_in_range() -> None:
    cfg = TuningConfig(
        role=Role.SURVIVOR,
        games_per_opponent=1,
        opponents=(AlgorithmId.GREEDY, AlgorithmId.RANDOM),
        base_config=MatchConfig(max_rounds=40),
    )
    scores = evaluate_population([MANUAL_SURVIVOR, MANUAL_SURVIVOR], cfg, seed_base=3)
    assert len(scores) == 2
    assert scores[0] == scores[1]  # same genome, same seeds -> same fitness
    assert 0.0 <= scores[0] <= 1.05


def test_constraint_keeps_imminent_capture_critical() -> None:
    """The GA once learned to treat 'capture next move' as merely 'near'; forbid it."""
    var = partition("danger", SURVIVOR_VARIABLES["danger"], (0.2, 0.3, 0.4))
    assert var.fuzzify(1.0)["critical"] == 1.0
    assert sum(var.fuzzify(1.0).values()) == pytest.approx(1.0)
