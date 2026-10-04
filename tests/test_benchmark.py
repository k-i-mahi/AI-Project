from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from neon_pursuit.ai import AlgorithmId
from neon_pursuit.benchmark.report import markdown_table, write_reports
from neon_pursuit.benchmark.runner import (
    MatchResult,
    MatchSpec,
    build_specs,
    play_match,
    run_tournament,
    summarise,
)
from neon_pursuit.engine import MatchConfig


def test_play_match_terminates_and_is_reproducible() -> None:
    spec = MatchSpec(AlgorithmId.GREEDY, AlgorithmId.FUZZY, MatchConfig(seed=11))
    a = play_match(spec)
    b = play_match(spec)
    assert a.winner in ("hunter", "survivor")
    assert a.reason in ("captured", "starved", "cores_collected", "survived")
    assert (a.winner, a.reason, a.rounds, a.cores) == (b.winner, b.reason, b.rounds, b.cores)


def test_build_specs_shares_seeds_across_matchups() -> None:
    pairs = [(AlgorithmId.GREEDY, AlgorithmId.RANDOM), (AlgorithmId.RANDOM, AlgorithmId.GREEDY)]
    specs = build_specs(pairs, 3, MatchConfig(seed=50))
    assert len(specs) == 6
    assert [s.config.seed for s in specs[:3]] == [50, 51, 52]
    assert [s.config.seed for s in specs[3:]] == [50, 51, 52]


@pytest.fixture
def results() -> list[MatchResult]:
    pairs = [(AlgorithmId.GREEDY, AlgorithmId.RANDOM), (AlgorithmId.RANDOM, AlgorithmId.GREEDY)]
    progress: list[int] = []
    out = run_tournament(
        build_specs(pairs, 2, MatchConfig(seed=3)),
        workers=1,
        on_result=lambda _r, d, _t: progress.append(d),
    )
    assert progress == [1, 2, 3, 4]
    return out


def test_summarise(results: list[MatchResult]) -> None:
    summaries = summarise(results)
    assert len(summaries) == 2
    for s in summaries:
        assert s.games == 2
        assert s.hunter_wins + s.survivor_wins == 2
        assert s.captures + s.escapes + s.timeouts + (s.hunter_wins - s.captures) == 2
        assert 0.0 <= s.hunter_win_rate <= 1.0
    table = markdown_table(summaries)
    assert table.count("\n") == 4


def test_write_reports(results: list[MatchResult], tmp_path: Path) -> None:
    paths = write_reports(results, tmp_path, stem="run")
    assert {p.suffix for p in paths} == {".csv", ".json", ".md"}
    rows = list(csv.DictReader((tmp_path / "run.csv").open(encoding="utf-8")))
    assert len(rows) == 4
    data = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert len(data["matches"]) == 4 and len(data["summary"]) == 2
