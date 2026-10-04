"""Match setup: pick the algorithm (and difficulty) for each side before playing."""

from __future__ import annotations

import random
from enum import Enum
from typing import TYPE_CHECKING

import pygame

from ...ai import ALGORITHMS, AgentSettings, AlgorithmId
from ...engine import MatchConfig, Role, generate_map, initial_state
from ...presets import Difficulty, settings_for
from .. import theme
from ..controller import MatchSetup
from ..render import BoardView, Overlays
from ..widgets import Button, Selector
from .base import Scene

if TYPE_CHECKING:
    from ..app import App

AI_CONTROLLERS: list[tuple[AlgorithmId | None, str]] = [
    (AlgorithmId.MCTS, "Monte Carlo Tree Search"),
    (AlgorithmId.FUZZY, "Fuzzy Logic"),
    (AlgorithmId.MINIMAX, "Minimax (Alpha-Beta)"),
    (AlgorithmId.GREEDY, "Greedy"),
    (AlgorithmId.RANDOM, "Random"),
]
CONTROLLERS: list[tuple[AlgorithmId | None, str]] = [*AI_CONTROLLERS, (None, "Human (you)")]


class SetupMode(Enum):
    """Which sides the player may configure."""

    DUEL = ("AI DUEL", "Pick an algorithm for each side, then watch them fight.")
    PLAY_SURVIVOR = ("PLAY AS SURVIVOR", "You are the Survivor. Choose the AI that hunts you.")
    PLAY_HUNTER = ("PLAY AS HUNTER", "You are the Hunter. Choose the AI you will chase.")
    CUSTOM = ("CUSTOM MATCH", "Choose a brain for each side. Any algorithm can play either role.")

    @property
    def title(self) -> str:
        return self.value[0]

    @property
    def subtitle(self) -> str:
        return self.value[1]

    def human_role(self) -> Role | None:
        if self is SetupMode.PLAY_SURVIVOR:
            return Role.SURVIVOR
        if self is SetupMode.PLAY_HUNTER:
            return Role.HUNTER
        return None


DIFFICULTIES = [(Difficulty.EASY, "Easy"), (Difficulty.NORMAL, "Normal"), (Difficulty.HARD, "Hard")]
CORES = [(6, "6 cores"), (8, "8 cores"), (10, "10 cores"), (12, "12 cores")]

HUNTER_CARD = pygame.Rect(60, 150, 440, 560)
SURVIVOR_CARD = pygame.Rect(1100, 150, 440, 560)
PREVIEW_AREA = pygame.Rect(540, 190, 520, 380)


