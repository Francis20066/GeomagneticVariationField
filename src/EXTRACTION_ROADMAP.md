# Extraction Roadmap

## Current Known Working Environments

- `worldmag`: WMM2025 main field
- `swarmfield`: Swarm MIO/MMA external field via `geoist.model.magmod`

The new C++ core should make these environment names implementation details,
not user-facing requirements.

## Milestone 1: WMM Native Module

Deliverables:

- build `magerr_native`
- expose `wmm_main_field(...)`
- verify against the existing Python `wmm2025.wmm_point(...)`

Implementation notes:

- existing C entry point: `wmmsub(...)`
- existing coefficient file: `wmm2025/src/wmm2025/WMM.COF`
- current C code reads `WMM.COF` from current working directory, so the provider
  temporarily switches directories. Replace this later.

## Milestone 2: Swarm Compatibility Wrapper

Before full C++ port, expose a Python compatibility layer that calls
`geoist.model.magmod` from `swarmfield`.

This gives the API its final contract early while the C++ port progresses.

## Milestone 3: C++ Swarm MIO

Port these pieces:

- `parser_mio.py`
- `coefficients_mio.py`
- `model_mio.py`
- dipole coordinate conversion and vector rotation
- `sheval` spherical harmonic evaluator

## Milestone 4: C++ Swarm MMA

Port these pieces:

- CDF variable reader boundary
- `parser_mma.py`
- time-dependent sparse coefficient interpolation
- geographic and dipole spherical harmonic models

## Milestone 5: Forecast Model

Start with Python callback predictor:

- Python model receives history samples and future timestamps
- returns external-field vectors

Then move to TorchScript/libtorch if deployment needs a pure C++ runtime.

## Milestone 6: Production API

- FastAPI for initial deployment
- option to move to C++ HTTP server only if Python process overhead becomes a
  bottleneck
- JSON response by default
- optional binary formats later: MessagePack, Arrow IPC, or NumPy `.npz`

