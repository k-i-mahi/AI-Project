"""Monte Carlo Tree Search with UCT (Upper Confidence bounds applied to Trees).

Each iteration runs the four classic phases:

1. **Selection** — descend the tree, choosing the child that maximises
   ``Q/N + c * sqrt(ln N_parent / N)``.
2. **Expansion** — add one untried action as a new child.
3. **Simulation** — play an epsilon-greedy rollout for a bounded number of
   plies, then score the position with the static heuristic.
4. **Backpropagation** — add the result to every node on the path, each from
   the perspective of the player who made the move into that node.

Before searching, the root is filtered with *decisive / anti-decisive moves*:
an immediately winning move is played at once, and moves that hand the
opponent an immediate win are discarded whenever a safe alternative exists.
This removes MCTS's classic weakness to shallow tactical traps.

The game is two-player, alternating and perfect-information, so a single tree
serves both sides: values flip between Survivor (v) and Hunter (1 - v).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..engine import (
    Action,
    GameMap,
    GameState,
    MatchConfig,
    Role,
    Status,
    apply_action,
    legal_actions,
)
from ..engine.rng import make_rng
from .base import ActionScore, Agent, AlgorithmId, Insight
from .heuristics import evaluate, rollout_action


@dataclass(slots=True)
class MctsParams:
    iterations: int = 700
    exploration: float = 1.2
    rollout_depth: int = 14
    rollout_epsilon: float = 0.2
    #: Hard wall-clock cap per decision; iterations stop early if exceeded.
    time_limit_ms: float = 1500.0


class _Node:
    __slots__ = ("action", "children", "parent", "state", "untried", "value", "visits")

    def __init__(
        self,
        state: GameState,
        parent: _Node | None,
        action: Action | None,
        untried: list[Action],
    ) -> None:
        self.state = state
        self.parent = parent
        self.action = action
        self.children: list[_Node] = []
        self.untried = untried
        self.visits = 0
        #: Sum of rewards for the player who moved *into* this node.
        self.value = 0.0


class MctsAgent(Agent):
    algorithm = AlgorithmId.MCTS

    def __init__(
        self,
        role: Role,
        game_map: GameMap,
        config: MatchConfig,
        seed: int = 0,
        params: MctsParams | None = None,
    ) -> None:
        super().__init__(role, game_map, config, seed)
        self.params = params or MctsParams()
        self.rng = make_rng(seed, 101)

    def choose(self, state: GameState) -> tuple[Action, Insight]:
        p = self.params
        gm, cfg, rng = self.map, self.config, self.rng
        root_actions, forced = self._screen_root(state, legal_actions(gm, state, cfg))
        if forced is not None:
            return forced, Insight(
                algorithm=self.algorithm,
                summary=f"{forced.label}: wins immediately (decisive move).",
                actions=[ActionScore(forced, 1.0, 0)],
                stats=[("Shortcut", "decisive move")],
            )
        if len(root_actions) == 1:
            only = root_actions[0]
            return only, Insight(
                algorithm=self.algorithm,
                summary="Only one legal move.",
                actions=[ActionScore(only, 1.0, 0)],
            )

        root = _Node(state, None, None, self._shuffled(root_actions))
        deadline = time.perf_counter() + p.time_limit_ms / 1000.0
        max_depth = 0
        iterations = 0
        log = math.log
        sqrt = math.sqrt
        c = p.exploration

        while iterations < p.iterations:
            if iterations % 32 == 0 and time.perf_counter() > deadline:
                break
            iterations += 1
            node = root
            depth = 0

            # 1. Selection.
            while not node.untried and node.children:
                log_n = log(node.visits)
                best = node.children[0]
                best_ucb = -math.inf
                for child in node.children:
                    ucb = child.value / child.visits + c * sqrt(log_n / child.visits)
                    if ucb > best_ucb:
                        best, best_ucb = child, ucb
                node = best
                depth += 1

            # 2. Expansion.
            if node.untried and not node.state.is_terminal:
                action = node.untried.pop()
                nxt = apply_action(gm, cfg, node.state, action)
                child = _Node(nxt, node, action, self._shuffled(legal_actions(gm, nxt, cfg)))
                node.children.append(child)
                node = child
                depth += 1
            max_depth = max(max_depth, depth)

            # 3. Simulation.
            sim = node.state
            for _ in range(p.rollout_depth):
                if sim.is_terminal:
                    break
                sim = apply_action(
                    gm, cfg, sim, rollout_action(gm, cfg, sim, rng, p.rollout_epsilon)
                )
            survivor_value = evaluate(gm, cfg, sim)

            # 4. Backpropagation.
            back: _Node | None = node
            while back is not None:
                back.visits += 1
                if back.parent is not None:
                    mover = back.parent.state.to_move
                    back.value += survivor_value if mover is Role.SURVIVOR else 1.0 - survivor_value
                back = back.parent

        best_child = max(root.children, key=lambda ch: (ch.visits, ch.value))
        return best_child.action or Action.WAIT, self._insight(
            root, best_child, iterations, max_depth
        )

    def _screen_root(
        self, state: GameState, actions: list[Action]
    ) -> tuple[list[Action], Action | None]:
        """Return (actions worth searching, immediately winning action or None)."""
        gm, cfg = self.map, self.config
        me = state.to_move
        win = Status.HUNTER_WIN if me is Role.HUNTER else Status.SURVIVOR_WIN
        safe: list[Action] = []
        for action in actions:
            child = apply_action(gm, cfg, state, action)
            if child.status is win:
                return actions, action
            if child.is_terminal:
                continue  # immediate loss
            loses = any(
                apply_action(gm, cfg, child, reply).status not in (Status.PLAYING, win)
                for reply in legal_actions(gm, child, cfg)
            )
            if not loses:
                safe.append(action)
        return (safe or actions), None

    def _shuffled(self, actions: list[Action]) -> list[Action]:
        self.rng.shuffle(actions)
        return actions

    def _insight(self, root: _Node, best: _Node, iterations: int, max_depth: int) -> Insight:
        total = max(1, sum(ch.visits for ch in root.children))
        scores = sorted(
            (
                ActionScore(ch.action or Action.WAIT, ch.visits / total, ch.visits)
                for ch in root.children
            ),
            key=lambda s: -s.score,
        )
        win_rate = best.value / max(1, best.visits)

        # Principal variation: follow the most-visited children, collect own positions.
        plan: list[int] = []
        node: _Node | None = best
        while node is not None and len(plan) < 8:
            if node.parent is not None and node.parent.state.to_move is self.role:
                plan.append(node.state.position_of(self.role))
            node = max(node.children, key=lambda ch: ch.visits) if node.children else None

        best_action = best.action or Action.WAIT
        return Insight(
            algorithm=self.algorithm,
            summary=(
                f"{best_action.label}: chosen in {best.visits}/{total} simulations, "
                f"est. win {win_rate:.0%}"
            ),
            actions=scores,
            plan=plan,
            stats=[
                ("Iterations", f"{iterations}"),
                ("Tree depth", f"{max_depth}"),
                ("Win estimate", f"{win_rate:.1%}"),
                ("Exploration c", f"{self.params.exploration:.2f}"),
            ],
        )
