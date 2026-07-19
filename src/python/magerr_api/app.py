from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

try:
    import magerr_native
except ImportError:  # pragma: no cover - deployment/configuration error path
    magerr_native = None


class VariationSeriesRequest(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=360.0)
    altitude_km: float = 0.0
    start_time: str
    end_time: str
    step_seconds: int = Field(60, gt=0)
    coefficient_dir: str = ""


app = FastAPI(title="MagErr Magnetic Field API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "native_module": magerr_native is not None}


@app.post("/v1/field/main")
def main_field(request: VariationSeriesRequest) -> dict[str, Any]:
    if magerr_native is None:
        return {
            "ok": False,
            "error": "magerr_native is not importable; build/install the pybind11 module first",
        }

    field = magerr_native.wmm_main_field(
        request.latitude,
        request.longitude,
        request.altitude_km,
        request.start_time,
        request.coefficient_dir,
    )
    return {
        "ok": True,
        "time": request.start_time,
        "main": dict(field),
    }


@app.post("/v1/field/variation-series")
def variation_series(request: VariationSeriesRequest) -> dict[str, Any]:
    # Placeholder endpoint shape. Once FieldWorkflow is fully exposed through
    # pybind11, this should call native get_variation_series instead of returning
    # a single WMM sample.
    result = main_field(request)
    if result.get("ok"):
        result["samples"] = [
            {
                "time": request.start_time,
                "main": result.pop("main"),
                "external": None,
                "source": "wmm-only-placeholder",
            }
        ]
    return result

