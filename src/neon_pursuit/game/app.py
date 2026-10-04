"""Application shell: window, scaling, scene stack and the main loop."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

from .. import __version__
from . import theme
from .brain import Brain

if TYPE_CHECKING:
    from .scenes.base import Scene

#: Logical resolution. Everything is laid out at this size, then scaled to the window.
WIDTH, HEIGHT = 1600, 900
FPS = 60


class App:
    def __init__(self, window_size: tuple[int, int] = (1440, 810), headless: bool = False) -> None:
        pygame.init()
        pygame.display.set_caption(f"Neon Pursuit {__version__} — AI Arena")
        self.headless = headless
        self.fullscreen = False
        self.windowed_size = window_size
        flags = 0 if headless else pygame.RESIZABLE
        self.window = pygame.display.set_mode(window_size, flags)
        self.canvas = pygame.Surface((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.brain = Brain(use_process=not headless)
        self.scenes: list[Scene] = []
        self.running = True
        self.time = 0.0
        rng = random.Random(3)
        self._stars = [
            (rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT), rng.uniform(0.3, 1.0))
            for _ in range(140)
        ]
        self._view = pygame.Rect(0, 0, WIDTH, HEIGHT)

    # --- Scene stack ------------------------------------------------------------

    @property
    def scene(self) -> Scene:
        return self.scenes[-1]

    def push(self, scene: Scene) -> None:
        self.scenes.append(scene)

    def replace(self, scene: Scene) -> None:
        if self.scenes:
            self.scenes.pop().on_exit()
        self.scenes.append(scene)

    def pop(self) -> None:
        if len(self.scenes) > 1:
            self.scenes.pop().on_exit()

    def quit(self) -> None:
        self.running = False

    # --- Coordinate mapping -------------------------------------------------------

    def _update_view(self) -> None:
        ww, wh = self.window.get_size()
        s = min(ww / WIDTH, wh / HEIGHT)
        w, h = round(WIDTH * s), round(HEIGHT * s)
        self._view = pygame.Rect((ww - w) // 2, (wh - h) // 2, w, h)

    def toggle_fullscreen(self) -> None:
        """Switch between a resizable window and borderless desktop-resolution fullscreen."""
        if self.headless:
            return
        if self.fullscreen:
            self.window = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        else:
            self.windowed_size = self.window.get_size()
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.fullscreen = not self.fullscreen
        self._update_view()

    def to_logical(self, pos: tuple[int, int]) -> tuple[int, int]:
        v = self._view
        x = (pos[0] - v.left) * WIDTH / max(1, v.width)
        y = (pos[1] - v.top) * HEIGHT / max(1, v.height)
        return round(x), round(y)

    def _translate(self, event: pygame.event.Event) -> pygame.event.Event:
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            data = dict(event.dict)
            data["pos"] = self.to_logical(event.pos)
            return pygame.event.Event(event.type, data)
        return event

    # --- Shared background ------------------------------------------------------

    def draw_background(self, surface: pygame.Surface) -> None:
        surface.blit(theme.vertical_gradient(WIDTH, HEIGHT, theme.BG_TOP, theme.BG_BOTTOM), (0, 0))
        t = self.time
        spacing = 64
        offset = (t * 12) % spacing
        for x in range(-spacing, WIDTH + spacing, spacing):
            pygame.draw.line(surface, (18, 20, 44), (x + offset, 0), (x + offset, HEIGHT))
        for y in range(-spacing, HEIGHT + spacing, spacing):
            pygame.draw.line(surface, (18, 20, 44), (0, y + offset), (WIDTH, y + offset))
        for sx, sy, depth in self._stars:
            tw = 0.5 + 0.5 * math.sin(t * 2 * depth + sx)
            c = theme.scale((150, 160, 255), 0.25 + 0.5 * depth * tw)
            surface.fill(c, (round(sx), round((sy + t * 8 * depth) % HEIGHT), 2, 2))

    # --- Main loop --------------------------------------------------------------

    def run(self, first: Scene) -> None:
        self.push(first)
        self._update_view()
        try:
            while self.running and self.scenes:
                dt = min(0.05, self.clock.tick(FPS) / 1000.0)
                self.step(dt)
        finally:
            for scene in reversed(self.scenes):
                scene.on_exit()
            self.brain.shutdown()
            pygame.quit()

    def step(self, dt: float) -> None:
        self.time += dt
        for raw in pygame.event.get():
            if raw.type == pygame.QUIT:
                self.running = False
                return
            if raw.type == pygame.VIDEORESIZE:
                self._update_view()
                continue
            if raw.type == pygame.KEYDOWN and raw.key == pygame.K_F11:
                self.toggle_fullscreen()
                continue
            self.scene.handle(self._translate(raw))
            if not self.running or not self.scenes:
                return
        self.scene.update(dt)
        self.render()

    def render(self) -> None:
        self.scene.draw(self.canvas)
        self.window.fill((0, 0, 0))
        if self._view.size == (WIDTH, HEIGHT):
            self.window.blit(self.canvas, self._view)
        else:
            self.window.blit(pygame.transform.smoothscale(self.canvas, self._view.size), self._view)
        pygame.display.flip()
