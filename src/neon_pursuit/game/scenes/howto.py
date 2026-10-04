"""Rules and algorithm explainer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from ...ai import ALGORITHMS
from .. import theme
from ..widgets import Button
from .base import Scene

if TYPE_CHECKING:
    from ..app import App

RULES = [
    (
        "Turns",
        "The Survivor moves, then the Hunter moves — one round. "
        "Moves are one tile N/E/S/W, or wait.",
    ),
    (
        "Bursts",
        "Survivor DASH and Hunter POUNCE move two tiles in a straight line, "
        "then go on cooldown. A dash costs 3 energy.",
    ),
    (
        "Abilities",
        "Blink Dash can leap over one wall tile. EMP pulse (Hunter within 3 tiles) "
        "stuns the Hunter for 3 turns; 18-round cooldown, costs 4 energy.",
    ),
    (
        "Energy",
        "The Survivor loses 1 energy per round. Each core restores 15. At 0 energy it collapses.",
    ),
    (
        "Hunter wins",
        "by stepping onto the Survivor (capture) or by starving it — "
        "guarding cores is a valid strategy.",
    ),
    (
        "Survivor wins",
        "by collecting the target number of cores, or by lasting until the round limit.",
    ),
    (
        "Fairness",
        "Maps are generated from a seed with mirrored walls and random, well-separated "
        "spawns. R replays the same map; M rolls a new one.",
    ),
]

CONTROLS = [
    ("WASD / Arrows", "move"),
    ("Shift + dir", "Dash / Pounce"),
    ("Space", "wait"),
    ("E", "EMP pulse"),
    ("P / N", "pause / step"),
    ("L / T / H", "overlays"),
    ("+ / -", "speed"),
    ("R / M", "rematch / new map"),
    ("F11", "fullscreen"),
]

GA_NOTE = (
    "Genetic Algorithm: tunes the fuzzy controllers' membership functions and rule "
    "weights offline (neon-pursuit tune)."
)

RULES_PANEL = pygame.Rect(60, 118, 700, 482)
BRAINS_PANEL = pygame.Rect(800, 118, 740, 482)
CONTROLS_PANEL = pygame.Rect(60, 618, 1480, 140)
BODY, LINE = 17, 21  # body font size and line height


class HowToScene(Scene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.widgets.append(
            Button(
                pygame.Rect(60, 792, 160, 50),
                "Back",
                app.pop,
                theme.HUNTER,
                size=20,
                hotkey=pygame.K_ESCAPE,
            )
        )
        #: Bottom y reached by each panel's content (checked by tests: no overflow).
        self.content_bottom: dict[str, int] = {}

    def draw_content(self, surface: pygame.Surface) -> None:
        theme.blit_text(surface, "HOW IT WORKS", (800, 66), "display", 40, theme.TEXT, "center")
        for rect in (RULES_PANEL, BRAINS_PANEL, CONTROLS_PANEL):
            theme.panel(surface, rect)
        self.content_bottom = {
            "rules": self._draw_rules(surface, RULES_PANEL),
            "brains": self._draw_brains(surface, BRAINS_PANEL),
            "controls": self._draw_controls(surface, CONTROLS_PANEL),
        }

    @staticmethod
    def _heading(surface: pygame.Surface, rect: pygame.Rect, text: str) -> int:
        theme.blit_text(surface, text, (rect.left + 24, rect.top + 16), "ui_bold", 18, theme.CORE)
        return rect.top + 48

    def _draw_rules(self, surface: pygame.Surface, rect: pygame.Rect) -> int:
        y = self._heading(surface, rect, "THE RULES")
        text_x = rect.left + 160
        width = rect.right - 24 - text_x
        for title, body in RULES:
            theme.blit_text(surface, title, (rect.left + 24, y), "ui_bold", 19, theme.TEXT)
            for line in theme.wrap(body, "ui", BODY, width):
                theme.blit_text(surface, line, (text_x, y + 2), "ui", BODY, theme.TEXT_DIM)
                y += LINE
            y += 13
        return y

    def _draw_brains(self, surface: pygame.Surface, rect: pygame.Rect) -> int:
        y = self._heading(surface, rect, "THE BRAINS")
        width = rect.width - 48
        for info in ALGORITHMS.values():
            theme.blit_text(surface, info.name, (rect.left + 24, y), "ui_bold", 20, theme.TEXT)
            theme.blit_text(
                surface,
                info.family.upper(),
                (rect.right - 24, y + 3),
                "ui_bold",
                14,
                theme.ACCENT,
                "topright",
            )
            y += 26
            for line in theme.wrap(info.description, "ui", BODY, width):
                theme.blit_text(surface, line, (rect.left + 24, y), "ui", BODY, theme.TEXT_DIM)
                y += LINE
            y += 10
        y += 4
        for line in theme.wrap(GA_NOTE, "ui", BODY, width):
            theme.blit_text(surface, line, (rect.left + 24, y), "ui", BODY, theme.CORE_SOFT)
            y += LINE
        return y

    def _draw_controls(self, surface: pygame.Surface, rect: pygame.Rect) -> int:
        y0 = self._heading(surface, rect, "CONTROLS")
        columns, rows = 3, 3
        col_w = (rect.width - 48) // columns
        bottom = y0
        for i, (keys, what) in enumerate(CONTROLS):
            col, row = divmod(i, rows)
            x = rect.left + 24 + col * col_w
            y = y0 + row * 24
            theme.blit_text(surface, keys, (x, y), "mono", 14, theme.TEXT)
            theme.blit_text(surface, what, (x + 170, y - 1), "ui", 16, theme.TEXT_DIM)
            bottom = max(bottom, y + 22)
        return bottom
