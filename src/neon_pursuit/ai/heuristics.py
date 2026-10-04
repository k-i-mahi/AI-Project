"""Static evaluation and fast rollout policies shared by the search agents."""

from __future__ import annotations

import math
import random

from ..engine import (
    Action,
    GameMap,
    GameState,
    MatchConfig,
    Role,
    Status,
    legal_actions,
    path_of,
    safe_core_distance,
    survivor_territory,
    threat_distance,
)

#: Weights of the evaluation features. The core weight grows with hunger
#: (``W_CORE + W_HUNGER * hunger``); the total is renormalised to [0, 1].
W_SAFETY = 0.28
W_TERRITORY = 0.14
W_PROGRESS = 0.28
W_CORE = 0.12
W_HUNGER = 0.14
W_ENERGY = 0.10
#: Distances beyond this count as "no core in sight".
CORE_HORIZON = 30.0


def evaluate(game_map: GameMap, config: MatchConfig, state: GameState) -> float:
    """Heuristic value of ``state`` for the **Survivor**, in [0, 1].

    Features (all normalised to [0, 1]):

    * **safety** — effective distance to the Hunter (a ready pounce counts as 2 tiles);
    * **territory** — Voronoi share of the map the Survivor reaches first;
    * **progress** — cores collected / cores needed;
    * **core** — closeness of the nearest *safe* core, weighted more as hunger grows;
    * **energy** — remaining energy.

    Positions where the Survivor can no longer reach a core before starving are
    heavily discounted. The Hunter simply maximises ``1 - evaluate(...)``.
    """
    if state.status is Status.HUNTER_WIN:
        return 0.0
    if state.status is Status.SURVIVOR_WIN:
        return 1.0

    threat = threat_distance(game_map, state)
    if state.to_move is Role.HUNTER and threat <= 1:
        return 0.02  # The Hunter captures next move.
    safety = 1.0 - math.exp(-max(0, threat - 1) / 2.5)

    floor = len(game_map.floor_cells)
    territory = min(1.0, 2.0 * survivor_territory(game_map, state.hunter, state.survivor) / floor)

    progress = state.cores_collected / config.cores_to_win
    core_d = min(
        CORE_HORIZON, safe_core_distance(game_map, state.cores, state.survivor, state.hunter)
    )
    core = 1.0 - core_d / CORE_HORIZON
    energy = state.energy / config.max_energy
    hunger = 1.0 - energy
    w_core = W_CORE + W_HUNGER * hunger

    value = (
        W_SAFETY * safety
        + W_TERRITORY * territory
        + W_PROGRESS * progress
        + w_core * core
        + W_ENERGY * energy
    ) / (W_SAFETY + W_TERRITORY + W_PROGRESS + w_core + W_ENERGY)
    if state.energy < core_d + 1:
        value *= 0.3  # Cannot reach food in time.
    return max(0.0, min(1.0, value))


def _landing(game_map: GameMap, state: GameState, role: Role, action: Action) -> int:
    path = path_of(game_map, state, role, action)
    return path[-1] if path else -1


def greedy_hunter_action(
    game_map: GameMap, state: GameState, actions: list[Action], rng: random.Random | None = None
) -> Action:
    """Move that minimises path distance to the Survivor (pounce only if it pays off)."""
    size = game_map.width * game_map.height
    target = state.survivor * size
    best: list[Action] = []
    best_score = math.inf
    for a in actions:
        cell = _landing(game_map, state, Role.HUNTER, a)
        d = game_map.dist[target + cell]
        # Save the pounce for when it lands a capture or closes a real gap.
        score = d + (0.6 if a.is_burst and d > 0 else 0.0) + (0.4 if a is Action.WAIT else 0.0)
        if score < best_score - 1e-9:
            best, best_score = [a], score
        elif abs(score - best_score) <= 1e-9:
            best.append(a)
    return rng.choice(best) if rng and len(best) > 1 else best[0]


def greedy_survivor_action(
    game_map: GameMap,
    config: MatchConfig,
    state: GameState,
    actions: list[Action],
    rng: random.Random | None = None,
) -> Action:
    """Move that balances distance from the Hunter against reaching a core (hungrier = bolder).

    A stunned Hunter loses turns, so stun rounds count as extra distance; the EMP
    pulse is therefore chosen exactly when the Hunter is about to strike.
    """
    size = game_map.width * game_map.height
    hunger = 1.0 + 2.0 * (1.0 - state.energy / config.max_energy)
    hunter_base = state.hunter * size
    pounce_ready = state.pounce_cooldown == 0
    best: list[Action] = []
    best_score = -math.inf
    for a in actions:
        path = path_of(game_map, state, Role.SURVIVOR, a)
        if path is None:
            continue
        cell = path[-1]
        d = game_map.dist[hunter_base + cell]
        reach = d - 1 if pounce_ready and d >= 2 else d
        reach += config.pulse_stun if a is Action.PULSE else state.hunter_stun
        if reach <= 1:
            score = -100.0 + d
        else:
            core_d = min(30.0, safe_core_distance(game_map, state.cores, cell, state.hunter))
            grabbed = sum(1 for c in path[1:] if c in state.cores)
            score = min(reach, 6) * 1.5 - core_d * hunger + grabbed * 8.0
            if a.is_burst:
                score -= 1.5  # Keep the dash for emergencies.
            elif a is Action.PULSE:
                score -= 4.0  # Only worth it when the Hunter is about to strike.
        if score > best_score + 1e-9:
            best, best_score = [a], score
        elif abs(score - best_score) <= 1e-9:
            best.append(a)
    if not best:
        return actions[0]
    return rng.choice(best) if rng and len(best) > 1 else best[0]


def rollout_action(
    game_map: GameMap, config: MatchConfig, state: GameState, rng: random.Random, epsilon: float
) -> Action:
    """Epsilon-greedy default policy used inside MCTS simulations."""
    actions = legal_actions(game_map, state, config)
    if rng.random() < epsilon:
        return rng.choice(actions)
    if state.to_move is Role.HUNTER:
        return greedy_hunter_action(game_map, state, actions, rng)
    return greedy_survivor_action(game_map, config, state, actions, rng)
