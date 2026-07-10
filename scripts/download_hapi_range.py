#!/usr/bin/env python3
"""Download multiple UTC days of INTERMAGNET HAPI data as CSV files."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from download_hapi_day import EUROPE_STATIONS, build_parser, download_one  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = build_parser(
        "Download a UTC date range from the BGS INTERMAGNET HAPI server.",
        include_date=False,
    )
    parser.add_argument(
        "--start-date",
        default="2022-01-01",
        help="First UTC date to download, YYYY-MM-DD. Default: 2022-01-01.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of consecutive days to download. Default: 1.",
    )
    return parser.parse_args()


def iter_days(start_date: str, days: int) -> list[str]:
    if days < 1:
        raise ValueError("--days must be at least 1.")
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days)]


def station_codes(args: argparse.Namespace) -> tuple[str, ...]:
    if args.all_europe:
        return EUROPE_STATIONS
    return tuple(code.strip().upper() for code in args.stations.split(",") if code.strip())


def main() -> int:
    args = parse_args()
    try:
        days = iter_days(args.start_date, args.days)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    stations = station_codes(args)
    if not stations:
        print("No station codes were provided.", file=sys.stderr)
        return 2

    failures = 0
    for day_text in days:
        print(f"[DAY] {day_text}")
        for station in stations:
            try:
                output_path, row_count = download_one(args, station, day_text=day_text)
            except Exception as exc:
                failures += 1
                print(f"[FAIL] {day_text} {station}: {exc}", file=sys.stderr)
                continue
            print(f"[OK] {day_text} {station}: wrote {row_count} rows -> {output_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())