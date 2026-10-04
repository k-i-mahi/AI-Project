"""Fuzzy-logic inference engine and game controllers."""

from .controllers import FuzzyAgent, FuzzyParams, hunter_system, survivor_system
from .system import (
    Clause,
    FuzzySystem,
    InferenceResult,
    LinguisticVariable,
    Rule,
    Trapezoid,
    triangle,
    when,
)

__all__ = [
    "Clause",
    "FuzzyAgent",
    "FuzzyParams",
    "FuzzySystem",
    "InferenceResult",
    "LinguisticVariable",
    "Rule",
    "Trapezoid",
    "hunter_system",
    "survivor_system",
    "triangle",
    "when",
]
