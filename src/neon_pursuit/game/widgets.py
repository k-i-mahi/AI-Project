"""Minimal immediate-feedback widgets drawn in the neon style."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

import pygame

from . import theme

T = TypeVar("T")


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    on_click: Callable[[], None]
    color: theme.Color = theme.ACCENT
    subtitle: str = ""
    size: int = 24
    hotkey: int | None = None
    enabled: bool = True
    _hover: float = field(default=0.0, init=False)
    _hovering: bool = field(default=False, init=False)

    def handle(self, event: pygame.event.Event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self._hovering = self.rect.collidepoint(event.pos)
        elif (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ) or (
            event.type == pygame.KEYDOWN and self.hotkey is not None and event.key == self.hotkey
        ):
            self.on_click()
            return True
        return False

    def update(self, dt: float) -> None:
        target = 1.0 if self._hovering and self.enabled else 0.0
        self._hover += (target - self._hover) * min(1.0, dt * 12)

    def draw(self, surface: pygame.Surface) -> None:
        h = self._hover
        color = self.color if self.enabled else theme.TEXT_FAINT
        if h > 0.02:
            theme.blit_glow(surface, self.rect.center, self.rect.width // 2 + 30, color, 0.35 * h)
        fill = theme.mix(theme.PANEL, theme.scale(color, 0.35), 0.25 + 0.45 * h)
        edge = theme.mix(theme.PANEL_EDGE, color, 0.5 + 0.5 * h)
        pygame.draw.rect(surface, fill, self.rect, border_radius=12)
        pygame.draw.rect(surface, edge, self.rect, width=2, border_radius=12)
        label_color = theme.mix(theme.TEXT, (255, 255, 255), h)
        if self.subtitle:
            theme.blit_text(
                surface,
                self.label,
                (self.rect.centerx, self.rect.centery - 11),
                "ui_bold",
                self.size,
                label_color,
                "center",
            )
            theme.blit_text(
                surface,
                self.subtitle,
                (self.rect.centerx, self.rect.centery + 15),
                "ui",
                16,
                theme.TEXT_DIM,
                "center",
            )
        else:
            theme.blit_text(
                surface, self.label, self.rect.center, "ui_bold", self.size, label_color, "center"
            )


@dataclass
class Selector(Generic[T]):
    """Left/right cycling selector: ``‹  Value  ›``."""

    rect: pygame.Rect
    options: Sequence[tuple[T, str]]
    index: int = 0
    color: theme.Color = theme.ACCENT
    on_change: Callable[[T], None] | None = None

    @property
    def value(self) -> T:
        return self.options[self.index][0]

    def set_value(self, value: T) -> None:
        for i, (v, _) in enumerate(self.options):
            if v == value:
                self.index = i
                return

    def _arrow_rects(self) -> tuple[pygame.Rect, pygame.Rect]:
        w = self.rect.height
        left = pygame.Rect(self.rect.left, self.rect.top, w, self.rect.height)
        right = pygame.Rect(self.rect.right - w, self.rect.top, w, self.rect.height)
        return left, right

    def step(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.options)
        if self.on_change:
            self.on_change(self.value)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            left, right = self._arrow_rects()
            if left.collidepoint(event.pos):
                self.step(-1)
                return True
            if right.collidepoint(event.pos) or self.rect.collidepoint(event.pos):
                self.step(1)
                return True
        if event.type == pygame.MOUSEWHEEL and self.rect.collidepoint(pygame.mouse.get_pos()):
            self.step(-event.y)
            return True
        return False

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(
            surface, theme.mix(theme.PANEL, self.color, 0.08), self.rect, border_radius=10
        )
        pygame.draw.rect(
            surface, theme.mix(theme.PANEL_EDGE, self.color, 0.45), self.rect, 1, border_radius=10
        )
        left, right = self._arrow_rects()
        theme.blit_text(surface, "‹", left.center, "ui_bold", 30, self.color, "center")
        theme.blit_text(surface, "›", right.center, "ui_bold", 30, self.color, "center")
        theme.blit_text(
            surface,
            self.options[self.index][1],
            self.rect.center,
            "ui_bold",
            22,
            theme.TEXT,
            "center",
        )


@dataclass
class Toggle:
    rect: pygame.Rect
    label: str
    value: bool
    color: theme.Color = theme.ACCENT
    hotkey_hint: str = ""
    on_change: Callable[[bool], None] | None = None

    def handle(self, event: pygame.event.Event) -> bool:
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ):
            self.flip()
            return True
        return False

    def flip(self) -> None:
        self.value = not self.value
        if self.on_change:
            self.on_change(self.value)

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        box = pygame.Rect(self.rect.left, self.rect.centery - 9, 34, 18)
        on = self.value
        pygame.draw.rect(
            surface, theme.scale(self.color, 0.55) if on else theme.GRID, box, border_radius=9
        )
        knob_x = box.right - 9 if on else box.left + 9
        pygame.draw.circle(surface, theme.TEXT if on else theme.TEXT_DIM, (knob_x, box.centery), 7)
        label = f"{self.label}  [{self.hotkey_hint}]" if self.hotkey_hint else self.label
        theme.blit_text(
            surface,
            label,
            (box.right + 10, self.rect.centery),
            "ui",
            18,
            theme.TEXT if on else theme.TEXT_DIM,
            "midleft",
        )


Widget = Button | Selector[object] | Toggle


def draw_bar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    fraction: float,
    color: theme.Color,
    back: theme.Color = theme.GRID,
    radius: int = 4,
) -> None:
    pygame.draw.rect(surface, back, rect, border_radius=radius)
    f = max(0.0, min(1.0, fraction))
    if f > 0:
        fill = pygame.Rect(rect.left, rect.top, max(radius * 2, round(rect.width * f)), rect.height)
        pygame.draw.rect(surface, color, fill, border_radius=radius)
