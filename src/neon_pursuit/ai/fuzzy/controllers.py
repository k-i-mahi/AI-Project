"""Fuzzy-logic controllers for both roles.

A fuzzy agent does not search. For every legal action it measures a handful of
crisp features of the resulting position, runs them through a Mamdani
:class:`FuzzySystem` and picks the action with the highest defuzzified
*desirability*. The rule bases below read like the advice a human coach
would give, which is exactly the appeal of fuzzy control.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from ...engine import (
    Action,
    GameMap,
    GameState,
    MatchConfig,
    Role,
    legal_actions,
    path_of,
    safe_core_distance,
    territory_fraction,
    threat_distance,
)
from ...engine.analysis import CONTESTED_CORE_PENALTY
from ...engine.rng import make_rng
from ..base import (
    ActionScore,
    Agent,
    AlgorithmId,
    FuzzyInput,
    FuzzyRuleFiring,
    Insight,
)
from .genome import (
    HUNTER_RULES,
    HUNTER_VARIABLES,
    MANUAL_HUNTER,
    MANUAL_SURVIVOR,
    SURVIVOR_RULES,
    SURVIVOR_VARIABLES,
    FuzzyGenome,
    build_system,
    tuned_genomes,
)
from .system import FuzzySystem


@dataclass(slots=True)
class FuzzyParams:
    #: Random jitter added to crisp scores to break ties and avoid oscillation.
    jitter: float = 0.01
    #: Penalty for spending the burst ability when it is not needed.
    burst_penalty: float = 0.04
    #: ``"tuned"`` uses the GA-optimised genomes when available, ``"manual"`` the hand-made ones.
    profile: str = "tuned"
    #: Explicit genomes (used by the genetic algorithm); override ``profile``.
    survivor_genome: FuzzyGenome | None = None
    hunter_genome: FuzzyGenome | None = None


def genome_for(role: Role, params: FuzzyParams | None = None) -> FuzzyGenome:
    p = params or FuzzyParams()
    explicit = p.survivor_genome if role is Role.SURVIVOR else p.hunter_genome
    if explicit is not None:
        return explicit
    if p.profile == "tuned" and role.value in tuned_genomes():
        return tuned_genomes()[role.value]
    return MANUAL_SURVIVOR if role is Role.SURVIVOR else MANUAL_HUNTER


@cache
def _system(role: Role, genome: FuzzyGenome) -> FuzzySystem:
    if role is Role.SURVIVOR:
        return build_system(SURVIVOR_VARIABLES, SURVIVOR_RULES, genome)
    return build_system(HUNTER_VARIABLES, HUNTER_RULES, genome)


def survivor_system(genome: FuzzyGenome | None = None) -> FuzzySystem:
    """Rule base for the Survivor: stay out of reach, keep room to run, feed when hungry."""
    return _system(Role.SURVIVOR, genome or genome_for(Role.SURVIVOR))


def hunter_system(genome: FuzzyGenome | None = None) -> FuzzySystem:
    """Rule base for the Hunter: close in, shrink the prey's space, guard its food."""
    return _system(Role.HUNTER, genome or genome_for(Role.HUNTER))


