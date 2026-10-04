"""Fuzzy-logic controllers for both roles.

A fuzzy agent does not search. For every legal action it measures a handful of
crisp features of the resulting position, runs them through a Mamdani
:class:`FuzzySystem` and picks the action with the highest defuzzified
*desirability*. The rule bases below read like the advice a human coach
would give, which is exactly the appeal of fuzzy control.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

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
from .system import FuzzySystem, LinguisticVariable, Trapezoid, triangle, when


@dataclass(slots=True)
class FuzzyParams:
    #: Random jitter added to crisp scores to break ties and avoid oscillation.
    jitter: float = 0.01
    #: Penalty for spending the burst ability when it is not needed.
    burst_penalty: float = 0.04


DESIRABILITY = LinguisticVariable(
    "desirability",
    0.0,
    1.0,
    {
        "avoid": Trapezoid(0.0, 0.0, 0.1, 0.25),
        "poor": triangle(0.1, 0.3, 0.5),
        "fair": triangle(0.35, 0.5, 0.65),
        "good": triangle(0.5, 0.7, 0.9),
        "excellent": Trapezoid(0.75, 0.9, 1.0, 1.0),
    },
)

# Every input below uses a *fuzzy partition* (adjacent terms overlap and sum to 1).
# With Mamdani + centroid, a lone active term always defuzzifies to its own
# centre; overlapping terms make the output interpolate smoothly, so moving one
# tile closer to a core is always visibly "a bit better".
SPACE_TERMS = {
    "cornered": Trapezoid(0.0, 0.0, 0.03, 0.12),
    "limited": triangle(0.03, 0.12, 0.3),
    "open": Trapezoid(0.12, 0.3, 0.6, 0.6),
}


def survivor_system() -> FuzzySystem:
    """Rule base for the Survivor: stay out of reach, keep room to run, feed when hungry."""
    danger = LinguisticVariable(
        "danger",
        0,
        12,
        {
            "critical": Trapezoid(0, 0, 1, 2),
            "near": triangle(1, 2, 4),
            "safe": Trapezoid(2, 4, 12, 12),
        },
        unit="moves",
    )
    core = LinguisticVariable(
        "core",
        0,
        30,
        {
            "close": Trapezoid(0, 0, 0, 10),
            "mid": triangle(0, 10, 30),
            "far": Trapezoid(10, 30, 30, 30),
        },
        unit="tiles",
    )
    space = LinguisticVariable("space", 0, 0.6, SPACE_TERMS, unit="of map")
    energy = LinguisticVariable(
        "energy",
        0,
        1,
        {
            "low": Trapezoid(0, 0, 0.15, 0.5),
            "medium": triangle(0.15, 0.5, 0.85),
            "high": Trapezoid(0.5, 0.85, 1, 1),
        },
        unit="of max",
    )
    rules = [
        when(("danger", "critical"), then="avoid", rule_id="S1"),
        when(("danger", "near"), ("space", "cornered"), then="avoid", rule_id="S2"),
        when(("danger", "near"), ("core", "close"), then="good", rule_id="S3"),
        when(("danger", "near"), ("core", "mid"), then="fair", rule_id="S4"),
        when(("danger", "near"), ("core", "far"), then="poor", rule_id="S5"),
        when(("danger", "near"), ("space", "open"), then="fair", rule_id="S6"),
        when(("danger", "safe"), ("core", "close"), then="excellent", rule_id="S7"),
        when(("danger", "safe"), ("core", "mid"), then="good", rule_id="S8"),
        when(("danger", "safe"), ("core", "far"), then="fair", rule_id="S9"),
        when(("danger", "safe"), ("space", "cornered"), then="poor", rule_id="S10"),
        when(("energy", "low"), ("core", "close"), then="excellent", rule_id="S11"),
        when(("energy", "low"), ("core", "mid"), then="fair", rule_id="S12"),
        when(("energy", "low"), ("core", "far"), then="avoid", rule_id="S13"),
    ]
    return FuzzySystem([danger, core, space, energy], DESIRABILITY, rules)


def hunter_system() -> FuzzySystem:
    """Rule base for the Hunter: close in, shrink the prey's space, guard its food."""
    gap = LinguisticVariable(
        "gap",
        0,
        24,
        {
            "striking": Trapezoid(0, 0, 0, 3),
            "close": triangle(0, 3, 10),
            "distant": Trapezoid(3, 10, 24, 24),
        },
        unit="moves",
    )
    squeeze = LinguisticVariable("squeeze", 0, 0.6, SPACE_TERMS, unit="prey space")
    intercept = LinguisticVariable(
        "intercept",
        -12,
        12,
        {
            "ahead": Trapezoid(-12, -12, -6, 0),
            "level": triangle(-6, 0, 6),
            "behind": Trapezoid(0, 6, 12, 12),
        },
        unit="tiles",
    )
    hunger = LinguisticVariable(
        "prey_energy",
        0,
        1,
        {
            "starving": Trapezoid(0, 0, 0.2, 0.5),
            "fed": Trapezoid(0.2, 0.5, 1, 1),
        },
        unit="of max",
    )
    rules = [
        when(("gap", "striking"), then="excellent", rule_id="H1"),
        when(("gap", "close"), ("squeeze", "cornered"), then="excellent", rule_id="H2"),
        when(("gap", "close"), ("squeeze", "limited"), then="good", rule_id="H3"),
        when(("gap", "close"), ("squeeze", "open"), then="fair", rule_id="H4"),
        when(("gap", "distant"), then="poor", rule_id="H5"),
        when(("intercept", "ahead"), then="good", rule_id="H6"),
        when(("intercept", "behind"), ("gap", "distant"), then="avoid", rule_id="H7"),
        when(("squeeze", "cornered"), then="good", rule_id="H8"),
        when(("prey_energy", "starving"), ("intercept", "ahead"), then="excellent", rule_id="H9"),
        when(("prey_energy", "fed"), ("gap", "close"), then="good", rule_id="H10"),
        when(("squeeze", "open"), ("gap", "distant"), then="poor", rule_id="H11"),
    ]
    return FuzzySystem([gap, squeeze, intercept, hunger], DESIRABILITY, rules)


