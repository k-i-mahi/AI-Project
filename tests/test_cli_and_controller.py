from __future__ import annotations

import time
from pathlib import Path

import pytest

from neon_pursuit.ai import AlgorithmId
from neon_pursuit.cli import ascii_board, build_parser, main
from neon_pursuit.engine import (
    Action,
    MatchConfig,
    Role,
    generate_map,
    initial_state,
    legal_actions,
)
from neon_pursuit.game.brain import Brain
from neon_pursuit.game.controller import MatchController, MatchSetup
from neon_pursuit.presets import Difficulty, settings_for


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["play", "--survivor", "human"])
    assert args.hunter is AlgorithmId.MCTS
    assert args.survivor is None
    with pytest.raises(SystemExit):
        build_parser().parse_args(["play", "--hunter", "nope"])


def test_simulate_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["simulate", "--hunter", "greedy", "--survivor", "fuzzy", "--seed", "4", "--render"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "wins" in out
    assert "H" in out and "#" in out


def test_benchmark_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "benchmark",
            "--hunters",
            "greedy",
            "--survivors",
            "random",
            "greedy",
            "--games",
            "2",
            "--workers",
            "1",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert len(list(tmp_path.glob("*.md"))) == 1
    assert "| greedy | random |" in capsys.readouterr().out


def test_ascii_board() -> None:
    cfg = MatchConfig()
    m = generate_map(cfg)
    art = ascii_board(m, initial_state(m, cfg))
    assert art.count("\n") == m.height - 1
    assert art.count("*") == cfg.active_cores


def test_presets_scale_search_budget() -> None:
    easy, hard = settings_for(Difficulty.EASY), settings_for(Difficulty.HARD)
    assert easy.mcts.iterations < hard.mcts.iterations
    assert easy.minimax.max_depth < hard.minimax.max_depth


def _wait(ctrl: MatchController, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not ctrl.ai_ready():
        assert time.monotonic() < deadline, "AI did not answer"
        time.sleep(0.005)


def test_controller_human_and_ai_turns() -> None:
    brain = Brain(use_process=False)
    try:
        setup = MatchSetup(hunter=AlgorithmId.GREEDY, survivor=None, config=MatchConfig(seed=8))
        ctrl = MatchController(setup, brain)
        assert ctrl.is_human_turn()
        ctrl.request_ai()  # no-op on a human turn
        assert not ctrl.ai_ready()

        illegal = next(a for a in Action if a not in legal_actions(ctrl.map, ctrl.state))
        assert ctrl.play_human(illegal) is None
        turn = ctrl.play_human(Action.WAIT)
        assert turn is not None and turn.role is Role.SURVIVOR

        ctrl.request_ai()
        assert ctrl.thinking
        _wait(ctrl)
        ai_turn = ctrl.commit_ai()
        assert ai_turn is not None and ai_turn.role is Role.HUNTER
        assert ctrl.insights[Role.HUNTER] is not None
        assert len(ctrl.history) == 2
    finally:
        brain.shutdown()


def test_controller_plays_full_ai_match() -> None:
    brain = Brain(use_process=False)
    try:
        settings = settings_for(Difficulty.EASY)
        setup = MatchSetup(
            AlgorithmId.GREEDY, AlgorithmId.RANDOM, MatchConfig(seed=2), settings, settings
        )
        ctrl = MatchController(setup, brain)
        while not ctrl.is_over:
            ctrl.request_ai()
            _wait(ctrl)
            ctrl.commit_ai()
        assert ctrl.state.is_terminal
        assert ctrl.think_ms[Role.HUNTER]
    finally:
        brain.shutdown()
