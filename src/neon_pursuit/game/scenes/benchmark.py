"""Benchmark Lab: run AI-vs-AI tournaments and view a win-rate heatmap."""

from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from ...ai import ALGORITHMS, AlgorithmId
from ...benchmark.report import write_reports
from ...benchmark.runner import MatchResult, build_specs, play_match, summarise
from ...engine import MatchConfig
from ...presets import Difficulty, settings_for
from .. import theme
from ..widgets import Button, Selector, draw_bar
from .base import Scene

if TYPE_CHECKING:
    from ..app import App

ALGOS = list(AlgorithmId)
GRID = pygame.Rect(330, 190, 760, 560)
GAMES = [(4, "4 games"), (8, "8 games"), (16, "16 games"), (32, "32 games")]
BUDGETS = [(Difficulty.EASY, "Easy budget"), (Difficulty.NORMAL, "Normal budget")]


class BenchmarkScene(Scene):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.selected: set[tuple[AlgorithmId, AlgorithmId]] = {
            (AlgorithmId.MCTS, AlgorithmId.FUZZY),
            (AlgorithmId.FUZZY, AlgorithmId.MCTS),
            (AlgorithmId.FUZZY, AlgorithmId.FUZZY),
            (AlgorithmId.GREEDY, AlgorithmId.FUZZY),
            (AlgorithmId.FUZZY, AlgorithmId.GREEDY),
        }
        self.results: list[MatchResult] = []
        self.futures: list[Future[MatchResult]] = []
        self.total = 0
        self.pool: ProcessPoolExecutor | None = None
        self.message = "Click cells to choose matchups, then press Run."
        self.games = Selector(pygame.Rect(1130, 230, 300, 48), GAMES, 1, theme.CORE)
        self.budget = Selector(pygame.Rect(1130, 290, 300, 48), BUDGETS, 0, theme.CORE)
        self.run_button = Button(
            pygame.Rect(1130, 360, 300, 60), "RUN TOURNAMENT", self.run, theme.SUCCESS, size=24
        )
        self.widgets += [
            self.games,
            self.budget,
            self.run_button,
            Button(
                pygame.Rect(1130, 432, 145, 46),
                "Select all",
                self.select_all,
                theme.ACCENT,
                size=18,
            ),
            Button(pygame.Rect(1285, 432, 145, 46), "Clear", self.clear, theme.ACCENT, size=18),
            Button(
                pygame.Rect(1130, 490, 300, 46),
                "Export CSV / JSON / MD",
                self.export,
                theme.CORE,
                size=18,
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

    # --- Matrix -----------------------------------------------------------------

    def _cell_rect(self, hi: int, si: int) -> pygame.Rect:
        n = len(ALGOS)
        w = GRID.width // n
        h = (GRID.height - 40) // n
        return pygame.Rect(GRID.left + si * w, GRID.top + 40 + hi * h, w - 6, h - 6)

    def on_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.running:
            for hi, h in enumerate(ALGOS):
                for si, s in enumerate(ALGOS):
                    if self._cell_rect(hi, si).collidepoint(event.pos):
                        self.selected ^= {(h, s)}
                        return

    def select_all(self) -> None:
        if not self.running:
            self.selected = {(h, s) for h in ALGOS for s in ALGOS}

    def clear(self) -> None:
        if not self.running:
            self.selected.clear()
            self.results.clear()

    # --- Execution ----------------------------------------------------------------

    @property
    def running(self) -> bool:
        return any(not f.done() for f in self.futures)

    def run(self) -> None:
        if self.running or not self.selected:
            return
        specs = build_specs(
            sorted(self.selected),
            self.games.value,
            MatchConfig(seed=1000),
            settings_for(self.budget.value),
        )
        workers = max(1, (os.cpu_count() or 2) - 1)
        if self.pool is None:
            self.pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"))
        self.results = []
        self.futures = [self.pool.submit(play_match, spec) for spec in specs]
        self.total = len(specs)
        self.message = f"Running {self.total} matches on {workers} worker processes…"

    def export(self) -> None:
        if not self.results:
            self.message = "Nothing to export yet."
            return
        paths = write_reports(self.results, Path.cwd() / "results")
        self.message = f"Saved {paths[0].parent}{os.sep}{paths[0].stem}.*"

    def update(self, dt: float) -> None:
        super().update(dt)
        if not self.futures:
            return
        still: list[Future[MatchResult]] = []
        for f in self.futures:
            if f.done():
                if not f.cancelled() and f.exception() is None:
                    self.results.append(f.result())
            else:
                still.append(f)
        self.futures = still
        if not still and self.total:
            self.message = f"Done — {len(self.results)} matches. Export to save the data."
            self.total = 0
        self.run_button.enabled = not self.running

    def on_exit(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)

    # --- Drawing ----------------------------------------------------------------

    def draw_content(self, surface: pygame.Surface) -> None:
        theme.blit_text(surface, "BENCHMARK LAB", (800, 70), "display", 40, theme.TEXT, "center")
        theme.blit_text(
            surface,
            "Every cell is a matchup. Colour = Hunter win rate "
            "(cyan: Survivor dominates · red: Hunter dominates).",
            (800, 118),
            "ui",
            19,
            theme.TEXT_DIM,
            "center",
        )
        theme.panel(surface, GRID.inflate(40, 40))
        summaries = {(s.hunter, s.survivor): s for s in summarise(self.results)}
        theme.blit_text(
            surface, "SURVIVOR  (columns)", (GRID.left, GRID.top - 6), "ui_bold", 15, theme.SURVIVOR
        )
        theme.blit_text(
            surface,
            "HUNTER (rows)",
            (GRID.left - 16, GRID.top - 6),
            "ui_bold",
            15,
            theme.HUNTER,
            "topright",
        )
        for si, s in enumerate(ALGOS):
            r = self._cell_rect(0, si)
            theme.blit_text(
                surface,
                ALGORITHMS[s].short,
                (r.centerx, GRID.top + 22),
                "ui_bold",
                17,
                theme.SURVIVOR,
                "center",
            )
        for hi, h in enumerate(ALGOS):
            r = self._cell_rect(hi, 0)
            theme.blit_text(
                surface,
                ALGORITHMS[h].short,
                (GRID.left - 16, r.centery),
                "ui_bold",
                17,
                theme.HUNTER,
                "midright",
            )
            for si, s in enumerate(ALGOS):
                cell = self._cell_rect(hi, si)
                summary = summaries.get((h.value, s.value))
                selected = (h, s) in self.selected
                if summary:
                    rate = summary.hunter_win_rate
                    fill = theme.mix(
                        theme.scale(theme.SURVIVOR, 0.55), theme.scale(theme.HUNTER, 0.65), rate
                    )
                    pygame.draw.rect(surface, fill, cell, border_radius=8)
                    theme.blit_text(
                        surface,
                        f"{rate:.0%}",
                        (cell.centerx, cell.centery - 10),
                        "display",
                        22,
                        theme.TEXT,
                        "center",
                    )
                    theme.blit_text(
                        surface,
                        f"{summary.games} g · {summary.avg_rounds:.0f} rds",
                        (cell.centerx, cell.centery + 18),
                        "mono",
                        12,
                        theme.TEXT,
                        "center",
                    )
                else:
                    pygame.draw.rect(
                        surface, theme.GRID if selected else theme.PANEL, cell, border_radius=8
                    )
                    if selected:
                        theme.blit_text(
                            surface,
                            "queued" if self.running else "selected",
                            cell.center,
                            "ui",
                            15,
                            theme.TEXT_DIM,
                            "center",
                        )
                edge = theme.CORE if selected else theme.PANEL_EDGE
                pygame.draw.rect(surface, edge, cell, 2 if selected else 1, border_radius=8)

        panel = pygame.Rect(1110, 190, 340, 560)
        theme.panel(surface, panel.inflate(0, 0))
        theme.blit_text(surface, "TOURNAMENT", (1130, 200), "ui_bold", 16, theme.CORE)
        done = len(self.results)
        total = done + len(self.futures)
        if total:
            draw_bar(
                surface, pygame.Rect(1130, 556, 300, 12), done / total, theme.SUCCESS, radius=6
            )
            theme.blit_text(
                surface, f"{done}/{total} matches", (1130, 576), "mono", 14, theme.TEXT_DIM
            )
        for i, line in enumerate(theme.wrap(self.message, "ui", 17, 300)):
            theme.blit_text(surface, line, (1130, 604 + i * 22), "ui", 17, theme.TEXT)
