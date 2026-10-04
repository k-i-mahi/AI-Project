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
        "Maps are procedurally generated, mirrored left/right and seeded: "
        "every match is reproducible.",
    ),
]

CONTROLS = [
    ("WASD / Arrows", "Move (when you control a side)"),
    ("Shift + direction", "Dash / Pounce two tiles"),
    ("Space", "Wait in place"),
    ("P  /  N", "Pause  /  step one move"),
    ("L  /  T  /  H", "Plans / territory / hunter-reach overlays"),
]


class HowToScene(Scene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.widgets.append(
            Button(
                pygame.Rect(60, 790, 160, 50),
                "Back",
                app.pop,
                theme.HUNTER,
                size=20,
                hotkey=pygame.K_ESCAPE,
            )
        )

    def draw_content(self, surface: pygame.Surface) -> None:
        theme.blit_text(surface, "HOW IT WORKS", (800, 70), "display", 40, theme.TEXT, "center")
        left = pygame.Rect(60, 130, 700, 640)
        right = pygame.Rect(800, 130, 740, 640)
        theme.panel(surface, left)
        theme.panel(surface, right)

        theme.blit_text(
            surface, "THE RULES", (left.left + 24, left.top + 20), "ui_bold", 18, theme.CORE
        )
        y = left.top + 56
        for title, body in RULES:
            theme.blit_text(surface, title, (left.left + 24, y), "ui_bold", 20, theme.TEXT)
            for line in theme.wrap(body, "ui", 18, left.width - 200):
                theme.blit_text(surface, line, (left.left + 170, y + 2), "ui", 18, theme.TEXT_DIM)
                y += 23
            y += 22

        y += 6
        theme.blit_text(surface, "CONTROLS", (left.left + 24, y), "ui_bold", 18, theme.CORE)
        y += 34
        for keys, what in CONTROLS:
            theme.blit_text(surface, keys, (left.left + 24, y), "mono", 15, theme.TEXT)
            theme.blit_text(surface, what, (left.left + 260, y), "ui", 18, theme.TEXT_DIM)
            y += 25

        theme.blit_text(
            surface, "THE BRAINS", (right.left + 24, right.top + 20), "ui_bold", 18, theme.CORE
        )
        y = right.top + 56
        for info in ALGORITHMS.values():
            theme.blit_text(surface, info.name, (right.left + 24, y), "ui_bold", 21, theme.TEXT)
            theme.blit_text(
                surface,
                info.family.upper(),
                (right.right - 24, y + 3),
                "ui_bold",
                14,
                theme.ACCENT,
                "topright",
            )
            y += 28
            for line in theme.wrap(info.description, "ui", 18, right.width - 48):
                theme.blit_text(surface, line, (right.left + 24, y), "ui", 18, theme.TEXT_DIM)
                y += 23
            y += 16
