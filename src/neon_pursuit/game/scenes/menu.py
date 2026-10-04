"""Title screen with a live attract-mode match running in the background."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from ... import __version__
from ...ai import AlgorithmId, create_agent
from ...engine import GameEvent, MatchConfig, Role, apply_action, generate_map, initial_state
from ...engine.rng import derive_seed
from ...presets import Difficulty, settings_for
from .. import theme
from ..controller import MatchSetup, Turn
from ..render import BoardView, Overlays
from ..widgets import Button
from .base import Scene

if TYPE_CHECKING:
    from ..app import App

DEMO_AREA = pygame.Rect(700, 150, 860, 620)


class MenuScene(Scene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        x, w, h, gap = 90, 440, 64, 14
        y = 330
        entries: list[tuple[str, str, Callable[[], None], theme.Color]] = [
            ("Watch AI Duel", "MCTS Hunter vs Fuzzy Survivor", self.watch, theme.ACCENT),
            ("Play as Survivor", "Outsmart an MCTS Hunter", self.play_survivor, theme.SURVIVOR),
            ("Play as Hunter", "Corner a Fuzzy-logic Survivor", self.play_hunter, theme.HUNTER),
            ("Custom Match", "Pick algorithms, difficulty and map", self.custom, theme.ACCENT),
            ("Benchmark Lab", "Run AI-vs-AI tournaments", self.benchmark, theme.CORE),
            ("How It Works", "Rules and algorithms explained", self.howto, theme.TEXT_DIM),
        ]
        for i, (label, sub, cb, color) in enumerate(entries):
            rect = pygame.Rect(x, y + i * (h + gap), w, h)
            self.widgets.append(Button(rect, label, cb, color, subtitle=sub, size=24))
        self.widgets.append(
            Button(
                pygame.Rect(x, y + len(entries) * (h + gap) + 6, 140, 44),
                "Quit",
                app.quit,
                theme.HUNTER,
                size=20,
            )
        )
        self._demo_seed = 41
        self._start_demo()

    # --- Navigation -----------------------------------------------------------

    def _launch(self, hunter: AlgorithmId | None, survivor: AlgorithmId | None) -> None:
        from .match import MatchScene

        settings = settings_for(Difficulty.NORMAL)
        setup = MatchSetup(hunter, survivor, MatchConfig(), settings, settings)
        self.app.push(MatchScene(self.app, setup))

    def watch(self) -> None:
        self._launch(AlgorithmId.MCTS, AlgorithmId.FUZZY)

    def play_survivor(self) -> None:
        self._launch(AlgorithmId.MCTS, None)

    def play_hunter(self) -> None:
        self._launch(None, AlgorithmId.FUZZY)

    def custom(self) -> None:
        from .setup import SetupScene

        self.app.push(SetupScene(self.app))

    def benchmark(self) -> None:
        from .benchmark import BenchmarkScene

        self.app.push(BenchmarkScene(self.app))

    def howto(self) -> None:
        from .howto import HowToScene

        self.app.push(HowToScene(self.app))

    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.quit()

    # --- Attract mode -------------------------------------------------------------

    def _start_demo(self) -> None:
        self._demo_seed += 1
        cfg = MatchConfig(seed=self._demo_seed)
        self.demo_cfg = cfg
        self.demo_map = generate_map(cfg)
        self.demo_state = initial_state(self.demo_map, cfg)
        self.demo_agents = {
            Role.HUNTER: create_agent(
                AlgorithmId.FUZZY, Role.HUNTER, self.demo_map, cfg, derive_seed(cfg.seed, 1)
            ),
            Role.SURVIVOR: create_agent(
                AlgorithmId.FUZZY, Role.SURVIVOR, self.demo_map, cfg, derive_seed(cfg.seed, 2)
            ),
        }
        self.demo_view = BoardView(self.demo_map, cfg, DEMO_AREA)
        self.demo_view.reset(self.demo_state)
        self.demo_timer = 0.0
        self.demo_end = 0.0

    def update(self, dt: float) -> None:
        super().update(dt)
        view = self.demo_view
        view.update(dt)
        if self.demo_state.is_terminal:
            self.demo_end += dt
            if self.demo_end > 2.5:
                self._start_demo()
            return
        self.demo_timer += dt
        if not view.animating and self.demo_timer > 0.05:
            self.demo_timer = 0.0
            before = self.demo_state
            decision = self.demo_agents[before.to_move].decide(before)
            events: list[GameEvent] = []
            self.demo_state = apply_action(
                self.demo_map, self.demo_cfg, before, decision.action, events
            )
            view.animate(
                Turn(before.to_move, decision.action, before, self.demo_state, events, decision),
                0.2,
            )

    def draw_content(self, surface: pygame.Surface) -> None:
        self.demo_view.draw(surface, self.demo_state, Overlays(plans=False), {})
        veil = pygame.Surface(DEMO_AREA.inflate(40, 40).size, pygame.SRCALPHA)
        veil.fill((6, 8, 20, 120))
        surface.blit(veil, DEMO_AREA.inflate(40, 40).topleft)
        theme.blit_text(
            surface,
            "LIVE DEMO · FUZZY vs FUZZY",
            (DEMO_AREA.right, DEMO_AREA.bottom + 30),
            "ui_bold",
            16,
            theme.TEXT_FAINT,
            "topright",
        )

        t = self.app.time
        theme.blit_glow(surface, (330, 175), 300, theme.ACCENT, 0.32 + 0.06 * math.sin(t * 1.5))
        theme.blit_text(surface, "NEON", (86, 92), "display", 92, theme.SURVIVOR)
        theme.blit_text(surface, "PURSUIT", (86, 186), "display", 92, theme.HUNTER)
        theme.blit_text(
            surface,
            "Hunter vs Survivor  ·  an adversarial AI arena",
            (92, 292),
            "ui",
            22,
            theme.TEXT_DIM,
        )
        theme.blit_text(
            surface, f"v{__version__}", (1576, 884), "mono", 13, theme.TEXT_FAINT, "bottomright"
        )
