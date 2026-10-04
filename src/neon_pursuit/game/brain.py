"""Runs agent decisions off the UI thread.

Agents are CPU-bound pure Python, so they run in a single worker *process*
(not a thread) to keep the render loop at a steady frame rate despite the GIL.
Agents are stateful (each owns a seeded RNG), so they live inside the worker
and are addressed by ``(match_id, role)``.

This module must not import pygame: it is imported by the worker process.
"""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import Executor as _Executor
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor

from ..ai import Agent, AgentSettings, AlgorithmId, Decision, create_agent
from ..engine import GameState, MatchConfig, Role, generate_map

_AGENTS: dict[tuple[int, Role], Agent] = {}


def _think(
    match_id: int,
    role: Role,
    algorithm: AlgorithmId,
    config: MatchConfig,
    seed: int,
    settings: AgentSettings,
    state: GameState,
) -> Decision:
    key = (match_id, role)
    agent = _AGENTS.get(key)
    if agent is None or agent.algorithm is not algorithm:
        # Drop agents from finished matches so the worker does not grow forever.
        for stale in [k for k in _AGENTS if k[0] != match_id]:
            del _AGENTS[stale]
        agent = create_agent(algorithm, role, generate_map(config), config, seed, settings)
        _AGENTS[key] = agent
    return agent.decide(state)


def _warmup() -> bool:
    return True


class Brain:
    """Submits ``decide`` calls to a background worker and returns futures."""

    def __init__(self, use_process: bool = True) -> None:
        self._executor: _Executor
        if use_process:
            try:
                self._executor = ProcessPoolExecutor(
                    max_workers=1, mp_context=mp.get_context("spawn")
                )
                self._executor.submit(_warmup)
            except (OSError, RuntimeError):  # pragma: no cover - restricted environments
                self._executor = ThreadPoolExecutor(max_workers=1)
        else:
            self._executor = ThreadPoolExecutor(max_workers=1)

    def think(
        self,
        match_id: int,
        role: Role,
        algorithm: AlgorithmId,
        config: MatchConfig,
        seed: int,
        settings: AgentSettings,
        state: GameState,
    ) -> Future[Decision]:
        return self._executor.submit(
            _think, match_id, role, algorithm, config, seed, settings, state
        )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
