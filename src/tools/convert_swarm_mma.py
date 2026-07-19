#!/usr/bin/env python3
"""Convert Swarm MMA CDF products into MagErr runtime resources."""

from __future__ import annotations

import argparse
from pathlib import Path

from spacepy import pycdf


CDF_EPOCH = pycdf.const.CDF_EPOCH.value
CDF_EPOCH_2000 = 63113904000000.0
CDF_EPOCH_TO_DAYS = 1.0 / 86400000.0


def raw_time_to_mjd2000(raw_time, cdf_type: int) -> list[float]:
    if cdf_type != CDF_EPOCH:
        raise ValueError(f"unsupported CDF time type: {cdf_type!r}")
    return [float((value - CDF_EPOCH_2000) * CDF_EPOCH_TO_DAYS) for value in raw_time]


def read_set(cdf, *, set_id: str, variable: str, suffix: str, frame: str, internal: bool, dipole: bool):
    if suffix:
        time_name = f"t_{variable}_{suffix}"
        nm_name = f"nm_{variable}_{suffix}"
        coeff_name = f"{variable}_{suffix}"
    else:
        time_name = f"t_{variable}"
        nm_name = f"nm_{variable}"
        coeff_name = f"{variable}_{frame}"

    raw_time = cdf.raw_var(time_name)
    times = raw_time_to_mjd2000(raw_time[0], raw_time.type())
    nm = cdf[nm_name][...]
    if nm.ndim == 3 and nm.shape[0] == 1:
        nm = nm[0]
    coeff = cdf[coeff_name][0].transpose()
    return {
        "id": set_id,
        "internal": internal,
        "dipole": dipole,
        "times": times,
        "nm": [[int(n), int(m)] for n, m in nm],
        "coeff": coeff,
    }


def write_resource(path: Path, sets: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as out:
        out.write("MAGERR_MMA_RESOURCE 1\n")
        out.write(f"sets {len(sets)}\n")
        for item in sets:
            times = item["times"]
            nm = item["nm"]
            coeff = item["coeff"]
            degree = max(abs(n) for n, _ in nm)
            out.write(
                "set {id} internal {internal} dipole {dipole} "
                "lat_ngp {lat:.12g} lon_ngp {lon:.12g} degree {degree}\n".format(
                    id=item["id"],
                    internal=1 if item["internal"] else 0,
                    dipole=1 if item["dipole"] else 0,
                    lat=80.08 if item["dipole"] else 0.0,
                    lon=-72.22 if item["dipole"] else 0.0,
                    degree=degree,
                )
            )
            out.write(f"times {len(times)}\n")
            out.write(" ".join(f"{value:.17g}" for value in times) + "\n")
            out.write(f"coefficients {len(nm)}\n")
            for index, (n, m) in enumerate(nm):
                values = " ".join(f"{float(value):.17g}" for value in coeff[index])
                out.write(f"{n} {m} {values}\n")
            out.write("endset\n")


def convert_mma_2c(input_path: Path, output_path: Path) -> None:
    with pycdf.CDF(str(input_path)) as cdf:
        sets = [
            read_set(cdf, set_id="mma_2c_primary_1", variable="qs", suffix="1", frame="", internal=False, dipole=True),
            read_set(cdf, set_id="mma_2c_primary_2", variable="qs", suffix="2", frame="", internal=False, dipole=True),
            read_set(cdf, set_id="mma_2c_secondary_1", variable="gh", suffix="1", frame="", internal=True, dipole=True),
            read_set(cdf, set_id="mma_2c_secondary_2", variable="gh", suffix="2", frame="", internal=True, dipole=True),
        ]
    write_resource(output_path, sets)


def convert_mma_2f(input_path: Path, output_path: Path) -> None:
    with pycdf.CDF(str(input_path)) as cdf:
        sets = [
            read_set(cdf, set_id="mma_2f_geo_primary", variable="qs", suffix="", frame="geo", internal=False, dipole=False),
            read_set(cdf, set_id="mma_2f_geo_secondary", variable="gh", suffix="", frame="geo", internal=True, dipole=False),
        ]
    write_resource(output_path, sets)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mma-2c", type=Path, required=True)
    parser.add_argument("--mma-2f", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("src/resources/swarm_mma"))
    args = parser.parse_args()

    convert_mma_2c(args.mma_2c, args.out_dir / "mma_2c.magerr")
    convert_mma_2f(args.mma_2f, args.out_dir / "mma_2f.magerr")


if __name__ == "__main__":
    main()
