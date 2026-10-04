"""The arena: live match between two controllers (AI or human)."""

from __future__ import annotations

import dataclasses
import math
from typing import TYPE_CHECKING

import pygame

from ...ai import ALGORITHMS
from ...engine import (
    Action,
    CaptureEvent,
    CoreCollectedEvent,
    MatchEndEvent,
    MoveEvent,
    Role,
    Status,
    WinReason,
    legal_actions,
    path_of,
)
from .. import theme
from ..controller import MatchController, MatchSetup, Turn
from ..panels import draw_brain_panel
from ..render import BoardView, Overlays
from ..widgets import Button, Selector, Toggle, draw_bar
from .base import Scene

if TYPE_CHECKING:
    from ..app import App

LEFT_PANEL = pygame.Rect(24, 102, 360, 702)
RIGHT_PANEL = pygame.Rect(1216, 102, 360, 702)
BOARD_AREA = pygame.Rect(400, 102, 800, 600)
TOP_BAR = pygame.Rect(24, 16, 1552, 72)
BOTTOM_BAR = pygame.Rect(24, 818, 1552, 66)

SPEEDS = [(0.5, "0.5×"), (1.0, "1×"), (2.0, "2×"), (4.0, "4×"), (8.0, "8×")]
DIRECTION_KEYS = {
    pygame.K_UP: 1,
    pygame.K_w: 1,
    pygame.K_RIGHT: 2,
    pygame.K_d: 2,
    pygame.K_DOWN: 3,
    pygame.K_s: 3,
    pygame.K_LEFT: 4,
    pygame.K_a: 4,
}


