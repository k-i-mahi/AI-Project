"""Match orchestration independent of rendering (and therefore unit-testable)."""

from __future__ import annotations

import itertools
from concurrent.futures import Future
from dataclasses import dataclass, field

from ..ai import AgentSettings, AlgorithmId, Decision, Insight
from ..engine import (
    Action,
    GameEvent,
    GameState,
    MatchConfig,
    Role,
    apply_action,
    generate_map,
    initial_state,
    is_legal,
)
from ..engine.rng import derive_seed
from .brain import Brain

_match_ids = itertools.count(1)


@dataclass(slots=True)
class MatchSetup:
    """Who controls each side. ``None`` means a human player."""

    hunter: AlgorithmId | None
    survivor: AlgorithmId | None
    config: MatchConfig = field(default_factory=MatchConfig)
    hunter_settings: AgentSettings = field(default_factory=AgentSettings)
    survivor_settings: AgentSettings = field(default_factory=AgentSettings)

    def controller(self, role: Role) -> AlgorithmId | None:
        return self.hunter if role is Role.HUNTER else self.survivor

    def settings(self, role: Role) -> AgentSettings:
        return self.hunter_settings if role is Role.HUNTER else self.survivor_settings


@dataclass(slots=True)
class Turn:
    role: Role
    action: Action
    before: GameState
    after: GameState
    events: list[GameEvent]
    decision: Decision | None


class MatchController:
    def __init__(self, setup: MatchSetup, brain: Brain) -> None:
        self.setup = setup
        self.brain = brain
        self.map = generate_map(setup.config)
        self.match_id = next(_match_ids)
        self.state = initial_state(self.map, setup.config)
        self.history: list[Turn] = []
        self.insights: dict[Role, Insight | None] = {Role.HUNTER: None, Role.SURVIVOR: None}
        self.think_ms: dict[Role, list[float]] = {Role.HUNTER: [], Role.SURVIVOR: []}
        self._pending: Future[Decision] | None = None

    # --- Queries --------------------------------------------------------------

    @property
    def config(self) -> MatchConfig:
        return self.setup.config

    @property
    def is_over(self) -> bool:
        return self.state.is_terminal

    def is_human_turn(self) -> bool:
        return not self.is_over and self.setup.controller(self.state.to_move) is None

    @property
    def thinking(self) -> bool:
        return self._pending is not None

    def agent_seed(self, role: Role) -> int:
        return derive_seed(self.config.seed, 11 if role is Role.HUNTER else 22)

    # --- AI turns -------------------------------------------------------------

    def request_ai(self) -> None:
        """Ask the background brain for a move if it is an AI's turn."""
        if self.is_over or self._pending is not None:
            return
        role = self.state.to_move
        algorithm = self.setup.controller(role)
        if algorithm is None:
            return
        self._pending = self.brain.think(
            self.match_id,
            role,
            algorithm,
            self.config,
            self.agent_seed(role),
            self.setup.settings(role),
            self.state,
        )

    def ai_ready(self) -> bool:
        return self._pending is not None and self._pending.done()

    def commit_ai(self) -> Turn | None:
        """Apply the finished AI decision, if any."""
        if self._pending is None or not self._pending.done():
            return None
        decision = self._pending.result()
        self._pending = None
        role = self.state.to_move
        self.insights[role] = decision.insight
        self.think_ms[role].append(decision.elapsed_ms)
        return self._apply(decision.action, decision)

    # --- Human turns ----------------------------------------------------------

    def can_play(self, action: Action) -> bool:
        return self.is_human_turn() and is_legal(self.map, self.state, action, self.config)

    def play_human(self, action: Action) -> Turn | None:
        if not self.can_play(action):
            return None
        return self._apply(action, None)

    # --- Internals --------------------------------------------------------------

    def _apply(self, action: Action, decision: Decision | None) -> Turn:
        before = self.state
        events: list[GameEvent] = []
        self.state = apply_action(self.map, self.config, before, action, events)
        turn = Turn(before.to_move, action, before, self.state, events, decision)
        self.history.append(turn)
        return turn

    def cancel(self) -> None:
        if self._pending is not None:
            self._pending.cancel()
            self._pending = None
