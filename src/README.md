# MagErr Magnetic Field Core

This directory is the extraction target for the magnetic-field workflow.

The goal is to move the stable physics/model-evaluation code out of ad-hoc
Python environments and into a C++ core, expose that core as a Python module
through pybind11, and provide an HTTP API on top.

> Note: the binding library is pybind11. There is no mainstream `pybind3`
> project; this architecture assumes the request meant a Python 3 compatible
> pybind module.

## Target Workflow

Input:

- latitude, longitude, altitude
- time range and step
- model source selection

Output:

- main field from WMM2025
- external variation field from Swarm MIO/MMA while timestamps are within the
  available model/product validity range
- predicted external variation field for timestamps beyond the available
  physical/product range
- serialized records for Python and HTTP clients

The important behavior is this split:

```text
time <= forecast_boundary:
    WMM2025 main field + Swarm MIO/MMA external field

time > forecast_boundary:
    WMM2025 main field + PyTorch predictor external field
```

The `forecast_boundary` should normally be the minimum of:

- current UTC time
- latest valid time in the loaded Swarm model/product files
- any user-specified cutover time

## Layers

```text
src/
  include/magerr/core/       C++ value types and time helpers
  include/magerr/models/     stable model provider interfaces
  include/magerr/workflow/   orchestration and forecast cutover policy
  cpp/                       C++ implementations
  bindings/                  pybind11 module
  python/magerr_api/         FastAPI service that imports the Python module
  examples/                  usage examples
```

## Extraction Plan

### 1. WMM2025 Main Field

Short-term implementation:

- compile the existing WMM C sources from `wmm2025/src/wmm2025/src`
- call the exported `wmmsub(...)` function from `Wmm2025Provider`
- copy `WMM.COF` beside the runtime library or pass the coefficient path before
  calling into the C routine

Long-term cleanup:

- remove the hidden process-wide `chdir` dependency in `wmmsub`
- load coefficients once per provider instance
- make WMM evaluation thread-safe

### 2. Swarm External Field

The current working implementation is in `geoist.model.magmod`:

- `loader_mio.py`
- `loader_mma.py`
- `parser_mio.py`
- `parser_mma.py`
- `_pymm` spherical harmonic C extension
- dipole coordinate transforms and vector rotations

Extraction should be staged:

1. Port the spherical-harmonic evaluator and coordinate transforms first.
2. Port MIO ASCII parsing and coefficient interpolation.
3. Port MMA CDF parsing. Prefer a small CDF reader boundary so `spacepy.pycdf`
   can be temporarily used from Python during migration if needed.
4. Implement `SwarmExternalProvider` behind the same C++ interface.

### 3. PyTorch Forecast Interface

Do not couple the core to libtorch yet. Keep a small C++ interface:

```cpp
class FieldPredictor {
public:
  virtual std::vector<FieldVector> forecast(...)=0;
};
```

Later options:

- C++ TorchScript predictor using libtorch
- Python-side predictor passed into pybind11 as a callback
- service-side predictor called after C++ history generation

For this project, the first practical path is Python callback first, then
TorchScript when the model architecture stabilizes.

## Public Surfaces

### Python Module

Expected shape:

```python
import magerr_native as magerr

series = magerr.get_variation_series(
    latitude=19.03,
    longitude=109.83,
    altitude_km=0.5,
    start_time="2025-02-04T00:00:00Z",
    end_time="2025-02-05T00:00:00Z",
    step_seconds=60,
)
```

### HTTP API

Expected shape:

```http
POST /v1/field/variation-series
```

Body:

```json
{
  "latitude": 19.03,
  "longitude": 109.83,
  "altitude_km": 0.5,
  "start_time": "2025-02-04T00:00:00Z",
  "end_time": "2025-02-05T00:00:00Z",
  "step_seconds": 60
}
```

Response:

```json
{
  "samples": [
    {
      "time": "2025-02-04T00:00:00Z",
      "main": {"north": 0, "east": 0, "down": 0, "total": 0},
      "external": {"north": 0, "east": 0, "down": 0, "total": 0},
      "source": "swarm"
    }
  ]
}
```

