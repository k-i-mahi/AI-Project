"""Headless smoke tests for every screen (SDL dummy video driver)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

pygame = pytest.importorskip("pygame")

from neon_pursuit.ai import AlgorithmId  # noqa: E402
from neon_pursuit.engine import Action, MatchConfig  # noqa: E402
from neon_pursuit.game.app import HEIGHT, WIDTH, App  # noqa: E402
from neon_pursuit.game.controller import MatchSetup  # noqa: E402
from neon_pursuit.game.scenes.benchmark import BenchmarkScene  # noqa: E402
from neon_pursuit.game.scenes.howto import HowToScene  # noqa: E402
from neon_pursuit.game.scenes.match import MatchScene  # noqa: E402
from neon_pursuit.game.scenes.menu import MenuScene  # noqa: E402
from neon_pursuit.game.scenes.setup import SetupMode, SetupScene  # noqa: E402
from neon_pursuit.presets import Difficulty, settings_for  # noqa: E402


@pytest.fixture
def app() -> Iterator[App]:
    application = App((WIDTH, HEIGHT), headless=True)
    yield application
    application.brain.shutdown()


def _run(app: App, frames: int) -> None:
    for _ in range(frames):
        app.step(1 / 60)


def _key(app: App, key: int, mod: int = 0) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))
    app.step(1 / 60)


def test_menu_runs_attract_demo(app: App) -> None:
    menu = MenuScene(app)
    app.scenes = [menu]
    _run(app, 120)
    assert menu.demo_state.round > 0 or menu.demo_state.is_terminal


@pytest.mark.parametrize("mode", list(SetupMode))
def test_setup_modes_start_matches(app: App, mode: SetupMode) -> None:
    setup = SetupScene(app, mode)
    app.scenes = [MenuScene(app), setup]
    _run(app, 3)
    setup.start()
    scene = app.scene
    assert isinstance(scene, MatchScene)
    human = mode.human_role()
    if human is not None:
        assert scene.setup.controller(human) is None
    if mode is SetupMode.DUEL:
        assert scene.setup.hunter is not None and scene.setup.survivor is not None


def test_ai_match_plays_to_the_end(app: App) -> None:
    easy = settings_for(Difficulty.EASY)
    setup = MatchSetup(AlgorithmId.GREEDY, AlgorithmId.FUZZY, MatchConfig(seed=4), easy, easy)
    scene = MatchScene(app, setup)
    app.scenes = [scene]
    scene.speed = 8.0
    for flag in "LTH":
        scene.toggles[flag].flip()
    guard = 0
    while not scene.controller.is_over and guard < 30_000:
        app.step(1 / 60)
        guard += 1
    assert scene.controller.is_over
    _run(app, 60)  # end-of-match overlay
    _key(app, pygame.K_r)  # rematch
    assert not scene.controller.is_over


def test_human_controls(app: App) -> None:
    setup = MatchSetup(AlgorithmId.RANDOM, None, MatchConfig(seed=9))
    scene = MatchScene(app, setup)
    app.scenes = [scene]
    _run(app, 2)
    assert scene.controller.is_human_turn()
    _key(app, pygame.K_SPACE)  # wait
    assert scene.controller.history[-1].action is Action.WAIT
    _key(app, pygame.K_p)
    assert scene.paused


def test_static_screens_render(app: App) -> None:
    for scene in (HowToScene(app), BenchmarkScene(app)):
        app.scenes = [scene]
        _run(app, 3)
