"""Fuzzy-logic inference engine and game controllers."""

from .controllers import FuzzyAgent, FuzzyParams, genome_for, hunter_system, survivor_system
from .genome import MANUAL_HUNTER, MANUAL_SURVIVOR, FuzzyGenome
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
    "MANUAL_HUNTER",
    "MANUAL_SURVIVOR",
    "Clause",
    "FuzzyAgent",
    "FuzzyGenome",
    "FuzzyParams",
    "FuzzySystem",
    "InferenceResult",
    "LinguisticVariable",
    "Rule",
    "Trapezoid",
    "genome_for",
    "hunter_system",
    "survivor_system",
    "triangle",
    "when",
]