class MatchScene(Scene):
    controller: MatchController
    board: BoardView

    def __init__(self, app: App, setup: MatchSetup) -> None:
        super().__init__(app)
        self.setup = setup
        self.overlays = Overlays()
        self.paused = False
        self.speed = 1.0
        self.log: list[tuple[str, theme.Color]] = []
        self.since_move = 0.0
        self.end_timer = 0.0
        self._new_match(setup)
        self._build_widgets()

    # --- Setup ----------------------------------------------------------------

    def _new_match(self, setup: MatchSetup) -> None:
        if hasattr(self, "controller"):
            self.controller.cancel()
        self.setup = setup
        self.controller = MatchController(setup, self.app.brain)
        self.board = BoardView(self.controller.map, setup.config, BOARD_AREA)
        self.board.reset(self.controller.state)
        self.log = [("Match start — the Survivor moves first.", theme.TEXT_DIM)]
        self.end_timer = 0.0
        self.since_move = 0.0

    def _build_widgets(self) -> None:
        y = 716
        self.pause_button = Button(
            pygame.Rect(400, y, 130, 46), "Pause", self.toggle_pause, theme.ACCENT, size=20
        )
        self.widgets = [
            self.pause_button,
            Button(pygame.Rect(538, y, 96, 46), "Step", self.step_once, theme.ACCENT, size=20),
            Button(pygame.Rect(642, y, 120, 46), "Restart", self.restart, theme.ACCENT, size=20),
            Button(pygame.Rect(770, y, 120, 46), "New map", self.new_map, theme.ACCENT, size=20),
            Selector(pygame.Rect(898, y, 150, 46), SPEEDS, 1, theme.ACCENT, self._set_speed),
            Button(pygame.Rect(1056, y, 144, 46), "Menu", self.app.pop, theme.HUNTER, size=20),
            Toggle(
                pygame.Rect(404, 772, 150, 26),
                "AI plans",
                self.overlays.plans,
                theme.ACCENT,
                "L",
                self._set_plans,
            ),
            Toggle(
                pygame.Rect(600, 772, 150, 26),
                "Territory",
                self.overlays.territory,
                theme.ACCENT,
                "T",
                self._set_territory,
            ),
            Toggle(
                pygame.Rect(800, 772, 180, 26),
                "Hunter reach",
                self.overlays.danger,
                theme.ACCENT,
                "H",
                self._set_danger,
            ),
        ]
        self.toggles = {w.hotkey_hint: w for w in self.widgets if isinstance(w, Toggle)}

    def _set_speed(self, value: float) -> None:
        self.speed = value

    def _set_plans(self, v: bool) -> None:
        self.overlays.plans = v

    def _set_territory(self, v: bool) -> None:
        self.overlays.territory = v

    def _set_danger(self, v: bool) -> None:
        self.overlays.danger = v

    # --- Commands -------------------------------------------------------------

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.label = "Resume" if self.paused else "Pause"

    def step_once(self) -> None:
        if not self.paused:
            self.toggle_pause()
        if not self.board.animating:
            self._commit_ai(force=True)

    def restart(self) -> None:
        self._new_match(self.setup)

    def new_map(self) -> None:
        config = dataclasses.replace(self.setup.config, seed=self.setup.config.seed + 1)
        self._new_match(dataclasses.replace(self.setup, config=config))

    def on_exit(self) -> None:
        self.controller.cancel()

    # --- Input ----------------------------------------------------------------

    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            key = event.key
            if key == pygame.K_ESCAPE:
                self.app.pop()
            elif key == pygame.K_p:
                self.toggle_pause()
            elif key == pygame.K_n:
                self.step_once()
            elif key == pygame.K_r:
                self.restart()
            elif key == pygame.K_m:
                self.new_map()
            elif key == pygame.K_l:
                self.toggles["L"].flip()
            elif key == pygame.K_t:
                self.toggles["T"].flip()
            elif key == pygame.K_h:
                self.toggles["H"].flip()
            elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self._speed_widget().step(1)
            elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._speed_widget().step(-1)
            elif self.controller.is_human_turn():
                self._human_key(event)
        elif (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.controller.is_human_turn()
        ):
            self._human_click(event.pos)

    def _speed_widget(self) -> Selector[float]:
        return next(w for w in self.widgets if isinstance(w, Selector))

    def _human_key(self, event: pygame.event.Event) -> None:
        if self.board.animating:
            return
        if event.key == pygame.K_SPACE:
            self._play_human(Action.WAIT)
            return
        direction = DIRECTION_KEYS.get(event.key)
        if direction is None:
            return
        burst = bool(event.mod & pygame.KMOD_SHIFT)
        self._play_human(Action(direction + (4 if burst else 0)))

    def _human_click(self, pos: tuple[int, int]) -> None:
        if self.board.animating or not self.board.rect.collidepoint(pos):
            return
        gx = (pos[0] - self.board.rect.left) // self.board.tile
        gy = (pos[1] - self.board.rect.top) // self.board.tile
        target = self.controller.map.cell(gx, gy)
        state = self.controller.state
        for action in legal_actions(self.controller.map, state):
            path = path_of(self.controller.map, state, state.to_move, action)
            if path and path[-1] == target:
                self._play_human(action)
                return

    def _play_human(self, action: Action) -> None:
        turn = self.controller.play_human(action)
        if turn is None:
            self._log("That move is blocked.", theme.WARNING)
            return
        self._after_turn(turn)

    # --- Simulation -------------------------------------------------------------

    @property
    def anim_duration(self) -> float:
        return 0.24 / self.speed

    def _commit_ai(self, force: bool = False) -> None:
        if not (force or not self.paused):
            return
        turn = self.controller.commit_ai()
        if turn is not None:
            self._after_turn(turn)

    def _after_turn(self, turn: Turn) -> None:
        self.board.animate(turn, self.anim_duration)
        self.since_move = 0.0
        self._log_turn(turn)

    def update(self, dt: float) -> None:
        super().update(dt)
        self.board.update(dt)
        self.since_move += dt
        ctrl = self.controller
        if ctrl.is_over:
            self.end_timer += dt
            return
        ctrl.request_ai()
        delay = 0.08 / self.speed
        if (
            not self.paused
            and not self.board.animating
            and self.since_move >= delay
            and ctrl.ai_ready()
        ):
            self._commit_ai()

    # --- Log --------------------------------------------------------------------

    def _log(self, message: str, color: theme.Color) -> None:
        self.log.append((message, color))
        self.log = self.log[-4:]

    def _log_turn(self, turn: Turn) -> None:
        r = turn.before.round + 1
        name = turn.role.value.capitalize()
        color = theme.ROLE_COLOR[turn.role]
        for ev in turn.events:
            if isinstance(ev, MoveEvent) and ev.action.is_burst:
                verb = "dashed" if turn.role is Role.SURVIVOR else "pounced"
                self._log(f"R{r} · {name} {verb} {ev.action.label.split()[-1].lower()}", color)
            elif isinstance(ev, CoreCollectedEvent):
                self._log(
                    f"R{r} · Core collected ({ev.total}/{self.setup.config.cores_to_win}) "
                    f"+{self.setup.config.core_energy} energy",
                    theme.CORE,
                )
            elif isinstance(ev, CaptureEvent):
                self._log(f"R{r} · CAPTURED!", theme.HUNTER)
            elif isinstance(ev, MatchEndEvent) and ev.reason is not WinReason.CAPTURED:
                msg = {
                    WinReason.CORES_COLLECTED: "The Survivor escaped with enough cores!",
                    WinReason.SURVIVED: "The Survivor outlasted the Hunter!",
                    WinReason.STARVED: "The Survivor ran out of energy.",
                }[ev.reason]
                self._log(
                    f"R{r} · {msg}",
                    theme.SUCCESS if ev.status is Status.SURVIVOR_WIN else theme.HUNTER,
                )

    # --- Drawing ----------------------------------------------------------------

    def draw_content(self, surface: pygame.Surface) -> None:
        ctrl = self.controller
        state = ctrl.state
        self._draw_top_bar(surface)

        plans = {}
        for role in Role:
            ins = ctrl.insights[role]
            if ins is not None and ctrl.setup.controller(role) is not None:
                plans[role] = ins.plan
        hints = None
        if ctrl.is_human_turn() and not self.board.animating:
            hints = self.board.human_hints(state, legal_actions(ctrl.map, state))
        self.board.draw(surface, state, self.overlays, plans, hints)

        for role, rect in ((Role.HUNTER, LEFT_PANEL), (Role.SURVIVOR, RIGHT_PANEL)):
            draw_brain_panel(
                surface,
                rect,
                role,
                ctrl.setup.controller(role),
                ctrl.insights[role],
                ctrl.thinking and state.to_move is role,
                ctrl.think_ms[role],
                self.app.time,
                state.to_move is role and not ctrl.is_over,
            )
        self._draw_bottom_bar(surface)
        if self.paused and not ctrl.is_over:
            theme.blit_text(
                surface,
                "PAUSED",
                (self.board.rect.centerx, self.board.rect.top + 24),
                "display",
                22,
                theme.WARNING,
                "center",
            )

    def draw(self, surface: pygame.Surface) -> None:
        super().draw(surface)
        if self.controller.is_over and self.end_timer > 0.6:
            self._draw_end(surface)

    def _draw_top_bar(self, surface: pygame.Surface) -> None:
        cfg = self.setup.config
        state = self.controller.state
        theme.panel(surface, TOP_BAR)
        y = TOP_BAR.centery
        theme.blit_text(
            surface, "NEON PURSUIT", (TOP_BAR.left + 20, y), "display", 22, theme.TEXT, "midleft"
        )
        hunter = self._controller_name(Role.HUNTER)
        survivor = self._controller_name(Role.SURVIVOR)
        x = TOP_BAR.left + 250
        r1 = theme.blit_text(surface, hunter, (x, y), "ui_bold", 20, theme.HUNTER, "midleft")
        r2 = theme.blit_text(surface, " vs ", (r1.right, y), "ui", 18, theme.TEXT_DIM, "midleft")
        theme.blit_text(surface, survivor, (r2.right, y), "ui_bold", 20, theme.SURVIVOR, "midleft")

        # Round progress.
        x = 760
        theme.blit_text(surface, "ROUND", (x, y - 14), "ui", 13, theme.TEXT_DIM, "midleft")
        theme.blit_text(
            surface,
            f"{state.round}/{cfg.max_rounds}",
            (x, y + 8),
            "mono",
            18,
            theme.TEXT,
            "midleft",
        )

        # Cores.
        x = 880
        theme.blit_text(surface, "CORES", (x, y - 14), "ui", 13, theme.TEXT_DIM, "midleft")
        for i in range(cfg.cores_to_win):
            cx, cy = x + 8 + i * 20, y + 10
            filled = i < state.cores_collected
            pts = [(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)]
            if filled:
                theme.blit_glow(surface, (cx, cy), 14, theme.CORE, 0.5)
                pygame.draw.polygon(surface, theme.CORE, pts)
            else:
                pygame.draw.polygon(surface, theme.GRID, pts, 2)

        # Energy.
        x = 1080
        frac = state.energy / cfg.max_energy
        theme.blit_text(
            surface, f"ENERGY  {state.energy}", (x, y - 14), "ui", 13, theme.TEXT_DIM, "midleft"
        )
        color = (
            theme.SUCCESS
            if frac >= 0.3
            else theme.mix(theme.WARNING, theme.HUNTER, 0.5 + 0.5 * math.sin(self.app.time * 8))
        )
        draw_bar(surface, pygame.Rect(x, y + 3, 200, 12), frac, color, radius=6)

        # Abilities.
        x = 1310
        dash = "READY" if state.dash_cooldown == 0 else f"{state.dash_cooldown}"
        pounce = "READY" if state.pounce_cooldown == 0 else f"{state.pounce_cooldown}"
        theme.blit_text(
            surface, f"POUNCE {pounce}", (x, y - 12), "mono", 14, theme.HUNTER_SOFT, "midleft"
        )
        theme.blit_text(
            surface, f"DASH   {dash}", (x, y + 10), "mono", 14, theme.SURVIVOR_SOFT, "midleft"
        )

    def _controller_name(self, role: Role) -> str:
        algorithm = self.setup.controller(role)
        return "You" if algorithm is None else ALGORITHMS[algorithm].short

    def _draw_bottom_bar(self, surface: pygame.Surface) -> None:
        theme.panel(surface, BOTTOM_BAR)
        x = BOTTOM_BAR.left + 20
        y = BOTTOM_BAR.top + 10
        for i, (msg, color) in enumerate(reversed(self.log[-2:])):
            theme.blit_text(
                surface,
                msg,
                (x, y + i * 24),
                "ui",
                18 if i == 0 else 16,
                color if i == 0 else theme.scale(color, 0.6),
            )
        hint = (
            "P pause · N step · R restart · M new map · +/− speed · "
            "L/T/H overlays · Esc menu · F11 fullscreen"
        )
        theme.blit_text(
            surface,
            hint,
            (BOTTOM_BAR.right - 20, BOTTOM_BAR.centery),
            "ui",
            15,
            theme.TEXT_FAINT,
            "midright",
        )

    def _draw_end(self, surface: pygame.Surface) -> None:
        state = self.controller.state
        hunter_won = state.status is Status.HUNTER_WIN
        color = theme.HUNTER if hunter_won else theme.SURVIVOR
        fade = min(1.0, (self.end_timer - 0.6) / 0.4)
        veil = pygame.Surface(self.board.rect.size, pygame.SRCALPHA)
        veil.fill((5, 6, 16, round(170 * fade)))
        surface.blit(veil, self.board.rect.topleft)
        cx, cy = self.board.rect.center
        theme.blit_glow(surface, (cx, cy - 40), 260, color, 0.35 * fade)
        title = "HUNTER WINS" if hunter_won else "SURVIVOR WINS"
        theme.blit_text(surface, title, (cx, cy - 70), "display", 52, color, "center")
        reason = {
            WinReason.CAPTURED: "Captured — the Hunter closed the distance.",
            WinReason.STARVED: "Starved — every core was too well guarded.",
            WinReason.CORES_COLLECTED: "Escaped — collected every core it needed.",
            WinReason.SURVIVED: "Survived — outlasted the round limit.",
        }[state.win_reason or WinReason.SURVIVED]
        theme.blit_text(surface, reason, (cx, cy - 18), "ui", 22, theme.TEXT, "center")
        ms = self.controller.think_ms
        avg = {r: (sum(v) / len(v) if v else 0.0) for r, v in ms.items()}
        stats = (
            f"{state.round} rounds  ·  {state.cores_collected} "
            f"core{'' if state.cores_collected == 1 else 's'}  ·  "
            f"think time H {avg[Role.HUNTER]:.0f} ms / S {avg[Role.SURVIVOR]:.0f} ms"
        )
        theme.blit_text(surface, stats, (cx, cy + 16), "mono", 15, theme.TEXT_DIM, "center")
        theme.blit_text(
            surface,
            "R  rematch     M  new map     Esc  menu",
            (cx, cy + 62),
            "ui_bold",
            20,
            theme.TEXT,
            "center",
        )
