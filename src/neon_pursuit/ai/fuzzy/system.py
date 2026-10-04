"""A small, dependency-free Mamdani fuzzy inference engine.

Pipeline for one evaluation:

1. **Fuzzification** — each crisp input is mapped to membership degrees of its
   linguistic terms (e.g. ``danger = 3`` → ``{critical: 0, near: 1, safe: 0}``).
2. **Rule evaluation** — each rule's antecedent strength is the ``min`` (AND)
   or ``max`` (OR) of its clause memberships, scaled by the rule weight.
3. **Implication & aggregation** — each consequent term is clipped at its rule
   strength; all clipped sets are combined with ``max``.
4. **Defuzzification** — the centroid (centre of gravity) of the aggregated
   set gives the crisp output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True, frozen=True)
class Trapezoid:
    """Trapezoidal membership function; a triangle when ``b == c``.

    Shoulders are expressed with ``a == b`` (left) or ``c == d`` (right).
    """

    a: float
    b: float
    c: float
    d: float

    def __call__(self, x: float) -> float:
        if x < self.a or x > self.d:
            return 0.0
        if self.b <= x <= self.c:
            return 1.0
        if x < self.b:
            return (x - self.a) / (self.b - self.a)
        return (self.d - x) / (self.d - self.c)


def triangle(a: float, b: float, c: float) -> Trapezoid:
    return Trapezoid(a, b, b, c)


@dataclass(slots=True, frozen=True)
class LinguisticVariable:
    name: str
    low: float
    high: float
    terms: Mapping[str, Trapezoid]
    unit: str = ""

    def fuzzify(self, value: float) -> dict[str, float]:
        x = min(self.high, max(self.low, value))
        return {label: mf(x) for label, mf in self.terms.items()}


@dataclass(slots=True, frozen=True)
class Clause:
    variable: str
    term: str
    negate: bool = False

    def __str__(self) -> str:
        return f"{self.variable} is {'not ' if self.negate else ''}{self.term}"


@dataclass(slots=True, frozen=True)
class Rule:
    rule_id: str
    clauses: tuple[Clause, ...]
    consequent: str
    operator: Literal["and", "or"] = "and"
    weight: float = 1.0

    def text(self, output_name: str) -> str:
        joiner = f" {self.operator.upper()} "
        antecedent = joiner.join(str(c) for c in self.clauses)
        return f"IF {antecedent} THEN {output_name} is {self.consequent}"


def when(*clauses: tuple[str, str], then: str, rule_id: str, weight: float = 1.0) -> Rule:
    """Convenience constructor: ``when(("danger", "near"), ("space", "open"), then="fair")``."""
    return Rule(rule_id, tuple(Clause(v, t) for v, t in clauses), then, "and", weight)


@dataclass(slots=True)
class InferenceResult:
    output: float
    fuzzified: dict[str, dict[str, float]]
    rule_strengths: list[tuple[Rule, float]]
    curve: list[float] = field(default_factory=list)


class FuzzySystem:
    """Mamdani inference with min-implication, max-aggregation and centroid defuzzification."""

    def __init__(
        self,
        inputs: Sequence[LinguisticVariable],
        output: LinguisticVariable,
        rules: Sequence[Rule],
        resolution: int = 101,
    ) -> None:
        self.inputs = {v.name: v for v in inputs}
        self.output = output
        self.rules = list(rules)
        self.resolution = resolution
        step = (output.high - output.low) / (resolution - 1)
        self._xs = [output.low + i * step for i in range(resolution)]
        # Pre-sample consequent membership functions once.
        self._samples = {label: [mf(x) for x in self._xs] for label, mf in output.terms.items()}
        self._validate()

    def _validate(self) -> None:
        for rule in self.rules:
            if rule.consequent not in self.output.terms:
                raise ValueError(f"Rule {rule.rule_id}: unknown output term {rule.consequent!r}")
            for clause in rule.clauses:
                var = self.inputs.get(clause.variable)
                if var is None:
                    raise ValueError(f"Rule {rule.rule_id}: unknown variable {clause.variable!r}")
                if clause.term not in var.terms:
                    raise ValueError(f"Rule {rule.rule_id}: unknown term {clause.term!r}")

    def evaluate(self, values: Mapping[str, float], keep_curve: bool = False) -> InferenceResult:
        fuzzified = {name: var.fuzzify(values[name]) for name, var in self.inputs.items()}

        strengths: list[tuple[Rule, float]] = []
        clip: dict[str, float] = dict.fromkeys(self.output.terms, 0.0)
        for rule in self.rules:
            degrees = [
                1.0 - fuzzified[c.variable][c.term] if c.negate else fuzzified[c.variable][c.term]
                for c in rule.clauses
            ]
            s = (min(degrees) if rule.operator == "and" else max(degrees)) * rule.weight
            strengths.append((rule, s))
            clip[rule.consequent] = max(clip[rule.consequent], s)

        curve = [0.0] * self.resolution
        for label, level in clip.items():
            if level <= 0.0:
                continue
            for i, mu in enumerate(self._samples[label]):
                v = mu if mu < level else level
                curve[i] = max(curve[i], v)

        area = sum(curve)
        if area <= 1e-12:
            crisp = (self.output.low + self.output.high) / 2.0
        else:
            crisp = sum(x * mu for x, mu in zip(self._xs, curve, strict=True)) / area
        return InferenceResult(crisp, fuzzified, strengths, curve if keep_curve else [])

    def best_term(self, value: float) -> str:
        memberships = self.output.fuzzify(value)
        return max(memberships, key=lambda k: memberships[k])
