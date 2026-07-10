#!/usr/bin/env python3
"""Concurrent batch downloader for 2022 European INTERMAGNET HAPI data."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from download_hapi_day import (  # noqa: E402
    EUROPE_STATIONS,
    HapiStatusError,
    build_parser,
    dataset_id,
    download_one,
    expected_output_path,
)


@dataclass(frozen=True)
class DownloadTask:
    station: str
    day: str


@dataclass(frozen=True)
class DownloadResult:
    station: str
    day: str
    dataset: str
    status: str
    output_path: str
    rows: int
    attempts: int
    error_type: str
    hapi_status_code: str
    hapi_status_message: str
    error: str


def parse_args() -> argparse.Namespace:
    parser = build_parser(
        "Download 2022 European INTERMAGNET HAPI data concurrently.",
        include_date=False,
    )
    for action in parser._actions:
        if action.dest == "stations":
            action.default = ",".join(EUROPE_STATIONS)
            action.help = "Comma-separated IAGA station codes. Default: embedded Europe list."

    parser.add_argument(
        "--year",
        type=int,
        default=2022,
        help="UTC year to download when --start-date/--days are not set. Default: 2022.",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="Optional first UTC date, YYYY-MM-DD. Overrides --year with --days.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="Optional number of consecutive days used with --start-date.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Number of concurrent download workers. Default: 6.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Retries per station-day task after the first failure. Default: 2.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=2.0,
        help="Base seconds to wait between retries. Default: 2.0.",
    )
    parser.add_argument(
        "--log-dir",
        default="data/logs",
        help="Directory for success/failure CSV logs. Default: data/logs.",
    )
    parser.add_argument(
        "--from-failures",
        default="",
        help="Retry only tasks listed in a previous failures CSV.",
    )
    return parser.parse_args()


def station_codes(args: argparse.Namespace) -> tuple[str, ...]:
    if args.all_europe:
        return EUROPE_STATIONS
    return tuple(code.strip().upper() for code in args.stations.split(",") if code.strip())


def iter_year_days(year: int) -> list[str]:
    start = date(year, 1, 1)
    stop = date(year + 1, 1, 1)
    count = (stop - start).days
    return [(start + timedelta(days=offset)).isoformat() for offset in range(count)]


def iter_range_days(start_date: str, days: int) -> list[str]:
    if not start_date:
        raise ValueError("--start-date is required when --days is set.")
    if days < 1:
        raise ValueError("--days must be at least 1.")
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days)]


def load_failure_tasks(path: Path) -> list[DownloadTask]:
    tasks: list[DownloadTask] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            station = (row.get("station") or "").strip().upper()
            day = (row.get("day") or row.get("date") or "").strip()
            if station and day:
                tasks.append(DownloadTask(station=station, day=day))
    return dedupe_tasks(tasks)


def build_tasks(args: argparse.Namespace) -> list[DownloadTask]:
    if args.from_failures:
        return load_failure_tasks(Path(args.from_failures))

    days = iter_range_days(args.start_date, args.days) if args.start_date or args.days else iter_year_days(args.year)
    stations = station_codes(args)
    if not stations:
        raise ValueError("No station codes were provided.")
    return [DownloadTask(station=station, day=day) for station in stations for day in days]


def dedupe_tasks(tasks: list[DownloadTask]) -> list[DownloadTask]:
    seen: set[tuple[str, str]] = set()
    unique: list[DownloadTask] = []
    for task in tasks:
        key = (task.station, task.day)
        if key in seen:
            continue
        seen.add(key)
        unique.append(task)
    return unique


def task_dataset(args: argparse.Namespace, station: str) -> str:
    return dataset_id(station, args.data_type, args.cadence, args.components)


def exception_fields(exc: Exception) -> tuple[str, str, str, str]:
    status_code = ""
    status_message = ""
    if isinstance(exc, HapiStatusError):
        status_code = "" if exc.status_code is None else str(exc.status_code)
        status_message = exc.status_message or ""
    return type(exc).__name__, status_code, status_message, str(exc)


def run_task(args: argparse.Namespace, task: DownloadTask) -> DownloadResult:
    station = task.station.upper()
    dataset = task_dataset(args, station)
    output_path = expected_output_path(args, station, task.day)

    if output_path.exists() and output_path.stat().st_size > 0 and not args.overwrite:
        return DownloadResult(
            station=station,
            day=task.day,
            dataset=dataset,
            status="SKIP",
            output_path=str(output_path),
            rows=0,
            attempts=0,
            error_type="",
            hapi_status_code="",
            hapi_status_message="",
            error="existing file",
        )

    last_exc: Exception | None = None
    total_attempts = args.max_retries + 1
    for attempt in range(1, total_attempts + 1):
        try:
            path, rows = download_one(args, station, day_text=task.day)
        except Exception as exc:
            last_exc = exc
            if attempt < total_attempts:
                time.sleep(args.retry_delay * attempt)
            continue

        return DownloadResult(
            station=station,
            day=task.day,
            dataset=dataset,
            status="OK",
            output_path=str(path),
            rows=rows,
            attempts=attempt,
            error_type="",
            hapi_status_code="",
            hapi_status_message="",
            error="",
        )

    assert last_exc is not None
    error_type, status_code, status_message, error = exception_fields(last_exc)
    return DownloadResult(
        station=station,
        day=task.day,
        dataset=dataset,
        status="FAIL",
        output_path=str(output_path),
        rows=0,
        attempts=total_attempts,
        error_type=error_type,
        hapi_status_code=status_code,
        hapi_status_message=status_message,
        error=error,
    )


def write_log(path: Path, rows: list[DownloadResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "station",
        "day",
        "dataset",
        "status",
        "output_path",
        "rows",
        "attempts",
        "error_type",
        "hapi_status_code",
        "hapi_status_message",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def main() -> int:
    args = parse_args()
    if args.workers < 1:
        print("--workers must be at least 1.", file=sys.stderr)
        return 2
    if args.max_retries < 0:
        print("--max-retries must be at least 0.", file=sys.stderr)
        return 2

    try:
        tasks = build_tasks(args)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not tasks:
        print("No download tasks were built.", file=sys.stderr)
        return 2

    print(
        f"[BATCH] tasks={len(tasks)} workers={args.workers} "
        f"dataset={args.data_type}/{args.cadence}/{args.components}"
    )

    results: list[DownloadResult] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_task, args, task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            if result.status == "FAIL":
                print(f"[FAIL] {result.day} {result.station}: {result.error}", file=sys.stderr)
            elif result.status == "SKIP":
                print(f"[{index}/{len(tasks)}] SKIP {result.day} {result.station}")
            else:
                print(f"[{index}/{len(tasks)}] OK {result.day} {result.station}: {result.rows} rows")

    ok_rows = [row for row in results if row.status in {"OK", "SKIP"}]
    fail_rows = [row for row in results if row.status == "FAIL"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path(args.log_dir)
    success_log = log_dir / f"hapi_batch_success_{stamp}.csv"
    failure_log = log_dir / f"hapi_batch_failures_{stamp}.csv"
    write_log(success_log, ok_rows)
    write_log(failure_log, fail_rows)

    print(f"[LOG] success -> {success_log}")
    print(f"[LOG] failures -> {failure_log}")
    print(f"[DONE] ok_or_skip={len(ok_rows)} failed={len(fail_rows)} total={len(results)}")
    return 1 if fail_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())