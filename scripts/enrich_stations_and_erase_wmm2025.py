#!/usr/bin/env python3
"""Enrich European station metadata and remove WMM2025 main-field estimates."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
import wmm2025


HAPI_BASE_URL = "https://imag-data.bgs.ac.uk/GIN_V1/hapi"
HAPI_FILL = 99999.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add station metadata and compute X/Y/Z with WMM2025 main field removed."
    )
    parser.add_argument("--station-doc", default="docs/欧洲开源台站信息.txt")
    parser.add_argument("--summary-csv", default="outputs/european_2022_station_summary.csv")
    parser.add_argument("--all-current-csv", default="outputs/european_2022_all_current.csv")
    parser.add_argument(
        "--summary-out",
        default="outputs/european_2022_station_summary_enriched.csv",
    )
    parser.add_argument(
        "--daily-main-field-out",
        default="outputs/european_2022_station_daily_wmm2025.csv",
    )
    parser.add_argument(
        "--all-current-out",
        default="outputs/european_2022_all_current_wmm2025_erased.csv",
    )
    parser.add_argument("--chunksize", type=int, default=500_000)
    return parser.parse_args()


def read_station_doc(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    try:
        header_idx = next(i for i, line in enumerate(lines) if line.startswith("Code,Station,Country,"))
    except StopIteration as exc:
        raise RuntimeError(f"Could not find station CSV header in {path}") from exc

    rows = list(csv.DictReader(lines[header_idx:]))
    stations = pd.DataFrame(rows)
    stations["Code"] = stations["Code"].str.strip().str.upper()
    stations["station"] = stations["Code"].str.lower()
    stations["Latitude"] = pd.to_numeric(stations["Latitude"], errors="raise")
    stations["Longitude"] = pd.to_numeric(stations["Longitude"], errors="raise")
    return stations


def hapi_info_url(code: str) -> str:
    dataset = f"{code.lower()}/definitive/PT1M/xyzf"
    return f"{HAPI_BASE_URL}/info?id={quote(dataset, safe='/')}"


def fetch_hapi_elevation(code: str) -> dict[str, object]:
    url = hapi_info_url(code)
    request = Request(url, headers={"User-Agent": "geomagnetic-wmm2025-erasure/1.0"})
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))

    status = payload.get("status", {})
    if status.get("code") != 1200:
        raise RuntimeError(f"HAPI info failed for {code}: {status}")

    return {
        "Code": code,
        "HAPI_Latitude": payload.get("x_latitude"),
        "HAPI_Longitude": payload.get("x_longitude"),
        "Elevation_m": payload.get("x_elevation"),
        "Elevation_Source": url,
    }


def decimal_year_at_day_midpoint(day_text: str) -> float:
    day_start = datetime.strptime(day_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    midpoint = day_start.timestamp() + 12 * 60 * 60
    dt = datetime.fromtimestamp(midpoint, tz=timezone.utc)
    year_start = datetime(dt.year, 1, 1, tzinfo=timezone.utc)
    next_year = datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return dt.year + (dt - year_start).total_seconds() / (next_year - year_start).total_seconds()


def build_enriched_summary(stations: pd.DataFrame, summary_path: Path, out_path: Path) -> pd.DataFrame:
    summary = pd.read_csv(summary_path, dtype={"station": "string"})
    elevations = pd.DataFrame(fetch_hapi_elevation(code) for code in summary["station"].str.upper())
    enriched = (
        summary.merge(stations, on="station", how="left", validate="one_to_one")
        .merge(elevations, on="Code", how="left", validate="one_to_one")
    )

    missing = enriched[enriched[["Code", "Latitude", "Longitude", "Elevation_m"]].isna().any(axis=1)]
    if not missing.empty:
        raise RuntimeError(f"Missing station metadata for: {', '.join(missing['station'])}")

    ordered = [
        "station",
        "Code",
        "Station",
        "Country",
        "Latitude",
        "Longitude",
        "Elevation_m",
        "Elevation_Source",
        "HAPI_Latitude",
        "HAPI_Longitude",
        "files",
        "rows",
        "min_file_date",
        "max_file_date",
        "min_time",
        "max_time",
    ]
    enriched = enriched[ordered]
    enriched.to_csv(out_path, index=False, float_format="%.8f")
    return enriched


def build_daily_main_field(enriched: pd.DataFrame, all_current_path: Path, out_path: Path) -> pd.DataFrame:
    station_dates = pd.read_csv(
        all_current_path,
        usecols=["station", "file_date"],
        dtype={"station": "string", "file_date": "string"},
    ).drop_duplicates()

    meta = enriched.set_index("station")
    rows: list[dict[str, object]] = []
    for row in station_dates.itertuples(index=False):
        station = str(row.station)
        file_date = str(row.file_date)
        station_meta = meta.loc[station]
        decimal_year = decimal_year_at_day_midpoint(file_date)
        altitude_km = float(station_meta["Elevation_m"]) / 1000.0
        mag = wmm2025.wmm_point(
            float(station_meta["Latitude"]),
            float(station_meta["Longitude"]),
            altitude_km,
            decimal_year,
        )
        rows.append(
            {
                "station": station,
                "file_date": file_date,
                "Latitude": float(station_meta["Latitude"]),
                "Longitude": float(station_meta["Longitude"]),
                "Elevation_m": float(station_meta["Elevation_m"]),
                "decimal_year_wmm2025": decimal_year,
                "X_main_wmm2025": mag["north"],
                "Y_main_wmm2025": mag["east"],
                "Z_main_wmm2025": mag["down"],
                "F_main_wmm2025": mag["total"],
                "Declination_deg_wmm2025": mag["decl"],
                "Inclination_deg_wmm2025": mag["incl"],
            }
        )

    daily = pd.DataFrame(rows).sort_values(["station", "file_date"])
    daily.to_csv(out_path, index=False, float_format="%.8f")
    return daily


def write_erased_current(all_current_path: Path, daily: pd.DataFrame, out_path: Path, chunksize: int) -> int:
    key_columns = [
        "station",
        "file_date",
        "Latitude",
        "Longitude",
        "Elevation_m",
        "decimal_year_wmm2025",
        "X_main_wmm2025",
        "Y_main_wmm2025",
        "Z_main_wmm2025",
        "F_main_wmm2025",
    ]
    daily = daily[key_columns]
    rows_written = 0
    first = True
    for chunk in pd.read_csv(
        all_current_path,
        chunksize=chunksize,
        dtype={"station": "string", "file_date": "string"},
    ):
        chunk = chunk.merge(daily, on=["station", "file_date"], how="left", validate="many_to_one")
        for column in ("X", "Y", "Z"):
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")
            chunk.loc[chunk[column] == HAPI_FILL, column] = pd.NA

        chunk["X_erase"] = chunk["X"] - chunk["X_main_wmm2025"]
        chunk["Y_erase"] = chunk["Y"] - chunk["Y_main_wmm2025"]
        chunk["Z_erase"] = chunk["Z"] - chunk["Z_main_wmm2025"]

        chunk.to_csv(
            out_path,
            index=False,
            mode="w" if first else "a",
            header=first,
            float_format="%.4f",
        )
        rows_written += len(chunk)
        first = False
        print(f"wrote {rows_written} rows", flush=True)
    return rows_written


def main() -> None:
    args = parse_args()
    station_doc = Path(args.station_doc)
    summary_csv = Path(args.summary_csv)
    all_current_csv = Path(args.all_current_csv)
    summary_out = Path(args.summary_out)
    daily_main_field_out = Path(args.daily_main_field_out)
    all_current_out = Path(args.all_current_out)

    stations = read_station_doc(station_doc)
    enriched = build_enriched_summary(stations, summary_csv, summary_out)
    daily = build_daily_main_field(enriched, all_current_csv, daily_main_field_out)
    rows_written = write_erased_current(all_current_csv, daily, all_current_out, args.chunksize)

    print(f"summary: {summary_out}")
    print(f"daily main field: {daily_main_field_out}")
    print(f"erased current: {all_current_out}")
    print(f"rows written: {rows_written}")


if __name__ == "__main__":
    main()
