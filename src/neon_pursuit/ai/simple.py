"""Baseline agents: a greedy shortest-path controller and a uniform random one.

Baselines matter: a sophisticated algorithm is only interesting if it beats a
simple one. Both are used as sparring partners in the benchmark lab.
"""

from __future__ import annotations

from ..engine import Action, GameMap, GameState, MatchConfig, Role, legal_actions, path_of
from ..engine.rng import make_rng
from .base import ActionScore, Agent, AlgorithmId, Insight
from .heuristics import greedy_hunter_action, greedy_survivor_action


class GreedyAgent(Agent):
    """Hunter: chase along the shortest path. Survivor: flee, grabbing cores when safe."""

    algorithm = AlgorithmId.GREEDY

    def __init__(self, role: Role, game_map: GameMap, config: MatchConfig, seed: int = 0) -> None:
        super().__init__(role, game_map, config, seed)
        self.rng = make_rng(seed, 303)

    def choose(self, state: GameState) -> tuple[Action, Insight]:
        actions = legal_actions(self.map, state, self.config)
        if self.role is Role.HUNTER:
            action = greedy_hunter_action(self.map, state, actions, self.rng)
            d = self.map.distance(state.hunter, state.survivor)
            summary = f"{action.label}: shortest path toward the Survivor ({d} tiles away)"
        else:
            action = greedy_survivor_action(self.map, self.config, state, actions, self.rng)
            summary = f"{action.label}: maximise distance, detour for cores when safe"
        path = path_of(self.map, state, self.role, action) or []
        return action, Insight(
            algorithm=self.algorithm,
            summary=summary,
            actions=[ActionScore(a, 1.0 if a is action else 0.0) for a in actions],
            plan=path[1:],
            stats=[("Candidates", f"{len(actions)}"), ("Lookahead", "1 ply")],
        )


class RandomAgent(Agent):
    """Uniformly random legal moves — the floor every other agent must beat."""

    algorithm = AlgorithmId.RANDOM

    def __init__(self, role: Role, game_map: GameMap, config: MatchConfig, seed: int = 0) -> None:
        super().__init__(role, game_map, config, seed)
        self.rng = make_rng(seed, 404)

    def choose(self, state: GameState) -> tuple[Action, Insight]:
        actions = legal_actions(self.map, state, self.config)
        action = self.rng.choice(actions)
        share = 1.0 / len(actions)
        return action, Insight(
            algorithm=self.algorithm,
            summary=f"{action.label}: picked uniformly from {len(actions)} legal moves",
            actions=[ActionScore(a, share) for a in actions],
            stats=[("Candidates", f"{len(actions)}")],
        )
