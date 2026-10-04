"""Difficulty presets shared by the GUI and the CLI."""

from __future__ import annotations

from enum import StrEnum

from .ai import AgentSettings, FuzzyParams, MctsParams, MinimaxParams


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


def settings_for(difficulty: Difficulty) -> AgentSettings:
    """Search budgets per difficulty. Fuzzy/Greedy/Random are unaffected by budget."""
    match difficulty:
        case Difficulty.EASY:
            return AgentSettings(
                mcts=MctsParams(iterations=80, time_limit_ms=400),
                minimax=MinimaxParams(max_depth=3, time_limit_ms=250),
                fuzzy=FuzzyParams(jitter=0.06),
            )
        case Difficulty.NORMAL:
            return AgentSettings(
                mcts=MctsParams(iterations=250, time_limit_ms=900),
                minimax=MinimaxParams(max_depth=6, time_limit_ms=500),
                fuzzy=FuzzyParams(),
            )
        case Difficulty.HARD:
            return AgentSettings(
                mcts=MctsParams(iterations=900, time_limit_ms=2500),
                minimax=MinimaxParams(max_depth=10, time_limit_ms=1500),
                fuzzy=FuzzyParams(jitter=0.0),
            )
    raise ValueError(difficulty)  # pragma: no cover
