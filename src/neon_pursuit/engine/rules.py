"""Game rules: legal moves and state transitions.

Turn structure: the Survivor moves, then the Hunter moves — together one
*round*. Outcomes:

* **Hunter wins** by entering the Survivor's tile (a pounce may capture on its
  first tile), or when the Survivor's energy runs out (*starved*).
* **Survivor wins** by collecting ``cores_to_win`` cores, or by lasting
  ``max_rounds`` rounds.

The Survivor loses one energy point per round and regains ``core_energy`` per
core, so hiding forever is not an option: it has to take risks to feed.
"""

from __future__ import annotations

from .board import GameMap
from .types import (
    Action,
    CaptureEvent,
    CoreCollectedEvent,
    CoreSpawnedEvent,
    GameEvent,
    GameState,
    MatchConfig,
    MatchEndEvent,
    MoveEvent,
    Role,
    Status,
    WinReason,
)

#: Minimum path distance between the Survivor and a freshly spawned core.
CORE_SPAWN_MIN_DISTANCE = 4
#: The Survivor cannot dash unless it has more energy than this.
DASH_MIN_ENERGY = 3


class IllegalActionError(ValueError):
    """Raised when an agent submits an action that is not legal in the state."""


def initial_state(game_map: GameMap, config: MatchConfig) -> GameState:
    cores = [-1] * config.active_cores
    cursor = _refill_cores(game_map, cores, game_map.hunter_spawn, game_map.survivor_spawn, 0)
    return GameState(
        hunter=game_map.hunter_spawn,
        survivor=game_map.survivor_spawn,
        cores=tuple(cores),
        cores_collected=0,
        core_cursor=cursor,
        round=0,
        to_move=Role.SURVIVOR,
        dash_cooldown=0,
        pounce_cooldown=0,
        energy=config.start_energy,
    )


def _refill_cores(
    game_map: GameMap,
    cores: list[int],
    hunter: int,
    survivor: int,
    cursor: int,
    events: list[GameEvent] | None = None,
) -> int:
    """Fill empty core slots in place from the deterministic spawn sequence."""
    seq = game_map.core_sequence
    n = len(seq)
    if n == 0:
        return cursor
    for slot, value in enumerate(cores):
        if value != -1:
            continue
        for _ in range(n):
            cell = seq[cursor % n]
            cursor += 1
            if cell in (hunter, survivor) or cell in cores:
                continue
            if game_map.distance(survivor, cell) < CORE_SPAWN_MIN_DISTANCE:
                continue
            cores[slot] = cell
            if events is not None:
                events.append(CoreSpawnedEvent(cell))
            break
    return cursor


def path_of(game_map: GameMap, state: GameState, role: Role, action: Action) -> list[int] | None:
    """Cells visited (start included) when ``role`` performs ``action``; None if blocked."""
    start = state.hunter if role is Role.HUNTER else state.survivor
    if action == Action.WAIT:
        return [start]
    d = ((action - 1) % 4) + 1
    step = game_map.step
    mid = step[start * 5 + d]
    if mid < 0:
        return None
    if action < Action.BURST_NORTH:
        return [start, mid]
    if role is Role.HUNTER:
        if state.pounce_cooldown > 0:
            return None
        if mid == state.survivor:
            return [start, mid]
    elif state.dash_cooldown > 0 or state.energy <= DASH_MIN_ENERGY:
        return None
    end = step[mid * 5 + d]
    if end < 0:
        return None
    return [start, mid, end]


def is_legal(game_map: GameMap, state: GameState, action: Action) -> bool:
    if state.status is not Status.PLAYING:
        return False
    path = path_of(game_map, state, state.to_move, action)
    if path is None:
        return False
    # The Survivor may never step onto (or dash through) the Hunter.
    return not (state.to_move is Role.SURVIVOR and state.hunter in path[1:])


def legal_actions(game_map: GameMap, state: GameState) -> list[Action]:
    if state.status is not Status.PLAYING:
        return []
    return [a for a in Action if is_legal(game_map, state, a)]