class FuzzyAgent(Agent):
    """Scores every legal action with a fuzzy rule base and plays the best one."""

    algorithm = AlgorithmId.FUZZY

    def __init__(
        self,
        role: Role,
        game_map: GameMap,
        config: MatchConfig,
        seed: int = 0,
        params: FuzzyParams | None = None,
    ) -> None:
        super().__init__(role, game_map, config, seed)
        self.params = params or FuzzyParams()
        self.rng = make_rng(seed, 202)
        self.genome = genome_for(role, self.params)
        self.system = _system(role, self.genome)

    # --- Feature extraction ---------------------------------------------------

    def features(self, state: GameState, action: Action) -> dict[str, float]:
        """Crisp inputs describing the position reached by ``action``."""
        path = path_of(self.map, state, self.role, action)
        if path is None:
            raise ValueError(f"Illegal action {action.name}")
        return (
            self._survivor_features(state, path, action)
            if self.role is Role.SURVIVOR
            else self._hunter_features(state, path)
        )

    def _survivor_features(
        self, state: GameState, path: list[int], action: Action
    ) -> dict[str, float]:
        gm, cfg = self.map, self.config
        cell = path[-1]
        d = gm.distance(state.hunter, cell)
        danger = d - 1 if state.pounce_cooldown == 0 and d >= 2 else d
        pulse = action is Action.PULSE
        danger += cfg.pulse_stun if pulse else state.hunter_stun
        grabbed = sum(1 for c in path[1:] if c in state.cores)
        energy = state.energy - (cfg.dash_energy if action.is_burst else 0)
        energy -= cfg.pulse_energy if pulse else 0
        energy = min(cfg.max_energy, energy + grabbed * cfg.core_energy)
        remaining = [c for c in state.cores if c >= 0 and c not in path]
        # Guarded cores look farther away — unless the Survivor is desperate.
        penalty = CONTESTED_CORE_PENALTY * energy / cfg.max_energy
        core = (
            0.0
            if grabbed
            else min(30.0, safe_core_distance(gm, remaining, cell, state.hunter, penalty))
        )
        space = territory_fraction(gm, state.hunter, cell)
        return {
            "danger": float(danger),
            "core": core,
            "space": space,
            "energy": energy / cfg.max_energy,
        }

    def _hunter_features(self, state: GameState, path: list[int]) -> dict[str, float]:
        gm = self.map
        cell = path[-1]
        prey = state.survivor
        prey_energy = state.energy / self.config.max_energy
        if prey in path:
            return {"gap": 0.0, "squeeze": 0.0, "intercept": -12.0, "prey_energy": prey_energy}
        d = gm.distance(cell, prey)
        pounce_after = state.pounce_cooldown <= 1 and len(path) < 3
        gap = d - 1 if pounce_after and d >= 2 else d
        squeeze = territory_fraction(gm, cell, prey)
        targets = [c for c in state.cores if c >= 0]
        if targets:
            target = min(targets, key=lambda c: gm.distance(prey, c))
            intercept = gm.distance(cell, target) - gm.distance(prey, target)
        else:
            intercept = 0
        return {
            "gap": float(gap),
            "squeeze": squeeze,
            "intercept": float(intercept),
            "prey_energy": prey_energy,
        }

    # --- Decision -------------------------------------------------------------

    def choose(self, state: GameState) -> tuple[Action, Insight]:
        actions = legal_actions(self.map, state, self.config)
        scored: list[tuple[float, float, Action, dict[str, float]]] = []
        for action in actions:
            feats = self.features(state, action)
            result = self.system.evaluate(feats)
            crisp = result.output
            urgent = feats.get("danger", 10.0) <= 2 or feats.get("gap", 10.0) <= 0
            if action.is_burst and not urgent:
                crisp -= self.params.burst_penalty
            if action is Action.PULSE and threat_distance(self.map, state) > 2:
                crisp -= 3 * self.params.burst_penalty  # save the EMP for real danger
            noisy = crisp + self.rng.uniform(0.0, self.params.jitter)
            scored.append((noisy, crisp, action, feats))

        scored.sort(key=lambda t: -t[0])
        _, best_crisp, best_action, best_feats = scored[0]
        detail = self.system.evaluate(best_feats, keep_curve=True)

        inputs = [
            FuzzyInput(
                name=name,
                value=best_feats[name],
                low=var.low,
                high=var.high,
                memberships=list(detail.fuzzified[name].items()),
            )
            for name, var in self.system.inputs.items()
        ]
        firings = [
            FuzzyRuleFiring(rule.rule_id, rule.text(self.system.output.name), strength)
            for rule, strength in detail.rule_strengths
        ]
        label = self.system.best_term(detail.output)
        top_rule = max(firings, key=lambda f: f.strength)
        return best_action, Insight(
            algorithm=self.algorithm,
            summary=f"{best_action.label}: desirability {best_crisp:.2f} ({label}); "
            f"strongest rule {top_rule.rule_id}",
            actions=[ActionScore(a, max(0.0, min(1.0, c))) for _, c, a, _ in scored],
            plan=(path_of(self.map, state, self.role, best_action) or [])[1:],
            stats=[
                ("Rules fired", f"{sum(1 for f in firings if f.strength > 0)}/{len(firings)}"),
                ("Output", f"{detail.output:.3f} ({label})"),
            ],
            fuzzy_inputs=inputs,
            fuzzy_rules=firings,
            fuzzy_output=detail.output,
            fuzzy_curve=detail.curve,
        )
