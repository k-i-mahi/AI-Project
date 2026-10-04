"""Render the main screens headlessly and save PNGs to docs/images/.

Usage:  python scripts/capture_screenshots.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from neon_pursuit.ai import AlgorithmId
from neon_pursuit.engine import MatchConfig
from neon_pursuit.game.app import HEIGHT, WIDTH, App
from neon_pursuit.game.controller import MatchSetup
from neon_pursuit.game.scenes.base import Scene
from neon_pursuit.game.scenes.benchmark import BenchmarkScene
from neon_pursuit.game.scenes.howto import HowToScene
from neon_pursuit.game.scenes.match import MatchScene
from neon_pursuit.game.scenes.menu import MenuScene
from neon_pursuit.game.scenes.setup import SetupMode, SetupScene
from neon_pursuit.presets import Difficulty, settings_for

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def frames(app: App, n: int) -> None:
    for _ in range(n):
        app.step(1 / 60)


def save(app: App, name: str) -> None:
    app.scene.draw(app.canvas)
    path = OUT / name
    pygame.image.save(app.canvas, str(path))
    print(f"saved {path}")


def show(app: App, scene: Scene) -> None:
    app.scenes = [scene]


def run_match(app: App, setup: MatchSetup, turns: int, name: str, overlays: str = "") -> None:
    scene = MatchScene(app, setup)
    scene.speed = 8.0
    show(app, scene)
    for flag in overlays:
        scene.toggles[flag].flip()
    guard = 0
    while len(scene.controller.history) < turns and not scene.controller.is_over and guard < 20_000:
        app.step(1 / 60)
        guard += 1
    scene.speed = 1.0
    frames(app, 80 if scene.controller.is_over else 20)
    save(app, name)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = App((WIDTH, HEIGHT), headless=True)

    menu = MenuScene(app)
    show(app, menu)
    frames(app, 240)
    save(app, "menu.png")

    setup_scene = SetupScene(app, SetupMode.DUEL)
    setup_scene._set_seed(2026)
    show(app, setup_scene)
    frames(app, 10)
    save(app, "setup.png")

    show(app, HowToScene(app))
    frames(app, 5)
    save(app, "howto.png")

    normal = settings_for(Difficulty.NORMAL)
    run_match(
        app,
        MatchSetup(AlgorithmId.MCTS, AlgorithmId.FUZZY, MatchConfig(seed=2026), normal, normal),
        38,
        "match_mcts_vs_fuzzy.png",
    )
    run_match(
        app,
        MatchSetup(AlgorithmId.FUZZY, AlgorithmId.MCTS, MatchConfig(seed=77), normal, normal),
        30,
        "match_overlays.png",
        overlays="T",
    )
    run_match(
        app,
        MatchSetup(AlgorithmId.MINIMAX, AlgorithmId.FUZZY, MatchConfig(seed=5), normal, normal),
        400,
        "match_end.png",
    )
    bench = BenchmarkScene(app)
    show(app, bench)
    bench.games.set_value(4)
    bench.run()
    while bench.running or bench.futures:
        app.step(1 / 30)
    frames(app, 5)
    save(app, "benchmark.png")
    bench.on_exit()

    app.brain.shutdown()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
