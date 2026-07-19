#include "magerr/core/time.hpp"

#include <ctime>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace magerr {
namespace {

std::tm to_utc_tm(TimePoint time) {
  const auto seconds = std::chrono::system_clock::to_time_t(time);
  std::tm out{};
#if defined(_WIN32)
  gmtime_s(&out, &seconds);
#else
  gmtime_r(&seconds, &out);
#endif
  return out;
}

TimePoint from_utc_tm(std::tm tm) {
#if defined(_WIN32)
  const auto seconds = _mkgmtime(&tm);
#else
  const auto seconds = timegm(&tm);
#endif
  if (seconds == static_cast<std::time_t>(-1)) {
    throw std::invalid_argument("invalid UTC time");
  }
  return std::chrono::system_clock::from_time_t(seconds);
}

}  // namespace

double decimal_year(TimePoint time) {
  const auto tm = to_utc_tm(time);
  std::tm start_tm{};
  start_tm.tm_year = tm.tm_year;
  start_tm.tm_mon = 0;
  start_tm.tm_mday = 1;

  std::tm next_tm = start_tm;
  next_tm.tm_year += 1;

  const auto start = from_utc_tm(start_tm);
  const auto next = from_utc_tm(next_tm);
  const auto elapsed = std::chrono::duration<double>(time - start).count();
  const auto year_len = std::chrono::duration<double>(next - start).count();

  return static_cast<double>(tm.tm_year + 1900) + elapsed / year_len;
}

std::string to_iso8601(TimePoint time) {
  const auto tm = to_utc_tm(time);
  std::ostringstream out;
  out << std::put_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
  return out.str();
}

TimePoint parse_iso8601_utc(const std::string& value) {
  std::tm tm{};
  std::istringstream in(value);
  in >> std::get_time(&tm, "%Y-%m-%dT%H:%M:%SZ");
  if (in.fail()) {
    throw std::invalid_argument("time must be UTC ISO-8601: YYYY-MM-DDTHH:MM:SSZ");
  }
  return from_utc_tm(tm);
}

std::vector<TimePoint> expand_time_range(const TimeRange& range) {
  if (range.step_seconds <= 0) {
    throw std::invalid_argument("step_seconds must be positive");
  }
  if (range.end < range.start) {
    throw std::invalid_argument("end time must be >= start time");
  }

  std::vector<TimePoint> times;
  for (auto t = range.start; t <= range.end;
       t += std::chrono::seconds(range.step_seconds)) {
    times.push_back(t);
  }
  return times;
}

}  // namespace magerr