class FuzzyAgent(Agent):
    """Scores every legal action with a fuzzy rule base and plays the best one."""

    algorithm = AlgorithmId.FUZZY
    _systems: ClassVar[dict[Role, FuzzySystem]] = {}

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
        if role not in self._systems:
            self._systems[role] = survivor_system() if role is Role.SURVIVOR else hunter_system()
        self.system = self._systems[role]

    # --- Feature extraction ---------------------------------------------------

    def features(self, state: GameState, action: Action) -> dict[str, float]:
        """Crisp inputs describing the position reached by ``action``."""
        path = path_of(self.map, state, self.role, action)
        if path is None:
            raise ValueError(f"Illegal action {action.name}")
        return (
            self._survivor_features(state, path)
            if self.role is Role.SURVIVOR
            else self._hunter_features(state, path)
        )

    def _survivor_features(self, state: GameState, path: list[int]) -> dict[str, float]:
        gm, cfg = self.map, self.config
        cell = path[-1]
        d = gm.distance(state.hunter, cell)
        danger = d - 1 if state.pounce_cooldown == 0 and d >= 2 else d
        grabbed = sum(1 for c in path[1:] if c in state.cores)
        energy = state.energy - (cfg.dash_energy if len(path) == 3 else 0)
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
        actions = legal_actions(self.map, state)
        scored: list[tuple[float, float, Action, dict[str, float]]] = []
        for action in actions:
            feats = self.features(state, action)
            result = self.system.evaluate(feats)
            crisp = result.output
            urgent = feats.get("danger", 10.0) <= 2 or feats.get("gap", 10.0) <= 0
            if action.is_burst and not urgent:
                crisp -= self.params.burst_penalty
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
