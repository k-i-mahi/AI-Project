"""The live "AI brain" side panels."""

from __future__ import annotations

import math

import pygame

from ..ai import ALGORITHMS, AlgorithmId, Insight
from ..engine import Role
from . import theme
from .widgets import draw_bar

PAD = 18


class _Cursor:
    """Vertical layout helper that refuses to draw past the panel bottom."""

    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.y = rect.top + PAD

    def room(self, h: int) -> bool:
        return self.y + h <= self.rect.bottom - PAD

    def take(self, h: int) -> int:
        y = self.y
        self.y += h
        return y


def _section(
    surface: pygame.Surface, cur: _Cursor, title: str, color: theme.Color, content: int = 24
) -> bool:
    """Draw a section header if the header *and* ``content`` pixels still fit."""
    if not cur.room(30 + content):
        return False
    y = cur.take(26)
    cur.y += 4
    theme.blit_text(surface, title.upper(), (cur.rect.left + PAD, y), "ui_bold", 15, color)
    pygame.draw.line(
        surface,
        theme.scale(color, 0.35),
        (cur.rect.left + PAD + 4 + theme.font("ui_bold", 15).size(title.upper())[0] + 6, y + 10),
        (cur.rect.right - PAD, y + 10),
    )
    return True


def draw_brain_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    role: Role,
    algorithm: AlgorithmId | None,
    insight: Insight | None,
    thinking: bool,
    think_ms: list[float],
    time: float,
    is_turn: bool,
) -> None:
    color = theme.ROLE_COLOR[role]
    theme.panel(surface, rect, edge=theme.mix(theme.PANEL_EDGE, color, 0.55 if is_turn else 0.2))
    if is_turn:
        theme.blit_glow(surface, (rect.centerx, rect.top), rect.width // 2, color, 0.25)
    cur = _Cursor(rect)
    left = rect.left + PAD
    inner_w = rect.width - 2 * PAD

    # Header ---------------------------------------------------------------
    y = cur.take(34)
    theme.blit_text(surface, role.value.upper(), (left, y), "display", 22, color)
    if is_turn:
        dot = 0.5 + 0.5 * math.sin(time * 6)
        pygame.draw.circle(
            surface, theme.scale(color, 0.5 + 0.5 * dot), (rect.right - PAD - 6, y + 14), 6
        )
    y = cur.take(28)
    if algorithm is None:
        name, family = "Human Player", "You"
    else:
        info = ALGORITHMS[algorithm]
        name, family = info.name, info.family
    theme.blit_text(surface, name, (left, y), "ui_bold", 22, theme.TEXT)
    y = cur.take(26)
    pill = theme.text(family.upper(), "ui_bold", 13, color)
    pill_rect = pill.get_rect(topleft=(left, y + 2)).inflate(16, 6)
    pygame.draw.rect(surface, theme.scale(color, 0.18), pill_rect, border_radius=8)
    pygame.draw.rect(surface, theme.scale(color, 0.6), pill_rect, 1, border_radius=8)
    surface.blit(pill, pill.get_rect(center=pill_rect.center))
    if thinking:
        dots = "." * (1 + int(time * 4) % 3)
        theme.blit_text(
            surface,
            f"THINKING{dots}",
            (rect.right - PAD, y + 4),
            "ui_bold",
            15,
            theme.WARNING,
            "topright",
        )
    elif think_ms:
        avg = sum(think_ms) / len(think_ms)
        theme.blit_text(
            surface,
            f"last {think_ms[-1]:.0f} ms · avg {avg:.0f} ms",
            (rect.right - PAD, y + 5),
            "mono",
            12,
            theme.TEXT_DIM,
            "topright",
        )
    cur.y += 8

    if algorithm is None:
        _draw_human_help(surface, cur, color, role)
        return
    if insight is None:
        if cur.room(40):
            theme.blit_text(
                surface,
                "Waiting for the first decision…",
                (left, cur.take(30)),
                "ui",
                18,
                theme.TEXT_DIM,
            )
        return

    # Summary ----------------------------------------------------------------
    for line in theme.wrap(insight.summary, "ui", 18, inner_w)[:3]:
        if not cur.room(22):
            return
        theme.blit_text(surface, line, (left, cur.take(22)), "ui", 18, theme.TEXT)
    cur.y += 6

    # Stats ------------------------------------------------------------------
    if insight.stats and _section(surface, cur, "Telemetry", color):
        col_w = inner_w // 2
        for i in range(0, len(insight.stats), 2):
            if not cur.room(40):
                return
            y = cur.take(40)
            for j, (k, v) in enumerate(insight.stats[i : i + 2]):
                x = left + j * col_w
                theme.blit_text(surface, k.upper(), (x, y), "ui", 13, theme.TEXT_DIM)
                theme.blit_text(surface, v, (x, y + 15), "mono", 16, theme.TEXT)

    if insight.fuzzy_inputs:
        _draw_fuzzy(surface, cur, insight, color)

    # Action scores ----------------------------------------------------------
    title = "Action visits" if algorithm is AlgorithmId.MCTS else "Action scores"
    if insight.actions and _section(surface, cur, title, color):
        best = max(insight.actions, key=lambda s: s.score).action
        limit = 3 if insight.fuzzy_inputs else 9
        for a in insight.actions[:limit]:
            if not cur.room(22):
                return
            y = cur.take(22)
            chosen = a.action == best
            label_color = theme.TEXT if chosen else theme.TEXT_DIM
            theme.blit_text(
                surface,
                a.action.glyph,
                (left + 10, y + 10),
                "mono",
                15,
                color if chosen else label_color,
                "center",
            )
            theme.blit_text(surface, a.action.label, (left + 26, y), "ui", 16, label_color)
            bar = pygame.Rect(left + 128, y + 5, inner_w - 128 - 52, 10)
            draw_bar(surface, bar, a.score, color if chosen else theme.scale(color, 0.45))
            value = f"{a.visits}" if a.visits is not None else f"{a.score:.2f}"
            theme.blit_text(
                surface, value, (rect.right - PAD, y), "mono", 13, label_color, "topright"
            )


def _draw_fuzzy(
    surface: pygame.Surface, cur: _Cursor, insight: Insight, color: theme.Color
) -> None:
    left = cur.rect.left + PAD
    inner_w = cur.rect.width - 2 * PAD
    if not _section(surface, cur, "Fuzzification", color):
        return
    for inp in insight.fuzzy_inputs:
        if not cur.room(32):
            return
        y = cur.take(32)
        value = f"{inp.value:.2f}" if inp.high <= 1.0 else f"{inp.value:.0f}"
        theme.blit_text(surface, inp.name, (left, y), "ui_bold", 15, theme.TEXT)
        theme.blit_text(surface, value, (left + 92, y + 1), "mono", 13, theme.TEXT_DIM)
        n = len(inp.memberships)
        gap = 4
        seg_w = (inner_w - 140 - gap * (n - 1)) // max(1, n)
        for i, (label, degree) in enumerate(inp.memberships):
            x = left + 140 + i * (seg_w + gap)
            seg = pygame.Rect(x, y + 4, seg_w, 9)
            draw_bar(surface, seg, degree, theme.mix(theme.scale(color, 0.5), color, degree))
            theme.blit_text(
                surface,
                label,
                (x + seg_w // 2, y + 15),
                "ui",
                12,
                theme.TEXT if degree > 0.5 else theme.TEXT_FAINT,
                "midtop",
            )

    fired = sorted((r for r in insight.fuzzy_rules if r.strength > 0), key=lambda r: -r.strength)
    if fired and _section(surface, cur, "Rules fired", color):
        for rule in fired[:3]:
            if not cur.room(30):
                return
            y = cur.take(30)
            text = (
                rule.text.replace("IF ", "")
                .replace(" THEN desirability is ", " THEN ")
                .replace(" is ", " ")
            )
            lines = theme.wrap(text, "ui", 14, inner_w - 46)
            theme.blit_text(surface, rule.rule_id, (left, y), "mono", 13, color)
            theme.blit_text(surface, lines[0], (left + 40, y), "ui", 14, theme.TEXT)
            draw_bar(
                surface,
                pygame.Rect(left + 40, y + 19, inner_w - 40, 5),
                rule.strength,
                theme.scale(color, 0.8),
            )

    if insight.fuzzy_curve and _section(surface, cur, "Defuzzification", color, 66):
        y = cur.take(66)
        plot = pygame.Rect(left, y, inner_w, 58)
        pygame.draw.rect(surface, theme.GRID, plot, 1, border_radius=4)
        curve = insight.fuzzy_curve
        n = len(curve)
        pts = [
            (plot.left + plot.width * i / (n - 1), plot.bottom - 2 - (plot.height - 6) * mu)
            for i, mu in enumerate(curve)
        ]
        poly = [(plot.left, plot.bottom - 2), *pts, (plot.right, plot.bottom - 2)]
        layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(layer, (*color, 70), poly)
        surface.blit(layer, (0, 0))
        pygame.draw.lines(surface, color, False, pts, 2)
        if insight.fuzzy_output is not None:
            cx = plot.left + plot.width * insight.fuzzy_output
            pygame.draw.line(surface, theme.TEXT, (cx, plot.top + 2), (cx, plot.bottom - 2), 2)
            theme.blit_text(
                surface,
                f"centroid {insight.fuzzy_output:.2f}",
                (cx + 4, plot.top + 2),
                "mono",
                12,
                theme.TEXT,
            )


def _draw_human_help(surface: pygame.Surface, cur: _Cursor, color: theme.Color, role: Role) -> None:
    left = cur.rect.left + PAD
    if not _section(surface, cur, "Your controls", color):
        return
    burst = "Dash" if role is Role.SURVIVOR else "Pounce"
    rows = [
        ("WASD / Arrows", "Move one tile"),
        ("Shift + direction", f"{burst} two tiles"),
        ("Space", "Wait in place"),
        ("Click a ring", "Move there"),
    ]
    for key, desc in rows:
        if not cur.room(26):
            return
        y = cur.take(26)
        theme.blit_text(surface, key, (left, y), "mono", 14, theme.TEXT)
        theme.blit_text(surface, desc, (left + 170, y), "ui", 16, theme.TEXT_DIM)
    goal = (
        "Collect cores to refill energy. Grab enough to escape — but never step next to the Hunter."
        if role is Role.SURVIVOR
        else "Catch the Survivor, or guard the cores until it starves."
    )
    if _section(surface, cur, "Objective", color):
        for line in theme.wrap(goal, "ui", 17, cur.rect.width - 2 * PAD):
            if cur.room(22):
                theme.blit_text(surface, line, (left, cur.take(22)), "ui", 17, theme.TEXT)
