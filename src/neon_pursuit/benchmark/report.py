"""Export tournament results as CSV, JSON and a Markdown table."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .runner import MatchResult, MatchupSummary, summarise


def markdown_table(summaries: list[MatchupSummary]) -> str:
    header = (
        "| Hunter | Survivor | Games | Hunter win % | 95% CI | Captures | Starved | Escapes "
        "| Timeouts | Avg rounds | Avg cores | Hunter ms/move | Survivor ms/move |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    rows = [
        f"| {s.hunter} | {s.survivor} | {s.games} | {s.hunter_win_rate:.0%} "
        f"| {s.hunter_win_ci[0]:.0%}-{s.hunter_win_ci[1]:.0%} | {s.captures} "
        f"| {s.hunter_wins - s.captures} | {s.escapes} | {s.timeouts} | {s.avg_rounds:.1f} "
        f"| {s.avg_cores:.1f} | {s.hunter_ms:.1f} | {s.survivor_ms:.1f} |"
        for s in sorted(summaries, key=lambda s: (s.hunter, s.survivor))
    ]
    return header + "\n".join(rows) + "\n"


def write_reports(results: list[MatchResult], out_dir: Path, stem: str | None = None) -> list[Path]:
    """Write ``<stem>.csv`` (per match), ``<stem>.json`` and ``<stem>.md`` (summary)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or f"benchmark_{datetime.now():%Y%m%d_%H%M%S}"
    summaries = summarise(results)

    csv_path = out_dir / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fields = list(MatchResult.__dataclass_fields__)
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())

    json_path = out_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(
            {
                "matches": [r.to_dict() for r in results],
                "summary": [
                    {
                        **{f: getattr(s, f) for f in s.__dataclass_fields__},
                        "hunter_win_rate": s.hunter_win_rate,
                    }
                    for s in summaries
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    md_path = out_dir / f"{stem}.md"
    md_path.write_text(
        f"# Neon Pursuit benchmark — {stem}\n\n{markdown_table(summaries)}", encoding="utf-8"
    )
    return [csv_path, json_path, md_path]