class SetupScene(Scene):
    def __init__(self, app: App, mode: SetupMode = SetupMode.CUSTOM) -> None:
        super().__init__(app)
        self.mode = mode
        self.human = mode.human_role()
        self.seed = random.randrange(10_000)  # new map and spawns every time
        self.controller: dict[Role, Selector[AlgorithmId | None]] = {}
        self.difficulty: dict[Role, Selector[Difficulty]] = {}
        options = CONTROLLERS if mode is SetupMode.CUSTOM else AI_CONTROLLERS
        for role, card, default in (
            (Role.HUNTER, HUNTER_CARD, 0),
            (Role.SURVIVOR, SURVIVOR_CARD, 1),
        ):
            if role is self.human:
                continue
            color = theme.ROLE_COLOR[role]
            sel = Selector(
                pygame.Rect(card.left + 24, card.top + 110, card.width - 48, 50),
                options,
                default,
                color,
            )
            diff = Selector(
                pygame.Rect(card.left + 24, card.top + 210, card.width - 48, 46),
                DIFFICULTIES,
                1,
                color,
            )
            self.controller[role] = sel
            self.difficulty[role] = diff
            self.widgets += [sel, diff]

        self.cores = Selector(pygame.Rect(600, 640, 190, 46), CORES, 2, theme.CORE)
        self.widgets += [
            self.cores,
            Button(
                pygame.Rect(810, 640, 90, 46),
                "‹ Map",
                lambda: self._set_seed(self.seed - 1),
                theme.ACCENT,
                size=18,
            ),
            Button(
                pygame.Rect(910, 640, 90, 46),
                "Map ›",
                lambda: self._set_seed(self.seed + 1),
                theme.ACCENT,
                size=18,
            ),
            Button(
                pygame.Rect(600, 700, 400, 42),
                "Random map",
                self._random_seed,
                theme.ACCENT,
                size=18,
            ),
            Button(
                pygame.Rect(620, 770, 360, 70),
                "START MATCH",
                self.start,
                theme.SUCCESS,
                size=28,
                hotkey=pygame.K_RETURN,
            ),
            Button(
                pygame.Rect(60, 790, 160, 50),
                "Back",
                app.pop,
                theme.HUNTER,
                size=20,
                hotkey=pygame.K_ESCAPE,
            ),
        ]
        self._set_seed(self.seed)

    def _set_seed(self, seed: int) -> None:
        self.seed = max(0, seed)
        cfg = MatchConfig(seed=self.seed)
        game_map = generate_map(cfg)
        self.preview = BoardView(game_map, cfg, PREVIEW_AREA)
        self.preview_state = initial_state(game_map, cfg)
        self.preview.reset(self.preview_state)

    def _random_seed(self) -> None:
        self._set_seed(random.randrange(10_000))

    def start(self) -> None:
        from .match import MatchScene

        config = MatchConfig(seed=self.seed, cores_to_win=self.cores.value)
        setup = MatchSetup(
            hunter=self._algorithm(Role.HUNTER),
            survivor=self._algorithm(Role.SURVIVOR),
            config=config,
            hunter_settings=self._settings(Role.HUNTER),
            survivor_settings=self._settings(Role.SURVIVOR),
        )
        self.app.replace(MatchScene(self.app, setup))

    def _algorithm(self, role: Role) -> AlgorithmId | None:
        return None if role is self.human else self.controller[role].value

    def _settings(self, role: Role) -> AgentSettings:
        if role is self.human:
            return settings_for(Difficulty.NORMAL)
        return settings_for(self.difficulty[role].value)

    def update(self, dt: float) -> None:
        super().update(dt)
        self.preview.update(dt)

    def draw_content(self, surface: pygame.Surface) -> None:
        theme.blit_text(surface, self.mode.title, (800, 70), "display", 40, theme.TEXT, "center")
        theme.blit_text(
            surface,
            self.mode.subtitle,
            (800, 118),
            "ui",
            20,
            theme.TEXT_DIM,
            "center",
        )
        for role, card in ((Role.HUNTER, HUNTER_CARD), (Role.SURVIVOR, SURVIVOR_CARD)):
            color = theme.ROLE_COLOR[role]
            theme.panel(surface, card, edge=theme.scale(color, 0.7))
            theme.blit_glow(surface, (card.centerx, card.top), 200, color, 0.18)
            theme.blit_text(
                surface, role.value.upper(), (card.left + 24, card.top + 24), "display", 30, color
            )
            goal = (
                "Catch the Survivor or starve it out"
                if role is Role.HUNTER
                else "Collect cores, stay alive, escape"
            )
            theme.blit_text(
                surface, goal, (card.left + 24, card.top + 66), "ui", 18, theme.TEXT_DIM
            )
            if role is self.human:
                you = pygame.Rect(card.left + 24, card.top + 110, card.width - 48, 50)
                pygame.draw.rect(surface, theme.scale(color, 0.2), you, border_radius=10)
                pygame.draw.rect(surface, color, you, 1, border_radius=10)
                theme.blit_text(surface, "YOU", you.center, "display", 24, color, "center")
            else:
                theme.blit_text(
                    surface,
                    "DIFFICULTY (search budget)",
                    (card.left + 24, card.top + 182),
                    "ui_bold",
                    15,
                    theme.TEXT_DIM,
                )
            algorithm = self._algorithm(role)
            points: tuple[str, ...]
            if algorithm is None:
                desc = (
                    "You take control. Arrow keys / WASD to move, "
                    "Shift for a burst move, Space to wait."
                )
                family, points = (
                    "Human",
                    ("Click a highlighted ring to move there", "Esc returns to the menu"),
                )
            else:
                info = ALGORITHMS[algorithm]
                desc, family, points = info.description, info.family, info.highlights
            theme.blit_text(
                surface, family.upper(), (card.left + 24, card.top + 290), "ui_bold", 16, color
            )
            y = card.top + 318
            for line in theme.wrap(desc, "ui", 19, card.width - 48):
                theme.blit_text(surface, line, (card.left + 24, y), "ui", 19, theme.TEXT)
                y += 25
            y += 18
            heading = "TIPS" if algorithm is None else "HOW IT DECIDES"
            theme.blit_text(surface, heading, (card.left + 24, y), "ui_bold", 15, theme.TEXT_DIM)
            y += 26
            for point in points:
                pygame.draw.circle(surface, color, (card.left + 30, y + 11), 3)
                theme.blit_text(surface, point, (card.left + 44, y), "ui", 18, theme.TEXT)
                y += 26

        self.preview.draw(surface, self.preview_state, Overlays(plans=False), {})
        theme.blit_text(
            surface,
            f"MAP SEED {self.seed}  ·  random spawns",
            (PREVIEW_AREA.centerx, PREVIEW_AREA.bottom + 20),
            "mono",
            16,
            theme.TEXT_DIM,
            "center",
        )
        theme.blit_text(surface, "WIN CONDITION", (600, 618), "ui_bold", 15, theme.TEXT_DIM)
