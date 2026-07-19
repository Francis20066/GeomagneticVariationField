import math
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


native_path = os.environ.get("MAGERR_NATIVE_PATH")
if native_path:
    sys.path.insert(0, native_path)

if hasattr(os, "add_dll_directory"):
    for dll_dir in os.environ.get("MAGERR_DLL_DIRS", "").split(os.pathsep):
        if dll_dir:
            os.add_dll_directory(dll_dir)


try:
    import magerr_native
except ImportError as exc:  # pragma: no cover - reported as a skipped suite
    magerr_native = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


def decimal_year(value: str) -> float:
    dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    start = datetime(dt.year, 1, 1, tzinfo=timezone.utc)
    end = datetime(dt.year + 1, 1, 1, tzinfo=timezone.utc)
    return dt.year + (dt - start).total_seconds() / (end - start).total_seconds()


@unittest.skipIf(magerr_native is None, f"magerr_native import failed: {IMPORT_ERROR}")
class NativeModuleSmokeTest(unittest.TestCase):
    def test_wmm_main_field_smoke(self):
        field = magerr_native.wmm_main_field(19.03, 109.83, 0.5, "2025-02-04T00:00:00Z")

        self.assertGreater(field["total"], 40_000.0)
        self.assertLess(field["total"], 50_000.0)
        self.assertTrue(math.isfinite(field["declination"]))
        self.assertTrue(math.isfinite(field["inclination"]))

    def test_swarm_mma_field_smoke(self):
        field = magerr_native.swarm_mma_field(
            19.03, 109.83, 0.5, "2021-02-04T00:00:00Z"
        )

        self.assertGreater(field["total"], 0.0)
        self.assertLess(field["total"], 1_000.0)

    def test_unified_series_and_batch(self):
        series = magerr_native.get_variation_series(
            19.03,
            109.83,
            0.5,
            "2021-02-04T00:00:00Z",
            "2021-02-04T00:02:00Z",
            60,
        )
        self.assertEqual(len(series), 3)
        self.assertEqual(series[0]["external_source"], "swarm_mma")

        batch = magerr_native.field_at_batch(
            [19.03, 20.0],
            [109.83, 110.0],
            [0.5, 0.5],
            ["2021-02-04T00:00:00Z", "2021-02-04T00:01:00Z"],
        )
        self.assertEqual(len(batch), 2)


@unittest.skipIf(magerr_native is None, f"magerr_native import failed: {IMPORT_ERROR}")
class OptionalReferenceTest(unittest.TestCase):
    def test_wmm_matches_python_reference_when_available(self):
        try:
            import wmm2025
        except ImportError:
            self.skipTest("wmm2025 reference package is not installed in this Python")

        time_utc = "2025-02-04T00:00:00Z"
        native = magerr_native.wmm_main_field(19.03, 109.83, 0.5, time_utc)
        reference = wmm2025.wmm_point(19.03, 109.83, 0.5, decimal_year(time_utc))

        self.assertAlmostEqual(native["north"], reference["north"], places=6)
        self.assertAlmostEqual(native["east"], reference["east"], places=6)
        self.assertAlmostEqual(native["down"], reference["down"], places=6)
        self.assertAlmostEqual(native["total"], reference["total"], places=6)


if __name__ == "__main__":
    unittest.main()
