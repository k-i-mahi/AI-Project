"""Board rendering: neon arena, entities, effects and AI overlays."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

import pygame

from ..engine import (
    UNREACHABLE,
    Action,
    CaptureEvent,
    CoreCollectedEvent,
    CoreSpawnedEvent,
    GameMap,
    GameState,
    MatchConfig,
    MoveEvent,
    Role,
    path_of,
    territory_owner_map,
)
from . import theme
from .controller import Turn


@dataclass(slots=True)
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: theme.Color
    size: float
    drag: float = 2.5


class Particles:
    def __init__(self) -> None:
        self.items: list[Particle] = []
        self.rng = random.Random(7)

    def burst(
        self,
        x: float,
        y: float,
        color: theme.Color,
        count: int = 24,
        speed: float = 220.0,
        life: float = 0.8,
        size: float = 4.0,
    ) -> None:
        for _ in range(count):
            a = self.rng.uniform(0, math.tau)
            v = speed * self.rng.uniform(0.25, 1.0)
            ttl = life * self.rng.uniform(0.6, 1.0)
            self.items.append(
                Particle(x, y, math.cos(a) * v, math.sin(a) * v, ttl, ttl, color, size)
            )

    def ring(
        self, x: float, y: float, color: theme.Color, count: int = 36, speed: float = 260
    ) -> None:
        for i in range(count):
            a = math.tau * i / count
            self.items.append(
                Particle(x, y, math.cos(a) * speed, math.sin(a) * speed, 0.6, 0.6, color, 3.0, 4.0)
            )

    def update(self, dt: float) -> None:
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0:
                continue
            damp = math.exp(-p.drag * dt)
            p.vx *= damp
            p.vy *= damp
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.items = alive

    def draw(self, surface: pygame.Surface, offset: tuple[float, float]) -> None:
        ox, oy = offset
        for p in self.items:
            k = p.life / p.max_life
            r = max(1, round(p.size * (0.4 + 0.6 * k)))
            theme.blit_glow(surface, (p.x + ox, p.y + oy), r * 3, p.color, 0.8 * k)
            pygame.draw.circle(
                surface, theme.mix(p.color, (255, 255, 255), 0.4), (p.x + ox, p.y + oy), r
            )


@dataclass
class EntityVisual:
    role: Role
    x: float
    y: float
    from_xy: tuple[float, float] = (0.0, 0.0)
    to_xy: tuple[float, float] = (0.0, 0.0)
    t: float = 1.0
    duration: float = 0.2
    heading: float = 0.0
    trail: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=14))

    def move(self, to_xy: tuple[float, float], duration: float) -> None:
        self.from_xy = (self.x, self.y)
        self.to_xy = to_xy
        dx, dy = to_xy[0] - self.x, to_xy[1] - self.y
        if abs(dx) + abs(dy) > 1e-6:
            self.heading = math.atan2(dy, dx)
        self.t = 0.0
        self.duration = max(0.01, duration)

    def update(self, dt: float) -> None:
        if self.t < 1.0:
            self.t = min(1.0, self.t + dt / self.duration)
            e = 1 - (1 - self.t) ** 3  # ease-out cubic
            self.x = self.from_xy[0] + (self.to_xy[0] - self.from_xy[0]) * e
            self.y = self.from_xy[1] + (self.to_xy[1] - self.from_xy[1]) * e
        self.trail.append((self.x, self.y))

    @property
    def moving(self) -> bool:
        return self.t < 1.0


@dataclass(slots=True)
class Overlays:
    territory: bool = False
    danger: bool = False
    plans: bool = True
    grid: bool = True


class BoardView:
    """Draws one match. Positions are kept in *tile* units and converted at draw time."""

    def __init__(self, game_map: GameMap, config: MatchConfig, rect: pygame.Rect) -> None:
        self.map = game_map
        self.config = config
        self.tile = max(8, min(rect.width // game_map.width, rect.height // game_map.height))
        w, h = self.tile * game_map.width, self.tile * game_map.height
        self.rect = pygame.Rect(0, 0, w, h)
        self.rect.center = rect.center
        self.particles = Particles()
        self.shake = 0.0
        self.time = 0.0
        self.flash = 0.0
        self.flash_color: theme.Color = theme.HUNTER
        self.entities: dict[Role, EntityVisual] = {}
        self.static = self._render_static()
        self._territory_cache: tuple[tuple[int, int], pygame.Surface] | None = None
        self._danger_cache: tuple[int, pygame.Surface] | None = None
        self.core_spawn_time: dict[int, float] = {}

    # --- Coordinates ----------------------------------------------------------

    def cell_center(self, cell: int) -> tuple[float, float]:
        x, y = self.map.xy(cell)
        return x + 0.5, y + 0.5

    def to_px(self, xy: tuple[float, float]) -> tuple[float, float]:
        return self.rect.left + xy[0] * self.tile, self.rect.top + xy[1] * self.tile

    def _offset(self) -> tuple[float, float]:
        if self.shake <= 0:
            return (0.0, 0.0)
        a = self.shake * 14
        return (math.sin(self.time * 91) * a, math.cos(self.time * 77) * a)

    # --- Static arena ---------------------------------------------------------

    def _render_static(self) -> pygame.Surface:
        gm, ts = self.map, self.tile
        surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        surf.fill((*theme.FLOOR, 255))
        for c in gm.floor_cells:
            x, y = gm.xy(c)
            r = pygame.Rect(x * ts, y * ts, ts, ts)
            shade = 1.0 + 0.08 * (((x + y) % 2) - 0.5)
            pygame.draw.rect(surf, theme.scale(theme.FLOOR, shade), r)
            pygame.draw.circle(surf, theme.GRID, r.center, max(1, ts // 18))

        # Walls: raised blocks with a lit top face and neon edges facing open floor.
        inset = max(2, ts // 10)
        for c in range(gm.size):
            if not gm.is_wall(c):
                continue
            x, y = gm.xy(c)
            r = pygame.Rect(x * ts, y * ts, ts, ts)
            pygame.draw.rect(surf, theme.WALL, r)
            top = r.inflate(-inset * 2, -inset * 2)
            pygame.draw.rect(
                surf, theme.mix(theme.WALL, theme.WALL_TOP, 0.55), top, border_radius=4
            )
            for d, (a, b) in {
                1: (r.topleft, r.topright),
                2: (r.topright, r.bottomright),
                3: (r.bottomleft, r.bottomright),
                4: (r.topleft, r.bottomleft),
            }.items():
                nx, ny = x + (0, 0, 1, 0, -1)[d], y + (0, -1, 0, 1, 0)[d]
                if 0 <= nx < gm.width and 0 <= ny < gm.height and not gm.is_wall(gm.cell(nx, ny)):
                    pygame.draw.line(surf, theme.WALL_EDGE, a, b, 2)

        glow_layer = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        for c in range(gm.size):
            if gm.is_wall(c):
                x, y = gm.xy(c)
                if any(not gm.is_wall(n) for n in self._neighbours_any(x, y)):
                    theme.blit_glow(
                        glow_layer, ((x + 0.5) * ts, (y + 0.5) * ts), ts, theme.WALL_EDGE, 0.12
                    )
        surf.blit(glow_layer, (0, 0), special_flags=pygame.BLEND_ADD)
        border = surf.get_rect()
        pygame.draw.rect(surf, theme.WALL_EDGE, border, 2, border_radius=6)
        return surf

    def _neighbours_any(self, x: int, y: int) -> list[int]:
        gm = self.map
        out = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < gm.width and 0 <= ny < gm.height:
                out.append(gm.cell(nx, ny))
        return out

    # --- State sync & animation -------------------------------------------------

    def reset(self, state: GameState) -> None:
        self.entities = {
            Role.HUNTER: EntityVisual(Role.HUNTER, *self.cell_center(state.hunter)),
            Role.SURVIVOR: EntityVisual(Role.SURVIVOR, *self.cell_center(state.survivor)),
        }
        self.entities[Role.HUNTER].heading = 0.0
        self.entities[Role.SURVIVOR].heading = math.pi
        self.particles.items.clear()
        self.core_spawn_time = {c: -10.0 for c in state.cores if c >= 0}
        self._territory_cache = None
        self._danger_cache = None

    def animate(self, turn: Turn, duration: float) -> None:
        ent = self.entities[turn.role]
        ent.move(self.cell_center(turn.after.position_of(turn.role)), duration)
        for event in turn.events:
            if isinstance(event, MoveEvent) and event.action.is_burst:
                px, py = self.to_px(self.cell_center(event.from_cell))
                self.particles.burst(
                    px - self.rect.left,
                    py - self.rect.top,
                    theme.ROLE_SOFT[event.role],
                    14,
                    120,
                    0.5,
                    3,
                )
            elif isinstance(event, CoreCollectedEvent):
                cx, cy = self.cell_center(event.cell)
                self.particles.burst(cx * self.tile, cy * self.tile, theme.CORE, 34, 260, 0.9, 4)
                self.particles.ring(cx * self.tile, cy * self.tile, theme.CORE_SOFT, 28, 200)
                self.flash, self.flash_color = 0.25, theme.CORE
            elif isinstance(event, CoreSpawnedEvent):
                self.core_spawn_time[event.cell] = self.time
            elif isinstance(event, CaptureEvent):
                cx, cy = self.cell_center(event.cell)
                self.particles.burst(cx * self.tile, cy * self.tile, theme.HUNTER, 70, 420, 1.3, 5)
                self.particles.burst(
                    cx * self.tile, cy * self.tile, theme.SURVIVOR, 50, 300, 1.1, 4
                )
                self.particles.ring(cx * self.tile, cy * self.tile, theme.HUNTER_SOFT, 48, 380)
                self.shake = 1.0
                self.flash, self.flash_color = 0.6, theme.HUNTER

    @property
    def animating(self) -> bool:
        return any(e.moving for e in self.entities.values())

    def update(self, dt: float) -> None:
        self.time += dt
        self.shake = max(0.0, self.shake - dt * 2.2)
        self.flash = max(0.0, self.flash - dt * 1.6)
        for e in self.entities.values():
            e.update(dt)
        self.particles.update(dt)

    # --- Drawing ----------------------------------------------------------------

    def draw(
        self,
        surface: pygame.Surface,
        state: GameState,
        overlays: Overlays,
        plans: dict[Role, list[int]],
        human_hints: list[tuple[Action, list[int]]] | None = None,
    ) -> None:
        ox, oy = self._offset()
        origin = (self.rect.left + ox, self.rect.top + oy)
        theme.blit_glow(surface, self.rect.center, self.rect.width // 2 + 80, theme.ACCENT, 0.12)
        surface.blit(self.static, origin)

        if overlays.danger:
            surface.blit(self._danger_surface(state), origin)
        if overlays.territory:
            surface.blit(self._territory_surface(state), origin)
        if overlays.plans:
            for role, plan in plans.items():
                self._draw_plan(surface, role, plan, origin)
        if human_hints:
            self._draw_hints(surface, state, human_hints, origin)

        self._draw_cores(surface, state, origin)
        self._draw_trails(surface, origin)
        self._draw_survivor(surface, state, origin)
        self._draw_hunter(surface, state, origin)
        self.particles.draw(surface, origin)

        if self.flash > 0:
            layer = pygame.Surface(self.rect.size, pygame.SRCALPHA)
            layer.fill((*self.flash_color, round(70 * self.flash)))
            surface.blit(layer, origin, special_flags=pygame.BLEND_ADD)

    def _px(self, xy: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
        return origin[0] + xy[0] * self.tile, origin[1] + xy[1] * self.tile

    def _territory_surface(self, state: GameState) -> pygame.Surface:
        key = (state.hunter, state.survivor)
        if self._territory_cache and self._territory_cache[0] == key:
            return self._territory_cache[1]
        surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        owners = territory_owner_map(self.map, state.hunter, state.survivor)
        ts = self.tile
        for c, owner in owners.items():
            x, y = self.map.xy(c)
            color = theme.SURVIVOR if owner == 1 else theme.HUNTER
            pygame.draw.rect(
                surf, (*color, 46), (x * ts + 1, y * ts + 1, ts - 2, ts - 2), border_radius=4
            )
        self._territory_cache = (key, surf)
        return surf

    def _danger_surface(self, state: GameState) -> pygame.Surface:
        if self._danger_cache and self._danger_cache[0] == state.hunter:
            return self._danger_cache[1]
        surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        ts = self.tile
        for c in self.map.floor_cells:
            d = self.map.distance(state.hunter, c)
            if d == UNREACHABLE:
                continue
            k = max(0.0, 1.0 - d / 9.0)
            if k <= 0:
                continue
            x, y = self.map.xy(c)
            pygame.draw.rect(surf, (*theme.HUNTER, round(110 * k * k)), (x * ts, y * ts, ts, ts))
            if d <= 9:
                theme.blit_text(
                    surf,
                    str(d),
                    ((x + 0.5) * ts, (y + 0.5) * ts),
                    "mono",
                    max(9, ts // 4),
                    theme.HUNTER_SOFT,
                    "center",
                )
        self._danger_cache = (state.hunter, surf)
        return surf

    def _draw_plan(
        self, surface: pygame.Surface, role: Role, plan: list[int], origin: tuple[float, float]
    ) -> None:
        if not plan:
            return
        ent = self.entities.get(role)
        if ent is None:
            return
        pts = [self._px((ent.x, ent.y), origin)] + [
            self._px(self.cell_center(c), origin) for c in plan if c >= 0
        ]
        color = theme.ROLE_COLOR[role]
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            fade = 1.0 - i / max(1, len(pts))
            seg = math.dist(a, b)
            n = max(1, int(seg // 9))
            for k in range(n):
                if k % 2:
                    continue
                t0, t1 = k / n, min(1.0, (k + 1) / n)
                p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
                p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
                pygame.draw.line(surface, theme.scale(color, 0.4 + 0.6 * fade), p0, p1, 2)
        end = pts[-1]
        pygame.draw.circle(surface, theme.scale(color, 0.8), end, max(3, self.tile // 9), 1)

    def _draw_hints(
        self,
        surface: pygame.Surface,
        state: GameState,
        hints: list[tuple[Action, list[int]]],
        origin: tuple[float, float],
    ) -> None:
        role = state.to_move
        color = theme.ROLE_COLOR[role]
        pulse = 0.5 + 0.5 * math.sin(self.time * 5)
        for action, path in hints:
            if action is Action.WAIT:
                continue
            cell = path[-1]
            cx, cy = self._px(self.cell_center(cell), origin)
            r = self.tile * (0.28 if action.is_burst else 0.36)
            alpha_c = theme.scale(color, 0.35 + 0.35 * pulse)
            pygame.draw.circle(surface, alpha_c, (cx, cy), r, 2)
            label = action.glyph
            theme.blit_text(
                surface, label, (cx, cy), "ui_bold", max(12, self.tile // 3), alpha_c, "center"
            )

    def _draw_cores(
        self, surface: pygame.Surface, state: GameState, origin: tuple[float, float]
    ) -> None:
        ts = self.tile
        for c in state.cores:
            if c < 0:
                continue
            born = self.core_spawn_time.get(c, -10.0)
            grow = min(1.0, (self.time - born) / 0.45)
            cx, cy = self._px(self.cell_center(c), origin)
            pulse = 0.5 + 0.5 * math.sin(self.time * 4 + c)
            theme.blit_glow(
                surface, (cx, cy), round(ts * (0.9 + 0.2 * pulse)), theme.CORE, 0.55 * grow
            )
            r = ts * 0.24 * grow * (0.92 + 0.08 * pulse)
            a = self.time * 1.6 + c
            pts = [
                (cx + math.cos(a + k * math.pi / 2) * r, cy + math.sin(a + k * math.pi / 2) * r)
                for k in range(4)
            ]
            pygame.draw.polygon(surface, theme.CORE, pts)
            inner = [(cx + (x - cx) * 0.45, cy + (y - cy) * 0.45) for x, y in pts]
            pygame.draw.polygon(surface, theme.CORE_SOFT, inner)
            pygame.draw.polygon(surface, (255, 255, 255), pts, 1)

    def _draw_trails(self, surface: pygame.Surface, origin: tuple[float, float]) -> None:
        for role, ent in self.entities.items():
            color = theme.ROLE_COLOR[role]
            pts = list(ent.trail)
            n = len(pts)
            for i, p in enumerate(pts[:-1]):
                k = (i + 1) / n
                px = self._px(p, origin)
                pygame.draw.circle(
                    surface,
                    theme.scale(color, 0.12 + 0.35 * k),
                    px,
                    max(1, round(self.tile * 0.12 * k)),
                )

    def _draw_survivor(
        self, surface: pygame.Surface, state: GameState, origin: tuple[float, float]
    ) -> None:
        ent = self.entities[Role.SURVIVOR]
        if state.win_reason is not None and state.win_reason.value == "captured" and not ent.moving:
            return
        cx, cy = self._px((ent.x, ent.y), origin)
        ts = self.tile
        pulse = 0.5 + 0.5 * math.sin(self.time * 3)
        theme.blit_glow(surface, (cx, cy), round(ts * 1.1), theme.SURVIVOR, 0.6 + 0.2 * pulse)
        pygame.draw.circle(surface, theme.scale(theme.SURVIVOR, 0.5), (cx, cy), ts * 0.32)
        pygame.draw.circle(surface, theme.SURVIVOR, (cx, cy), ts * 0.26)
        pygame.draw.circle(surface, (235, 255, 255), (cx, cy), ts * 0.12)
        # Energy ring.
        frac = state.energy / self.config.max_energy
        ring = pygame.Rect(0, 0, ts * 0.86, ts * 0.86)
        ring.center = (round(cx), round(cy))
        low = frac < 0.3
        ring_color = theme.mix(theme.WARNING, theme.HUNTER, pulse) if low else theme.SUCCESS
        pygame.draw.arc(surface, theme.GRID, ring, 0, math.tau, 2)
        if frac > 0:
            pygame.draw.arc(
                surface, ring_color, ring, math.pi / 2, math.pi / 2 + math.tau * frac, 3
            )
        if state.dash_cooldown == 0 and state.energy > 3:
            for k in range(3):
                a = self.time * 2 + k * math.tau / 3
                pygame.draw.circle(
                    surface,
                    theme.SURVIVOR_SOFT,
                    (cx + math.cos(a) * ts * 0.5, cy + math.sin(a) * ts * 0.5),
                    2,
                )

    def _draw_hunter(
        self, surface: pygame.Surface, state: GameState, origin: tuple[float, float]
    ) -> None:
        ent = self.entities[Role.HUNTER]
        cx, cy = self._px((ent.x, ent.y), origin)
        ts = self.tile
        pulse = 0.5 + 0.5 * math.sin(self.time * 6)
        ready = state.pounce_cooldown == 0
        theme.blit_glow(
            surface, (cx, cy), round(ts * 1.2), theme.HUNTER, 0.6 + (0.3 * pulse if ready else 0)
        )
        h = ent.heading
        r = ts * 0.4

        def pt(angle: float, radius: float) -> tuple[float, float]:
            return (cx + math.cos(h + angle) * radius, cy + math.sin(h + angle) * radius)

        outer = [pt(0, r), pt(2.4, r * 0.85), pt(math.pi, r * 0.35), pt(-2.4, r * 0.85)]
        pygame.draw.polygon(surface, theme.scale(theme.HUNTER, 0.55), outer)
        inner = [pt(0, r * 0.75), pt(2.4, r * 0.55), pt(math.pi, r * 0.1), pt(-2.4, r * 0.55)]
        pygame.draw.polygon(surface, theme.HUNTER, inner)
        pygame.draw.polygon(surface, theme.HUNTER_SOFT, outer, 2)
        pygame.draw.circle(surface, (255, 230, 240), pt(0.0, r * 0.25), max(2, ts // 14))
        if ready:
            ring = r * (1.25 + 0.1 * pulse)
            pygame.draw.circle(
                surface, theme.scale(theme.HUNTER, 0.5 + 0.4 * pulse), (cx, cy), ring, 1
            )

    # --- Human helpers --------------------------------------------------------

    def human_hints(self, state: GameState, legal: list[Action]) -> list[tuple[Action, list[int]]]:
        out = []
        for a in legal:
            path = path_of(self.map, state, state.to_move, a)
            if path:
                out.append((a, path))
        return out
