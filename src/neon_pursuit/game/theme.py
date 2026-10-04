"""Visual design tokens: palette, typography and cached glow sprites."""

from __future__ import annotations

from functools import cache
from importlib import resources

import pygame

from ..engine import Role

Color = tuple[int, int, int]

# --- Palette ----------------------------------------------------------------
BG_TOP: Color = (7, 9, 22)
BG_BOTTOM: Color = (14, 6, 30)
PANEL: Color = (16, 20, 42)
PANEL_EDGE: Color = (44, 52, 96)
GRID: Color = (26, 32, 64)
FLOOR: Color = (12, 15, 34)
WALL: Color = (30, 36, 78)
WALL_TOP: Color = (58, 70, 150)
WALL_EDGE: Color = (110, 130, 255)

TEXT: Color = (226, 232, 255)
TEXT_DIM: Color = (138, 148, 192)
TEXT_FAINT: Color = (84, 92, 136)

HUNTER: Color = (255, 56, 112)
HUNTER_SOFT: Color = (255, 128, 160)
SURVIVOR: Color = (40, 232, 255)
SURVIVOR_SOFT: Color = (150, 244, 255)
CORE: Color = (255, 214, 64)
CORE_SOFT: Color = (255, 238, 160)
ACCENT: Color = (150, 108, 255)
SUCCESS: Color = (88, 240, 160)
WARNING: Color = (255, 168, 64)

ROLE_COLOR: dict[Role, Color] = {Role.HUNTER: HUNTER, Role.SURVIVOR: SURVIVOR}
ROLE_SOFT: dict[Role, Color] = {Role.HUNTER: HUNTER_SOFT, Role.SURVIVOR: SURVIVOR_SOFT}


def mix(a: Color, b: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def scale(c: Color, k: float) -> Color:
    return (min(255, round(c[0] * k)), min(255, round(c[1] * k)), min(255, round(c[2] * k)))


# --- Typography ---------------------------------------------------------------
_FONT_FILES = {
    "display": "Orbitron.ttf",
    "ui": "Rajdhani-Medium.ttf",
    "ui_bold": "Rajdhani-Bold.ttf",
    "mono": "JetBrainsMono.ttf",
}


@cache
def font(kind: str, size: int) -> pygame.font.Font:
    """Bundled OFL fonts, with a system fallback if the asset is missing."""
    filename = _FONT_FILES[kind]
    try:
        ref = resources.files("neon_pursuit.assets").joinpath("fonts", filename)
        with resources.as_file(ref) as path:
            return pygame.font.Font(str(path), size)
    except (FileNotFoundError, OSError):  # pragma: no cover - packaging fallback
        return pygame.font.SysFont("consolas", size)


@cache
def _text_surface(text: str, kind: str, size: int, color: Color) -> pygame.Surface:
    return font(kind, size).render(text, True, color)


def text(text_: str, kind: str, size: int, color: Color) -> pygame.Surface:
    """Render (and cache) a text surface."""
    return _text_surface(text_, kind, size, color)


def blit_text(
    surface: pygame.Surface,
    value: str,
    pos: tuple[float, float],
    kind: str = "ui",
    size: int = 20,
    color: Color = TEXT,
    anchor: str = "topleft",
) -> pygame.Rect:
    img = text(value, kind, size, color)
    rect = img.get_rect(**{anchor: (round(pos[0]), round(pos[1]))})
    surface.blit(img, rect)
    return rect


def wrap(value: str, kind: str, size: int, width: int) -> list[str]:
    """Greedy word wrap for a pixel width."""
    f = font(kind, size)
    lines: list[str] = []
    for paragraph in value.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}".strip()
            if f.size(candidate)[0] <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


# --- Glow sprites -------------------------------------------------------------
@cache
def glow(radius: int, color: Color, intensity: float = 1.0) -> pygame.Surface:
    """Radial gradient sprite meant to be blitted with ``BLEND_ADD``."""
    size = radius * 2
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    steps = max(8, radius // 2)
    for i in range(steps, 0, -1):
        t = i / steps
        falloff = (1.0 - t) ** 2.2
        c = scale(color, falloff * intensity * 0.9)
        pygame.draw.circle(surf, (*c, 255), (radius, radius), max(1, round(radius * t)))
    return surf


def blit_glow(
    surface: pygame.Surface, center: tuple[float, float], radius: int, color: Color, k: float = 1.0
) -> None:
    if k <= 0.01:
        return
    g = glow(radius, color, round(k * 20) / 20)  # quantised to keep the cache small
    surface.blit(
        g, (round(center[0] - radius), round(center[1] - radius)), special_flags=pygame.BLEND_ADD
    )


@cache
def vertical_gradient(width: int, height: int, top: Color, bottom: Color) -> pygame.Surface:
    surf = pygame.Surface((width, height))
    for y in range(height):
        pygame.draw.line(surf, mix(top, bottom, y / max(1, height - 1)), (0, y), (width, y))
    return surf


def panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    edge: Color = PANEL_EDGE,
    fill: Color = PANEL,
    alpha: int = 225,
    radius: int = 14,
) -> None:
    """Translucent rounded panel with a thin neon border."""
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, (*fill, alpha), layer.get_rect(), border_radius=radius)
    pygame.draw.rect(layer, (*edge, 255), layer.get_rect(), width=1, border_radius=radius)
    surface.blit(layer, rect.topleft)
