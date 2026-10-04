"""Core domain types for the Neon Pursuit engine.

The engine is pure and deterministic: given the same map, configuration and
sequence of actions it always produces the same states. That property lets the
search-based agents (MCTS, Minimax) plan without hidden randomness, and makes
every match and benchmark reproducible from its seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Role(StrEnum):
    HUNTER = "hunter"
    SURVIVOR = "survivor"

    @property
    def opponent(self) -> Role:
        return Role.SURVIVOR if self is Role.HUNTER else Role.HUNTER


class Action(IntEnum):
    """Integer-encoded actions keep search trees compact.

    ``BURST_*`` moves two tiles in a straight line: the Survivor's *Dash* or the
    Hunter's *Pounce*. Both are limited by a cooldown. ``PULSE`` is the Survivor's
    EMP: it stays in place and stuns a nearby Hunter for a few turns.
    """

    WAIT = 0
    NORTH = 1
    EAST = 2
    SOUTH = 3
    WEST = 4
    BURST_NORTH = 5
    BURST_EAST = 6
    BURST_SOUTH = 7
    BURST_WEST = 8
    PULSE = 9

    @property
    def is_burst(self) -> bool:
        return Action.BURST_NORTH <= self <= Action.BURST_WEST

    @property
    def direction(self) -> int:
        """Direction index 1..4 (N, E, S, W); 0 for WAIT and PULSE."""
        if self is Action.WAIT or self is Action.PULSE:
            return 0
        return ((self - 1) % 4) + 1

    @property
    def label(self) -> str:
        names = {0: "Wait", 1: "North", 2: "East", 3: "South", 4: "West"}
        if self is Action.PULSE:
            return "EMP Pulse"
        if self.is_burst:
            return f"Burst {names[self.direction]}"
        return names[int(self)]

    @property
    def glyph(self) -> str:
        if self is Action.PULSE:
            return "*"
        arrows = {0: "·", 1: "↑", 2: "→", 3: "↓", 4: "←"}
        g = arrows[self.direction]
        return g * 2 if self.is_burst else g


ALL_ACTIONS: tuple[Action, ...] = tuple(Action)


class Status(StrEnum):
    PLAYING = "playing"
    HUNTER_WIN = "hunter_win"
    SURVIVOR_WIN = "survivor_win"


class WinReason(StrEnum):
    CAPTURED = "captured"
    STARVED = "starved"
    CORES_COLLECTED = "cores_collected"
    SURVIVED = "survived"


@dataclass(slots=True, frozen=True)
class MatchConfig:
    """Static rules for a match. Never mutated during play."""

    width: int = 21
    height: int = 15
    seed: int = 2026
    #: Fraction of interior tiles that start as walls (before connectivity repair).
    wall_density: float = 0.24
    #: Number of cores on the board at any moment.
    active_cores: int = 4
    #: Cores the Survivor needs for an outright win.
    cores_to_win: int = 10
    #: Rounds the Survivor must outlast (one round = Survivor move + Hunter move).
    max_rounds: int = 160
    #: Rounds between Survivor dashes.
    dash_cooldown: int = 7
    #: Rounds between Hunter pounces.
    pounce_cooldown: int = 9
    #: Survivor energy at the start; one point drains every round.
    start_energy: int = 35
    #: Energy cap.
    max_energy: int = 45
    #: Energy restored by each core.
    core_energy: int = 15
    #: Extra energy spent by a dash.
    dash_energy: int = 3
    #: EMP pulse: works when the Hunter is within this path distance.
    pulse_radius: int = 3
    #: Hunter turns lost to a pulse.
    pulse_stun: int = 3
    #: Rounds between pulses.
    pulse_cooldown: int = 18
    #: Energy spent by a pulse.
    pulse_energy: int = 4

    def __post_init__(self) -> None:
        if self.width < 9 or self.height < 7:
            raise ValueError("Map must be at least 9x7")
        if self.cores_to_win < 1 or self.active_cores < 1 or self.max_rounds < 1:
            raise ValueError("cores_to_win, active_cores and max_rounds must be >= 1")
        if not 0 < self.start_energy <= self.max_energy:
            raise ValueError("start_energy must be in (0, max_energy]")
        if not 0.0 <= self.wall_density < 0.6:
            raise ValueError("wall_density must be in [0, 0.6)")


@dataclass(slots=True, frozen=True)
class GameState:
    """A snapshot of a match. Treated as immutable; transitions build new states."""

    hunter: int
    survivor: int
    #: Cell index of each active core; -1 marks an empty slot.
    cores: tuple[int, ...]
    cores_collected: int
    #: Next index into ``GameMap.core_sequence`` used when respawning cores.
    core_cursor: int
    round: int
    to_move: Role
    dash_cooldown: int
    pounce_cooldown: int
    #: Survivor energy; the Survivor collapses (Hunter wins) when it reaches 0.
    energy: int
    #: Rounds until the Survivor may pulse again.
    pulse_cooldown: int = 0
    #: Hunter turns remaining in which it is stunned (may only wait).
    hunter_stun: int = 0
    status: Status = Status.PLAYING
    win_reason: WinReason | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status is not Status.PLAYING

    def position_of(self, role: Role) -> int:
        return self.hunter if role is Role.HUNTER else self.survivor

    def key(self) -> tuple[int, ...]:
        """Hashable key for transposition tables and repetition detection."""
        return (
            self.hunter,
            self.survivor,
            *self.cores,
            self.cores_collected,
            1 if self.to_move is Role.HUNTER else 0,
            self.dash_cooldown,
            self.pounce_cooldown,
            self.energy,
            self.pulse_cooldown,
            self.hunter_stun,
        )


# --- Events -----------------------------------------------------------------
# Emitted by transitions so the UI can trigger effects and build a match log.


@dataclass(slots=True, frozen=True)
class MoveEvent:
    role: Role
    from_cell: int
    to_cell: int
    action: Action


@dataclass(slots=True, frozen=True)
class CoreCollectedEvent:
    cell: int
    total: int


@dataclass(slots=True, frozen=True)
class CoreSpawnedEvent:
    cell: int


@dataclass(slots=True, frozen=True)
class CaptureEvent:
    cell: int


@dataclass(slots=True, frozen=True)
class PulseEvent:
    cell: int
    stunned: bool


@dataclass(slots=True, frozen=True)
class MatchEndEvent:
    status: Status
    reason: WinReason


GameEvent = (
    MoveEvent | CoreCollectedEvent | CoreSpawnedEvent | CaptureEvent | PulseEvent | MatchEndEvent
)
