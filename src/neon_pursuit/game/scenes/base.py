from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pygame

if TYPE_CHECKING:
    from ..app import App


class Widget(Protocol):
    def handle(self, event: pygame.event.Event) -> bool: ...
    def update(self, dt: float) -> None: ...
    def draw(self, surface: pygame.Surface) -> None: ...


class Scene:
    """Base scene. Subclasses override the hooks they need."""

    def __init__(self, app: App) -> None:
        self.app = app
        self.widgets: list[Widget] = []

    def handle(self, event: pygame.event.Event) -> None:
        for widget in list(self.widgets):
            if widget.handle(event):
                return
        self.on_event(event)

    def on_event(self, event: pygame.event.Event) -> None:
        """Events not consumed by a widget."""

    def update(self, dt: float) -> None:
        for widget in self.widgets:
            widget.update(dt)

    def draw(self, surface: pygame.Surface) -> None:
        self.app.draw_background(surface)
        self.draw_content(surface)
        for widget in self.widgets:
            widget.draw(surface)

    def draw_content(self, surface: pygame.Surface) -> None:
        """Scene-specific drawing beneath the widgets."""

    def on_exit(self) -> None:
        """Release resources when the scene leaves the stack."""
