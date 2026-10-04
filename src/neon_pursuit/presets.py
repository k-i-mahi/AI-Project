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
                mcts=MctsParams(iterations=80, time_limit_ms=5_000),
                minimax=MinimaxParams(max_depth=4, node_budget=1_500),
                fuzzy=FuzzyParams(jitter=0.06),
            )
        case Difficulty.NORMAL:
            return AgentSettings(
                mcts=MctsParams(iterations=250, time_limit_ms=5_000),
                minimax=MinimaxParams(max_depth=8, node_budget=6_000),
                fuzzy=FuzzyParams(),
            )
        case Difficulty.HARD:
            return AgentSettings(
                mcts=MctsParams(iterations=900, time_limit_ms=10_000),
                minimax=MinimaxParams(max_depth=12, node_budget=20_000),
                fuzzy=FuzzyParams(jitter=0.0),
            )
    raise ValueError(difficulty)  # pragma: no cover
