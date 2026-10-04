"""Parameterised fuzzy rule bases.

Each rule base is described by a :class:`FuzzyGenome`:

* **breakpoints**: for every input variable, the points ``a <= b (<= c)`` that
  define a *fuzzy partition* (adjacent terms overlap and sum to 1);
* **weights**: one weight in ``[0, 1]`` per rule.

The rule *structure* (which clauses imply which consequent) is fixed and
human-written; only the shapes and weights are tunable. That keeps a tuned
controller explainable while letting an optimiser such as the genetic
algorithm in :mod:`.tuning` fit it to the game.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

from .system import Clause, FuzzySystem, LinguisticVariable, Rule, Trapezoid, triangle

#: name -> (low, high, term labels, unit)
VariableSpec = tuple[float, float, tuple[str, ...], str]

DESIRABILITY = LinguisticVariable(
    "desirability",
    0.0,
    1.0,
    {
        "avoid": Trapezoid(0.0, 0.0, 0.1, 0.25),
        "poor": triangle(0.1, 0.3, 0.5),
        "fair": triangle(0.35, 0.5, 0.65),
        "good": triangle(0.5, 0.7, 0.9),
        "excellent": Trapezoid(0.75, 0.9, 1.0, 1.0),
    },
)

SPACE: VariableSpec = (0.0, 0.6, ("cornered", "limited", "open"), "of map")

SURVIVOR_VARIABLES: dict[str, VariableSpec] = {
    "danger": (0.0, 12.0, ("critical", "near", "safe"), "moves"),
    "core": (0.0, 30.0, ("close", "mid", "far"), "tiles"),
    "space": SPACE,
    "energy": (0.0, 1.0, ("low", "medium", "high"), "of max"),
}

HUNTER_VARIABLES: dict[str, VariableSpec] = {
    "gap": (0.0, 24.0, ("striking", "close", "distant"), "moves"),
    "squeeze": (*SPACE[:3], "prey space"),
    "intercept": (-12.0, 12.0, ("ahead", "level", "behind"), "tiles"),
    "prey_energy": (0.0, 1.0, ("starving", "fed"), "of max"),
}

#: (rule id, ((variable, term), ...), consequent)
RuleSpec = tuple[str, tuple[tuple[str, str], ...], str]

SURVIVOR_RULES: tuple[RuleSpec, ...] = (
    ("S1", (("danger", "critical"),), "avoid"),
    ("S2", (("danger", "near"), ("space", "cornered")), "avoid"),
    ("S3", (("danger", "near"), ("core", "close")), "good"),
    ("S4", (("danger", "near"), ("core", "mid")), "fair"),
    ("S5", (("danger", "near"), ("core", "far")), "poor"),
    ("S6", (("danger", "near"), ("space", "open")), "fair"),
    ("S7", (("danger", "safe"), ("core", "close")), "excellent"),
    ("S8", (("danger", "safe"), ("core", "mid")), "good"),
    ("S9", (("danger", "safe"), ("core", "far")), "fair"),
    ("S10", (("danger", "safe"), ("space", "cornered")), "poor"),
    ("S11", (("energy", "low"), ("core", "close")), "excellent"),
    ("S12", (("energy", "low"), ("core", "mid")), "fair"),
    ("S13", (("energy", "low"), ("core", "far")), "avoid"),
)

HUNTER_RULES: tuple[RuleSpec, ...] = (
    ("H1", (("gap", "striking"),), "excellent"),
    ("H2", (("gap", "close"), ("squeeze", "cornered")), "excellent"),
    ("H3", (("gap", "close"), ("squeeze", "limited")), "good"),
    ("H4", (("gap", "close"), ("squeeze", "open")), "fair"),
    ("H5", (("gap", "distant"),), "poor"),
    ("H6", (("intercept", "ahead"),), "good"),
    ("H7", (("intercept", "behind"), ("gap", "distant")), "avoid"),
    ("H8", (("squeeze", "cornered"),), "good"),
    ("H9", (("prey_energy", "starving"), ("intercept", "ahead")), "excellent"),
    ("H10", (("prey_energy", "fed"), ("gap", "close")), "good"),
    ("H11", (("squeeze", "open"), ("gap", "distant")), "poor"),
)


@dataclass(frozen=True, slots=True)
class FuzzyGenome:
    """Tunable parameters of one rule base (see module docstring)."""

    breakpoints: tuple[tuple[str, tuple[float, ...]], ...]
    weights: tuple[tuple[str, float], ...] = field(default=())

    def points(self, variable: str) -> tuple[float, ...]:
        return dict(self.breakpoints)[variable]

    def weight(self, rule_id: str) -> float:
        return dict(self.weights).get(rule_id, 1.0)

    def to_json(self) -> dict[str, object]:
        return {
            "breakpoints": {k: list(v) for k, v in self.breakpoints},
            "weights": dict(self.weights),
        }

    @staticmethod
    def from_json(data: dict[str, object]) -> FuzzyGenome:
        bps = data["breakpoints"]
        ws = data.get("weights", {})
        assert isinstance(bps, dict) and isinstance(ws, dict)
        return FuzzyGenome(
            breakpoints=tuple((str(k), tuple(float(x) for x in v)) for k, v in bps.items()),
            weights=tuple((str(k), float(v)) for k, v in ws.items()),
        )


MANUAL_SURVIVOR = FuzzyGenome(
    breakpoints=(
        ("danger", (1.0, 2.0, 4.0)),
        ("core", (0.0, 10.0, 30.0)),
        ("space", (0.03, 0.12, 0.3)),
        ("energy", (0.15, 0.5, 0.85)),
    ),
)

MANUAL_HUNTER = FuzzyGenome(
    breakpoints=(
        ("gap", (0.0, 3.0, 10.0)),
        ("squeeze", (0.03, 0.12, 0.3)),
        ("intercept", (-6.0, 0.0, 6.0)),
        ("prey_energy", (0.2, 0.5)),
    ),
)


#: Domain-knowledge constraints the optimiser may not violate: the *first*
#: breakpoint of these variables has a lower bound. ``danger <= 1`` means the
#: Hunter can capture on its next move, which must always be fully "critical".
MIN_FIRST_BREAKPOINT: dict[str, float] = {"danger": 1.0}


def normalize_points(name: str, spec: VariableSpec, points: Sequence[float]) -> tuple[float, ...]:
    """Sort, clamp to the universe, apply constraints and keep a minimum spacing.

    The spacing (1 % of the range) prevents degenerate, overlapping terms so the
    result is always a valid Ruspini partition.
    """
    low, high, _labels, _unit = spec
    eps = 0.01 * (high - low)
    pts = sorted(min(high, max(low, p)) for p in points)
    pts[0] = max(pts[0], MIN_FIRST_BREAKPOINT.get(name, low))
    for i in range(1, len(pts)):
        pts[i] = max(pts[i], pts[i - 1] + eps)
    pts[-1] = min(pts[-1], high)
    for i in range(len(pts) - 2, -1, -1):
        pts[i] = min(pts[i], pts[i + 1] - eps)
    return tuple(round(p, 4) for p in pts)


def partition(name: str, spec: VariableSpec, points: Sequence[float]) -> LinguisticVariable:
    """Build a Ruspini partition from breakpoints (2 or 3 terms)."""
    low, high, labels, unit = spec
    pts = normalize_points(name, spec, points)
    if len(labels) == 2:
        a, b = pts
        terms = {labels[0]: Trapezoid(low, low, a, b), labels[1]: Trapezoid(a, b, high, high)}
    else:
        a, b, c = pts
        terms = {
            labels[0]: Trapezoid(low, low, a, b),
            labels[1]: triangle(a, b, c),
            labels[2]: Trapezoid(b, c, high, high),
        }
    return LinguisticVariable(name, low, high, terms, unit)


def build_system(
    variables: dict[str, VariableSpec], rules: tuple[RuleSpec, ...], genome: FuzzyGenome
) -> FuzzySystem:
    inputs = [partition(name, spec, genome.points(name)) for name, spec in variables.items()]
    built = [
        Rule(
            rule_id,
            tuple(Clause(v, t) for v, t in clauses),
            consequent,
            "and",
            genome.weight(rule_id),
        )
        for rule_id, clauses, consequent in rules
    ]
    return FuzzySystem(inputs, DESIRABILITY, built)


@cache
def tuned_genomes() -> dict[str, FuzzyGenome]:
    """Genomes produced by the genetic algorithm (``tuned.json``), if present."""
    try:
        raw = resources.files("neon_pursuit.ai.fuzzy").joinpath("tuned.json").read_text("utf-8")
    except (FileNotFoundError, OSError):
        return {}
    data = json.loads(raw)
    return {role: FuzzyGenome.from_json(g) for role, g in data.get("genomes", {}).items()}
