"""Agent interface and the *insight* objects agents expose to the UI.

Every agent returns a :class:`Decision`: the chosen action plus an
:class:`Insight` that explains *why* — MCTS visit counts, fuzzy rule
activations, minimax scores. The match screen renders these live in the
"brain" panels, which turns the game into a teaching tool.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

from ..engine import Action, GameMap, GameState, MatchConfig, Role


class AlgorithmId(StrEnum):
    MCTS = "mcts"
    FUZZY = "fuzzy"
    MINIMAX = "minimax"
    GREEDY = "greedy"
    RANDOM = "random"


@dataclass(slots=True)
class ActionScore:
    action: Action
    #: Normalised desirability in [0, 1] from the deciding agent's point of view.
    score: float
    #: MCTS visit count (when applicable).
    visits: int | None = None


@dataclass(slots=True)
class FuzzyInput:
    name: str
    value: float
    low: float
    high: float
    memberships: list[tuple[str, float]]


@dataclass(slots=True)
class FuzzyRuleFiring:
    rule_id: str
    text: str
    strength: float


@dataclass(slots=True)
class Insight:
    """Explanation of a decision. Algorithm-specific fields are optional."""

    algorithm: AlgorithmId | None
    summary: str
    actions: list[ActionScore] = field(default_factory=list)
    #: Cells the agent expects to visit next (its predicted own path).
    plan: list[int] = field(default_factory=list)
    #: Key/value statistics shown in the brain panel ("Iterations": "1200", ...).
    stats: list[tuple[str, str]] = field(default_factory=list)
    # Fuzzy-logic specifics.
    fuzzy_inputs: list[FuzzyInput] = field(default_factory=list)
    fuzzy_rules: list[FuzzyRuleFiring] = field(default_factory=list)
    fuzzy_output: float | None = None
    #: Sampled aggregated output membership curve (for the defuzzification plot).
    fuzzy_curve: list[float] = field(default_factory=list)


@dataclass(slots=True)
class Decision:
    action: Action
    elapsed_ms: float
    insight: Insight


class Agent(ABC):
    """Base class for all controllers. Subclasses implement :meth:`choose`."""

    algorithm: AlgorithmId

    def __init__(self, role: Role, game_map: GameMap, config: MatchConfig, seed: int = 0) -> None:
        self.role = role
        self.map = game_map
        self.config = config
        self.seed = seed

    def decide(self, state: GameState) -> Decision:
        if state.to_move is not self.role:
            raise ValueError(
                f"{self.role.value} agent asked to move on {state.to_move.value}'s turn"
            )
        start = time.perf_counter()
        action, insight = self.choose(state)
        elapsed = (time.perf_counter() - start) * 1000.0
        return Decision(action=action, elapsed_ms=elapsed, insight=insight)

    @abstractmethod
    def choose(self, state: GameState) -> tuple[Action, Insight]:
        """Return the action to play and an explanation of the choice."""