def apply_action(
    game_map: GameMap,
    config: MatchConfig,
    state: GameState,
    action: Action,
    events: list[GameEvent] | None = None,
) -> GameState:
    """Return the state after the side to move plays ``action``.

    Pass an ``events`` list to receive :mod:`GameEvent` objects describing what
    happened (the UI uses them for effects); search agents omit it.
    """
    if state.status is not Status.PLAYING:
        raise IllegalActionError("Match is already over")
    role = state.to_move
    path = path_of(game_map, state, role, action)
    if path is None or (role is Role.SURVIVOR and state.hunter in path[1:]):
        raise IllegalActionError(f"Illegal action {Action(action).name} for {role.value}")
    start, end = path[0], path[-1]
    if events is not None:
        events.append(MoveEvent(role, start, end, Action(action)))

    if role is Role.SURVIVOR:
        return _apply_survivor(game_map, config, state, path, events)

    if state.survivor in path:
        if events is not None:
            events.append(CaptureEvent(state.survivor))
            events.append(MatchEndEvent(Status.HUNTER_WIN, WinReason.CAPTURED))
        return GameState(
            hunter=state.survivor,
            survivor=state.survivor,
            cores=state.cores,
            cores_collected=state.cores_collected,
            core_cursor=state.core_cursor,
            round=state.round,
            to_move=Role.SURVIVOR,
            dash_cooldown=state.dash_cooldown,
            pounce_cooldown=state.pounce_cooldown,
            energy=state.energy,
            status=Status.HUNTER_WIN,
            win_reason=WinReason.CAPTURED,
        )

    rnd = state.round + 1
    pounce = config.pounce_cooldown if len(path) == 3 else state.pounce_cooldown
    energy = state.energy - 1
    status, reason = Status.PLAYING, None
    if energy <= 0:
        status, reason = Status.HUNTER_WIN, WinReason.STARVED
    elif rnd >= config.max_rounds:
        status, reason = Status.SURVIVOR_WIN, WinReason.SURVIVED
    if reason is not None and events is not None:
        events.append(MatchEndEvent(status, reason))
    return GameState(
        hunter=end,
        survivor=state.survivor,
        cores=state.cores,
        cores_collected=state.cores_collected,
        core_cursor=state.core_cursor,
        round=rnd,
        to_move=Role.SURVIVOR,
        dash_cooldown=max(0, state.dash_cooldown - 1),
        pounce_cooldown=max(0, pounce - 1),
        energy=max(0, energy),
        status=status,
        win_reason=reason,
    )


def _apply_survivor(
    game_map: GameMap,
    config: MatchConfig,
    state: GameState,
    path: list[int],
    events: list[GameEvent] | None,
) -> GameState:
    end = path[-1]
    dashed = len(path) == 3
    energy = state.energy - (config.dash_energy if dashed else 0)
    collected = state.cores_collected
    cores = state.cores
    cursor = state.core_cursor
    status = Status.PLAYING
    reason: WinReason | None = None

    hits = [cell for cell in path[1:] if cell in cores]
    if hits:
        slots = list(cores)
        for cell in hits:
            slots[slots.index(cell)] = -1
            collected += 1
            energy = min(config.max_energy, energy + config.core_energy)
            if events is not None:
                events.append(CoreCollectedEvent(cell, collected))
        if collected >= config.cores_to_win:
            status, reason = Status.SURVIVOR_WIN, WinReason.CORES_COLLECTED
            if events is not None:
                events.append(MatchEndEvent(status, reason))
        else:
            cursor = _refill_cores(game_map, slots, state.hunter, end, cursor, events)
        cores = tuple(slots)

    return GameState(
        hunter=state.hunter,
        survivor=end,
        cores=cores,
        cores_collected=collected,
        core_cursor=cursor,
        round=state.round,
        to_move=Role.HUNTER,
        dash_cooldown=config.dash_cooldown if dashed else state.dash_cooldown,
        pounce_cooldown=state.pounce_cooldown,
        energy=energy,
        status=status,
        win_reason=reason,
    )
