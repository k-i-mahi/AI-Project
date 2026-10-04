"""Algorithm catalogue and agent factory."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..engine import GameMap, MatchConfig, Role
from .base import Agent, AlgorithmId
from .fuzzy import FuzzyAgent, FuzzyParams
from .mcts import MctsAgent, MctsParams
from .minimax import MinimaxAgent, MinimaxParams
from .simple import GreedyAgent, RandomAgent


@dataclass(slots=True, frozen=True)
class AlgorithmInfo:
    algorithm: AlgorithmId
    name: str
    short: str
    family: str
    description: str
    #: Short bullet points on how the algorithm decides (shown in the UI).
    highlights: tuple[str, ...] = ()


ALGORITHMS: dict[AlgorithmId, AlgorithmInfo] = {
    AlgorithmId.MCTS: AlgorithmInfo(
        AlgorithmId.MCTS,
        "Monte Carlo Tree Search",
        "MCTS",
        "Stochastic search",
        "Builds a search tree from hundreds of simulated futures, balancing "
        "exploration and exploitation with the UCT formula.",
        (
            "Selection by UCT: mean value + c * sqrt(ln N / n)",
            "Epsilon-greedy rollouts, heuristic cut-off",
            "Plays the most-visited move",
        ),
    ),
    AlgorithmId.FUZZY: AlgorithmInfo(
        AlgorithmId.FUZZY,
        "Fuzzy Logic Controller",
        "FUZZY",
        "Soft computing",
        "Turns crisp measurements into linguistic terms (danger is 'near', space "
        "is 'open') and reasons with human-readable IF-THEN rules.",
        (
            "4 inputs, 3 terms each, 11-13 rules",
            "Mamdani min/max inference",
            "Centroid defuzzification scores each move",
        ),
    ),
    AlgorithmId.MINIMAX: AlgorithmInfo(
        AlgorithmId.MINIMAX,
        "Minimax + Alpha-Beta",
        "MINIMAX",
        "Adversarial search",
        "Assumes a perfect opponent and searches the game tree depth-first, "
        "pruning branches that cannot change the decision.",
        (
            "Negamax with alpha-beta pruning",
            "Iterative deepening under a time budget",
            "Transposition table with bound flags",
        ),
    ),
    AlgorithmId.GREEDY: AlgorithmInfo(
        AlgorithmId.GREEDY,
        "Greedy Pathfinder",
        "GREEDY",
        "Baseline",
        "One-ply lookahead on shortest-path distances: chase or flee, nothing more.",
        ("Precomputed all-pairs BFS distances", "No lookahead beyond one move"),
    ),
    AlgorithmId.RANDOM: AlgorithmInfo(
        AlgorithmId.RANDOM,
        "Random Walker",
        "RANDOM",
        "Baseline",
        "Uniformly random legal moves. Every real algorithm should beat it.",
        ("The performance floor for benchmarks",),
    ),
}


@dataclass(slots=True)
class AgentSettings:
    """Tunable parameters for every algorithm (only the relevant one is used)."""

    mcts: MctsParams = field(default_factory=MctsParams)
    minimax: MinimaxParams = field(default_factory=MinimaxParams)
    fuzzy: FuzzyParams = field(default_factory=FuzzyParams)


def create_agent(
    algorithm: AlgorithmId,
    role: Role,
    game_map: GameMap,
    config: MatchConfig,
    seed: int = 0,
    settings: AgentSettings | None = None,
) -> Agent:
    s = settings or AgentSettings()
    match algorithm:
        case AlgorithmId.MCTS:
            return MctsAgent(role, game_map, config, seed, s.mcts)
        case AlgorithmId.FUZZY:
            return FuzzyAgent(role, game_map, config, seed, s.fuzzy)
        case AlgorithmId.MINIMAX:
            return MinimaxAgent(role, game_map, config, seed, s.minimax)
        case AlgorithmId.GREEDY:
            return GreedyAgent(role, game_map, config, seed)
        case AlgorithmId.RANDOM:
            return RandomAgent(role, game_map, config, seed)
    raise ValueError(f"Unknown algorithm: {algorithm}")  # pragma: no cover
