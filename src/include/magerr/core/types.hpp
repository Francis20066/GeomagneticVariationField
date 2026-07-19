#pragma once

#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace magerr {

using TimePoint = std::chrono::system_clock::time_point;

struct GeoPoint {
  double latitude_deg = 0.0;
  double longitude_deg = 0.0;
  double altitude_km = 0.0;
};

struct TimeRange {
  TimePoint start;
  TimePoint end;
  std::int64_t step_seconds = 60;
};

struct FieldVector {
  double north_nt = 0.0;
  double east_nt = 0.0;
  double down_nt = 0.0;
  double total_nt = 0.0;
  double declination_deg = 0.0;
  double inclination_deg = 0.0;
};

enum class FieldSource {
  Wmm2025,
  Swarm,
  Predictor,
  Missing,
};

struct FieldSample {
  TimePoint time;
  double decimal_year = 0.0;
  FieldVector main;
  std::optional<FieldVector> external;
  FieldSource external_source = FieldSource::Missing;
};

struct SeriesRequest {
  GeoPoint point;
  TimeRange range;
};

struct SeriesResponse {
  std::vector<FieldSample> samples;
};

}  // namespace magerr

