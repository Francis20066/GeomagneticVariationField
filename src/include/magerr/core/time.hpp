#pragma once

#include "magerr/core/types.hpp"

#include <string>
#include <vector>

namespace magerr {

double decimal_year(TimePoint time);
std::string to_iso8601(TimePoint time);
TimePoint parse_iso8601_utc(const std::string& value);
std::vector<TimePoint> expand_time_range(const TimeRange& range);

}  // namespace magerr

