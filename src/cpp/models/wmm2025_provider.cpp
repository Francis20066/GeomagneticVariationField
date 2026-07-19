#include "magerr/models/wmm2025_provider.hpp"

#include "magerr/core/time.hpp"

#include <filesystem>
#include <stdexcept>
#include <utility>

extern "C" int wmmsub(double geolatitude,
                      double geolongitude,
                      double height_above_ellipsoid,
                      double year_decimal,
                      double* x,
                      double* y,
                      double* z,
                      double* f,
                      double* decl,
                      double* incl);

namespace magerr {

Wmm2025Provider::Wmm2025Provider(std::filesystem::path coefficient_dir)
    : coefficient_dir_(std::move(coefficient_dir)) {}

FieldVector Wmm2025Provider::evaluate(const GeoPoint& point, TimePoint time) const {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  double f = 0.0;
  double decl = 0.0;
  double incl = 0.0;

  const auto old_cwd = std::filesystem::current_path();
  if (!coefficient_dir_.empty()) {
    std::filesystem::current_path(coefficient_dir_);
  }

  const int rc = wmmsub(
      point.latitude_deg,
      point.longitude_deg,
      point.altitude_km,
      decimal_year(time),
      &x,
      &y,
      &z,
      &f,
      &decl,
      &incl);

  if (!coefficient_dir_.empty()) {
    std::filesystem::current_path(old_cwd);
  }

  if (rc != 0) {
    throw std::runtime_error("WMM2025 evaluation failed; check WMM.COF location");
  }

  return FieldVector{
      x,
      y,
      z,
      f,
      decl,
      incl,
  };
}

}  // namespace magerr


