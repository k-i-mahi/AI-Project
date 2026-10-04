"""Minimax search with alpha-beta pruning and iterative deepening.

Formulated as *negamax*: the value of a position is always from the point of
view of the side to move, so one recursive function serves both roles.
Iterative deepening searches depth 1, 2, 3 … until the depth limit or the
*node budget* is reached; the best move from the previous depth is searched
first, which greatly improves pruning. A transposition table caches results.

The budget counts searched nodes rather than milliseconds, so a decision is
fully deterministic and does not depend on CPU load (important for fair,
reproducible benchmarks). A generous wall-clock limit remains as a safety net.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..engine import Action, GameMap, GameState, MatchConfig, Role, apply_action, legal_actions
from .base import ActionScore, Agent, AlgorithmId, Insight
from .heuristics import evaluate


@dataclass(slots=True)
class MinimaxParams:
    max_depth: int = 8
    #: Maximum nodes per decision; the deepest *completed* iteration is used.
    node_budget: int = 6_000
    #: Safety net only; normally the node budget ends the search first.
    time_limit_ms: float = 5_000.0


_EXACT, _LOWER, _UPPER = 0, 1, 2


class _SearchTimeoutError(Exception):
    pass


class MinimaxAgent(Agent):
    algorithm = AlgorithmId.MINIMAX

    def __init__(
        self,
        role: Role,
        game_map: GameMap,
        config: MatchConfig,
        seed: int = 0,
        params: MinimaxParams | None = None,
    ) -> None:
        super().__init__(role, game_map, config, seed)
        self.params = params or MinimaxParams()
        self._nodes = 0
        self._cutoffs = 0
        self._deadline = 0.0
        self._budget = 0
        self._table: dict[tuple[int, ...], tuple[int, float, int]] = {}

    def _value(self, state: GameState) -> float:
        """Heuristic in [-1, 1] from the perspective of the side to move."""
        v = 2.0 * evaluate(self.map, self.config, state) - 1.0
        return v if state.to_move is Role.SURVIVOR else -v

    def _negamax(self, state: GameState, depth: int, alpha: float, beta: float) -> float:
        self._nodes += 1
        if self._nodes > self._budget or (
            self._nodes & 255 == 0 and time.perf_counter() > self._deadline
        ):
            raise _SearchTimeoutError
        if state.is_terminal or depth == 0:
            v = self._value(state)
            # Prefer quicker wins / slower losses.
            return v * (1.0 + 0.01 * depth) if state.is_terminal else v

        key = state.key()
        cached = self._table.get(key)
        if cached is not None and cached[0] >= depth:
            _, value, flag = cached
            if flag == _EXACT:
                return value
            if flag == _LOWER:
                alpha = max(alpha, value)
            else:
                beta = min(beta, value)
            if alpha >= beta:
                return value

        alpha_orig = alpha
        best = -math.inf
        for action in self._ordered(state, legal_actions(self.map, state, self.config)):
            child = apply_action(self.map, self.config, state, action)
            score = -self._negamax(child, depth - 1, -beta, -alpha)
            best = max(best, score)
            alpha = max(alpha, best)
            if alpha >= beta:
                self._cutoffs += 1
                break
        if best <= alpha_orig:
            flag = _UPPER
        elif best >= beta:
            flag = _LOWER
        else:
            flag = _EXACT
        self._table[key] = (depth, best, flag)
        return best

    def _ordered(self, state: GameState, actions: list[Action]) -> list[Action]:
        """Move ordering: approach (Hunter) / retreat (Survivor) first."""
        gm = self.map
        size = gm.width * gm.height
        if state.to_move is Role.HUNTER:
            tgt = state.survivor * size
            key = [
                gm.dist[tgt + gm.step[state.hunter * 5 + a.direction]] if a.direction else 99
                for a in actions
            ]
            return [a for _, a in sorted(zip(key, actions, strict=True), key=lambda p: p[0])]
        src = state.hunter * size
        key = [
            -gm.dist[src + gm.step[state.survivor * 5 + a.direction]] if a.direction else 0
            for a in actions
        ]
        return [a for _, a in sorted(zip(key, actions, strict=True), key=lambda p: p[0])]

    def choose(self, state: GameState) -> tuple[Action, Insight]:
        p = self.params
        self._nodes = self._cutoffs = 0
        self._table.clear()
        self._deadline = time.perf_counter() + p.time_limit_ms / 1000.0
        self._budget = p.node_budget
        actions = legal_actions(self.map, state, self.config)
        ordered = self._ordered(state, actions)
        best_action = ordered[0]
        scores: dict[Action, float] = {}
        depth_reached = 0

        for depth in range(1, p.max_depth + 1):
            try:
                alpha = -math.inf
                current: dict[Action, float] = {}
                iteration_best = ordered[0]
                for action in ordered:
                    child = apply_action(self.map, self.config, state, action)
                    # Full window at the root so every action gets an exact score for the panel.
                    score = -self._negamax(child, depth - 1, -math.inf, math.inf)
                    current[action] = score
                    if score > alpha:
                        alpha, iteration_best = score, action
            except _SearchTimeoutError:
                break
            scores, best_action, depth_reached = current, iteration_best, depth
            ordered = sorted(ordered, key=lambda a: -current[a])
            if abs(alpha) >= 1.0:  # Forced win/loss found.
                break

        if not scores:
            scores = dict.fromkeys(actions, 0.0)
        best_value = scores.get(best_action, 0.0)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        insight = Insight(
            algorithm=self.algorithm,
            summary=(
                f"{best_action.label}: best line scores {best_value:+.2f} at depth {depth_reached}"
            ),
            actions=[ActionScore(a, (max(-1.0, min(1.0, v)) + 1.0) / 2.0) for a, v in ranked],
            plan=self._principal_line(state, best_action),
            stats=[
                ("Depth reached", f"{depth_reached} ply"),
                ("Nodes searched", f"{self._nodes:,}"),
                ("Pruned cutoffs", f"{self._cutoffs:,}"),
                ("Value", f"{best_value:+.3f}"),
            ],
        )
        return best_action, insight

    def _principal_line(self, state: GameState, first: Action) -> list[int]:
        """Reconstruct a short expected path for the overlay (own positions only)."""
        plan: list[int] = []
        s = apply_action(self.map, self.config, state, first)
        plan.append(s.position_of(self.role))
        for _ in range(6):
            if s.is_terminal:
                break
            actions = legal_actions(self.map, s, self.config)
            best_child = s
            best_val = -math.inf
            for a in actions:
                child = apply_action(self.map, self.config, s, a)
                cached = self._table.get(child.key())
                val = -cached[1] if cached and cached[2] == _EXACT else -self._value(child)
                if val > best_val:
                    best_val, best_child = val, child
            s = best_child
            if s.to_move is not self.role:
                plan.append(s.position_of(self.role))
        return plan
