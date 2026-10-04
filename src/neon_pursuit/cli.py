"""Command-line entry point.

Examples::

    neon-pursuit                                   # open the game menu
    neon-pursuit play --hunter mcts --survivor human
    neon-pursuit simulate --hunter mcts --survivor fuzzy --seed 7 --render
    neon-pursuit benchmark --games 20 --hunters mcts fuzzy --survivors fuzzy greedy
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .ai import AlgorithmId, create_agent
from .engine import GameMap, GameState, MatchConfig, Role, apply_action, generate_map, initial_state
from .engine.rng import derive_seed
from .presets import Difficulty, settings_for

_ALGOS = [a.value for a in AlgorithmId]


def _controller(value: str) -> AlgorithmId | None:
    if value == "human":
        return None
    try:
        return AlgorithmId(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"choose from {[*_ALGOS, 'human']}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neon-pursuit",
        description="Neon Pursuit — Hunter vs Survivor, an adversarial AI arena.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--window", default="1440x810", help="window size, e.g. 1920x1080")
    sub = parser.add_subparsers(dest="command")

    play = sub.add_parser("play", help="start a match directly in the game window")
    play.add_argument("--hunter", type=_controller, default=AlgorithmId.MCTS, metavar="ALGO|human")
    play.add_argument(
        "--survivor", type=_controller, default=AlgorithmId.FUZZY, metavar="ALGO|human"
    )
    play.add_argument(
        "--difficulty", type=Difficulty, choices=list(Difficulty), default=Difficulty.NORMAL
    )
    play.add_argument("--seed", type=int, default=2026)
    play.add_argument("--cores", type=int, default=8, help="cores the Survivor needs to win")

    sim = sub.add_parser("simulate", help="play one AI-vs-AI match in the terminal")
    sim.add_argument(
        "--hunter", type=AlgorithmId, choices=list(AlgorithmId), default=AlgorithmId.MCTS
    )
    sim.add_argument(
        "--survivor", type=AlgorithmId, choices=list(AlgorithmId), default=AlgorithmId.FUZZY
    )
    sim.add_argument(
        "--difficulty", type=Difficulty, choices=list(Difficulty), default=Difficulty.NORMAL
    )
    sim.add_argument("--seed", type=int, default=2026)
    sim.add_argument("--render", action="store_true", help="print the final board as ASCII art")

    bench = sub.add_parser("benchmark", help="run a headless tournament and export the results")
    bench.add_argument(
        "--hunters",
        nargs="+",
        type=AlgorithmId,
        choices=list(AlgorithmId),
        default=list(AlgorithmId),
    )
    bench.add_argument(
        "--survivors",
        nargs="+",
        type=AlgorithmId,
        choices=list(AlgorithmId),
        default=list(AlgorithmId),
    )
    bench.add_argument("--games", type=int, default=10, help="games per matchup")
    bench.add_argument(
        "--difficulty", type=Difficulty, choices=list(Difficulty), default=Difficulty.EASY
    )
    bench.add_argument("--seed", type=int, default=1000, help="seed of the first game")
    bench.add_argument(
        "--workers", type=int, default=None, help="parallel processes (default: CPUs - 1)"
    )
    bench.add_argument("--out", type=Path, default=Path("results"), help="output directory")
    return parser


def ascii_board(game_map: GameMap, state: GameState) -> str:
    rows = []
    for y in range(game_map.height):
        row = []
        for x in range(game_map.width):
            c = game_map.cell(x, y)
            if c == state.hunter:
                row.append("H")
            elif c == state.survivor:
                row.append("S")
            elif c in state.cores:
                row.append("*")
            else:
                row.append("#" if game_map.is_wall(c) else "·")
        rows.append(" ".join(row))
    return "\n".join(rows)


def cmd_simulate(args: argparse.Namespace) -> int:
    cfg = MatchConfig(seed=args.seed)
    game_map = generate_map(cfg)
    settings = settings_for(args.difficulty)
    agents = {
        Role.HUNTER: create_agent(
            args.hunter, Role.HUNTER, game_map, cfg, derive_seed(cfg.seed, 11), settings
        ),
        Role.SURVIVOR: create_agent(
            args.survivor, Role.SURVIVOR, game_map, cfg, derive_seed(cfg.seed, 22), settings
        ),
    }
    state = initial_state(game_map, cfg)
    print(
        f"Neon Pursuit · {args.hunter.value} (Hunter) vs {args.survivor.value} (Survivor)"
        f" · seed {cfg.seed}"
    )
    start = time.perf_counter()
    while not state.is_terminal:
        role = state.to_move
        decision = agents[role].decide(state)
        state = apply_action(game_map, cfg, state, decision.action)
        if role is Role.HUNTER and state.round % 10 == 0:
            print(
                f"  round {state.round:3d} · cores {state.cores_collected}/{cfg.cores_to_win}"
                f" · energy {state.energy:2d}"
            )
    winner = "HUNTER" if state.status.value == "hunter_win" else "SURVIVOR"
    reason = state.win_reason.value if state.win_reason else "?"
    print(
        f"\n{winner} wins ({reason}) after {state.round} rounds, {state.cores_collected} cores "
        f"[{time.perf_counter() - start:.1f}s]"
    )
    if args.render:
        print()
        print(ascii_board(game_map, state))
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark.report import markdown_table, write_reports
    from .benchmark.runner import build_specs, run_tournament, summarise

    pairs = [(h, s) for h in args.hunters for s in args.survivors]
    specs = build_specs(
        pairs, args.games, MatchConfig(seed=args.seed), settings_for(args.difficulty)
    )
    print(f"Running {len(specs)} matches ({len(pairs)} matchups × {args.games} games)…")
    start = time.perf_counter()

    def progress(_result: object, done: int, total: int) -> None:
        bar = "█" * int(30 * done / total)
        print(f"\r  [{bar:<30}] {done}/{total}", end="", flush=True)

    results = run_tournament(specs, workers=args.workers, on_result=progress)
    print(f"\nFinished in {time.perf_counter() - start:.1f}s\n")
    print(markdown_table(summarise(results)))
    for path in write_reports(results, args.out):
        print(f"wrote {path}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        width, height = (int(v) for v in args.window.lower().split("x"))
    except ValueError:
        print("--window must look like 1440x810", file=sys.stderr)
        return 2
    from .game.app import App
    from .game.scenes.menu import MenuScene

    app = App((width, height))
    menu = MenuScene(app)
    if args.command == "play":
        from .game.controller import MatchSetup
        from .game.scenes.match import MatchScene

        settings = settings_for(args.difficulty)
        cfg = MatchConfig(seed=args.seed, cores_to_win=args.cores)
        app.push(menu)
        app.run(MatchScene(app, MatchSetup(args.hunter, args.survivor, cfg, settings, settings)))
    else:
        app.run(menu)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "simulate":
        return cmd_simulate(args)
    if args.command == "benchmark":
        return cmd_benchmark(args)
    return cmd_gui(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
