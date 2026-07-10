#!/usr/bin/env python3
"""Download one day of INTERMAGNET HAPI data as local CSV files."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://imag-data.bgs.ac.uk/GIN_V1/hapi"

EUROPE_STATIONS = (
    "VAL",
    "STT",
    "SFS",
    "HAD",
    "SPT",
    "ESK",
    "EBR",
    "DOU",
    "MAB",
    "BFO",
    "WNG",
    "FUR",
    "BFE",
    "NGK",
    "AQU",
    "BDV",
    "DUR",
    "WIC",
    "LON",
    "NCK",
    "THY",
    "HRB",
    "HLP",
    "GCK",
    "BEL",
    "LVV",
    "PEG",
    "PAG",
    "SUA",
    "ISK",
    "IZN",
    "KIV",
)


class HapiStatusError(RuntimeError):
    """Raised when a HAPI endpoint returns a non-OK status payload."""

    def __init__(
        self,
        message: str,
        *,
        url: str,
        status_code: int | None = None,
        status_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.status_message = status_message


def parse_args() -> argparse.Namespace:
    parser = build_parser("Download one UTC day from the BGS INTERMAGNET HAPI server.")
    return parser.parse_args()


def build_parser(description: str, include_date: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    if include_date:
        parser.add_argument(
            "--date",
            default="2022-01-01",
            help="UTC date to download, YYYY-MM-DD. Default: 2022-01-01.",
        )
    parser.add_argument(
        "--stations",
        default="VAL",
        help="Comma-separated IAGA station codes. Default: VAL.",
    )
    parser.add_argument(
        "--all-europe",
        action="store_true",
        help="Download the European station list embedded in this script.",
    )
    parser.add_argument(
        "--data-type",
        default="definitive",
        choices=("adjusted", "definitive", "quasi-def", "reported", "best-avail"),
        help="HAPI data type. Use best-avail for recent data. Default: definitive.",
    )
    parser.add_argument(
        "--cadence",
        default="PT1M",
        choices=("PT1M", "PT1S"),
        help="HAPI cadence. Default: PT1M.",
    )
    parser.add_argument(
        "--components",
        default="xyzf",
        choices=("xyzf", "hdzf", "diff", "native"),
        help="Coordinate components. Default: xyzf.",
    )
    parser.add_argument(
        "--parameters",
        default="",
        help=(
            "Comma-separated HAPI parameter names, excluding Time. "
            "Default: all non-Time parameters from /info."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="data",
        help="Directory for output CSV files. Default: data.",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"HAPI base URL. Default: {BASE_URL}.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing CSV files.",
    )
    return parser


def utc_day_bounds(day_text: str) -> tuple[date, str, str]:
    day = datetime.strptime(day_text, "%Y-%m-%d").date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    stop = start + timedelta(days=1)
    return day, hapi_time(start), hapi_time(stop)


def hapi_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_url(base_url: str, endpoint: str, query: dict[str, str]) -> str:
    return f"{base_url.rstrip('/')}/{endpoint}?{urlencode(query)}"


def request_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "geomagnetic-hapi-downloader/1.0"})
    try:
        with urlopen(request, timeout=60) as response:
            return response.read()
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            error = hapi_status_error(data, url)
            if error is not None:
                raise error from exc
        raise RuntimeError(f"HTTP {exc.code} for {url}\n{message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to {url}: {exc.reason}") from exc


def hapi_status_error(data: dict[str, Any], url: str) -> HapiStatusError | None:
    status = data.get("status")
    if not isinstance(status, dict):
        return HapiStatusError("HAPI response did not include a status object.", url=url)

    code = status.get("code")
    if code == 1200:
        return None

    message = str(status.get("message", "unknown HAPI error"))
    return HapiStatusError(
        f"HAPI status {code}: {message}",
        url=url,
        status_code=code if isinstance(code, int) else None,
        status_message=message,
    )


def request_json(url: str) -> dict[str, Any]:
    payload = request_bytes(url).decode("utf-8")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON from {url}, got:\n{payload[:500]}") from exc

    error = hapi_status_error(data, url)
    if error is not None:
        raise error
    return data


def raise_if_hapi_error_payload(payload: bytes, url: str) -> None:
    stripped = payload.lstrip()
    if not stripped.startswith(b"{"):
        return

    try:
        data = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return

    error = hapi_status_error(data, url)
    if error is not None:
        raise error


def dataset_id(station: str, data_type: str, cadence: str, components: str) -> str:
    return f"{station.lower()}/{data_type}/{cadence}/{components}"


def expected_output_path(args: argparse.Namespace, station: str, day_text: str) -> Path:
    day, _, _ = utc_day_bounds(day_text)
    dataset = dataset_id(station.upper(), args.data_type, args.cadence, args.components)
    safe_dataset = dataset.replace("/", "_")
    return Path(args.output_dir) / f"{safe_dataset}_{day.isoformat()}.csv"


def selected_parameters(info: dict[str, Any], parameter_text: str) -> list[dict[str, Any]]:
    all_parameters = [p for p in info["parameters"] if p["name"] != "Time"]
    if not parameter_text:
        return all_parameters

    requested = [name.strip() for name in parameter_text.split(",") if name.strip()]
    by_name = {p["name"]: p for p in all_parameters}
    missing = [name for name in requested if name not in by_name]
    if missing:
        available = ", ".join(sorted(by_name))
        raise RuntimeError(
            f"Unknown parameter(s): {', '.join(missing)}. Available: {available}"
        )
    return [by_name[name] for name in requested]


def flattened_header(parameters: list[dict[str, Any]]) -> list[str]:
    header = ["Time"]
    for parameter in parameters:
        name = parameter["name"]
        label = parameter.get("label")
        size = parameter.get("size")

        if isinstance(label, list):
            header.extend(str(item) for item in label)
        elif size:
            count = 1
            for dimension in size:
                count *= int(dimension)
            header.extend(f"{name}_{index + 1}" for index in range(count))
        elif isinstance(label, str):
            header.append(label)
        else:
            header.append(name)
    return header


def write_csv_with_header(output_path: Path, header: list[str], payload: bytes) -> int:
    text = payload.decode("utf-8")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise RuntimeError("HAPI returned no data rows.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def download_one(
    args: argparse.Namespace,
    station: str,
    day_text: str | None = None,
    dataset_info: dict[str, Any] | None = None,
) -> tuple[Path, int]:
    station = station.upper()
    day_text = day_text or args.date
    day, start, stop = utc_day_bounds(day_text)
    dataset = dataset_id(station, args.data_type, args.cadence, args.components)
    info_url = build_url(args.base_url, "info", {"dataset": dataset})
    info = dataset_info or request_json(info_url)
    parameters = selected_parameters(info, args.parameters)
    header = flattened_header(parameters)
    parameter_names = ",".join(parameter["name"] for parameter in parameters)

    query = {
        "dataset": dataset,
        "parameters": parameter_names,
        "start": start,
        "stop": stop,
        "format": "csv",
    }
    data_url = build_url(args.base_url, "data", query)
    payload = request_bytes(data_url)
    raise_if_hapi_error_payload(payload, data_url)

    output_path = expected_output_path(args, station, day.isoformat())
    if output_path.exists() and not args.overwrite:
        raise RuntimeError(f"{output_path} already exists. Use --overwrite to replace it.")

    row_count = write_csv_with_header(output_path, header, payload)
    return output_path, row_count


def main() -> int:
    args = parse_args()
    stations = EUROPE_STATIONS if args.all_europe else tuple(
        code.strip().upper() for code in args.stations.split(",") if code.strip()
    )
    if not stations:
        print("No station codes were provided.", file=sys.stderr)
        return 2

    failures = 0
    for station in stations:
        try:
            output_path, row_count = download_one(args, station)
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {station}: {exc}", file=sys.stderr)
            continue
        print(f"[OK] {station}: wrote {row_count} rows -> {output_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())