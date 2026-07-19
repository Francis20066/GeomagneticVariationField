#include "magerr/models/swarm_external_provider.hpp"

#include <geo_conv.h>
#include <math_aux.h>
#include <shc.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace magerr {
namespace {

constexpr double kDegToRad = 3.14159265358979323846 / 180.0;
constexpr double kSecondsPerDay = 86400.0;

struct CoeffSeries {
  int n = 0;
  int m = 0;
  std::vector<double> values;
};

struct MmaCoeffSet {
  std::string id;
  bool internal = true;
  bool dipole = false;
  double lat_ngp_deg = 0.0;
  double lon_ngp_deg = 0.0;
  int degree = 0;
  std::vector<double> times_mjd2000;
  std::vector<CoeffSeries> coefficients;
};

struct SphericalVector {
  double north = 0.0;
  double east = 0.0;
  double radial_up = 0.0;
};

struct CartesianVector {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
};

TimePoint mjd2000_epoch() {
  std::tm tm{};
  tm.tm_year = 100;
  tm.tm_mon = 0;
  tm.tm_mday = 1;
#if defined(_WIN32)
  const auto seconds = _mkgmtime(&tm);
#else
  const auto seconds = timegm(&tm);
#endif
  return std::chrono::system_clock::from_time_t(seconds);
}

double time_to_mjd2000(TimePoint time) {
  static const auto epoch = mjd2000_epoch();
  return std::chrono::duration<double>(time - epoch).count() / kSecondsPerDay;
}

TimePoint mjd2000_to_time(double mjd2000) {
  static const auto epoch = mjd2000_epoch();
  return epoch + std::chrono::duration_cast<std::chrono::system_clock::duration>(
                     std::chrono::duration<double>(mjd2000 * kSecondsPerDay));
}

std::filesystem::path resource_candidate(const std::filesystem::path& resource_dir,
                                         const char* file_name) {
  if (!resource_dir.empty()) {
    return resource_dir / file_name;
  }
#ifdef MAGERR_DEFAULT_RESOURCE_DIR
  return std::filesystem::path(MAGERR_DEFAULT_RESOURCE_DIR) / "swarm_mma" / file_name;
#else
  return std::filesystem::current_path() / "src" / "resources" / "swarm_mma" / file_name;
#endif
}

std::vector<MmaCoeffSet> load_resource_file(const std::filesystem::path& path) {
  std::ifstream in(path);
  if (!in) {
    throw std::runtime_error("failed to open MMA resource: " + path.string());
  }

  std::string magic;
  int version = 0;
  in >> magic >> version;
  if (magic != "MAGERR_MMA_RESOURCE" || version != 1) {
    throw std::runtime_error("invalid MMA resource header: " + path.string());
  }

  std::string token;
  std::size_t set_count = 0;
  in >> token >> set_count;
  if (token != "sets") {
    throw std::runtime_error("invalid MMA resource set count: " + path.string());
  }

  std::vector<MmaCoeffSet> sets;
  sets.reserve(set_count);
  for (std::size_t set_index = 0; set_index < set_count; ++set_index) {
    MmaCoeffSet set;
    std::string internal_label;
    int internal = 0;
    std::string dipole_label;
    int dipole = 0;
    std::string lat_label;
    std::string lon_label;
    std::string degree_label;

    in >> token >> set.id >> internal_label >> internal >> dipole_label >> dipole >>
        lat_label >> set.lat_ngp_deg >> lon_label >> set.lon_ngp_deg >>
        degree_label >> set.degree;
    if (token != "set" || internal_label != "internal" || dipole_label != "dipole" ||
        lat_label != "lat_ngp" || lon_label != "lon_ngp" || degree_label != "degree") {
      throw std::runtime_error("invalid MMA set header in: " + path.string());
    }
    set.internal = internal != 0;
    set.dipole = dipole != 0;

    std::size_t time_count = 0;
    in >> token >> time_count;
    if (token != "times" || time_count < 1) {
      throw std::runtime_error("invalid MMA time vector in: " + path.string());
    }
    set.times_mjd2000.resize(time_count);
    for (auto& value : set.times_mjd2000) {
      in >> value;
    }

    std::size_t coeff_count = 0;
    in >> token >> coeff_count;
    if (token != "coefficients") {
      throw std::runtime_error("invalid MMA coefficient block in: " + path.string());
    }
    set.coefficients.reserve(coeff_count);
    for (std::size_t coeff_index = 0; coeff_index < coeff_count; ++coeff_index) {
      CoeffSeries series;
      in >> series.n >> series.m;
      series.values.resize(time_count);
      for (auto& value : series.values) {
        in >> value;
      }
      set.coefficients.push_back(std::move(series));
    }

    in >> token;
    if (token != "endset") {
      throw std::runtime_error("missing endset in MMA resource: " + path.string());
    }
    sets.push_back(std::move(set));
  }

  return sets;
}

int coeff_size(int degree) {
  return ((degree + 1) * (degree + 2)) / 2;
}

double interpolate(const std::vector<double>& times,
                   const std::vector<double>& values,
                   double time) {
  if (time < times.front() || time > times.back()) {
    throw std::out_of_range("time outside MMA coefficient validity");
  }
  if (times.size() == 1) {
    return values.front();
  }

  auto upper = std::lower_bound(times.begin(), times.end(), time);
  if (upper == times.begin()) {
    return values.front();
  }
  if (upper == times.end()) {
    return values.back();
  }
  const std::size_t i1 = static_cast<std::size_t>(upper - times.begin());
  const std::size_t i0 = i1 - 1;
  const double alpha = (time - times[i0]) / (times[i1] - times[i0]);
  return values[i0] * (1.0 - alpha) + values[i1] * alpha;
}

void fill_coefficients(const MmaCoeffSet& set,
                       double time,
                       std::vector<double>& g,
                       std::vector<double>& h) {
  g.assign(coeff_size(set.degree), 0.0);
  h.assign(coeff_size(set.degree), 0.0);

  for (const auto& series : set.coefficients) {
    const int index = std::abs(series.m) + (series.n * (series.n + 1)) / 2;
    if (index < 0 || static_cast<std::size_t>(index) >= g.size()) {
      throw std::runtime_error("invalid MMA coefficient index");
    }
    if (series.m < 0) {
      h[static_cast<std::size_t>(index)] = interpolate(set.times_mjd2000, series.values, time);
    } else {
      g[static_cast<std::size_t>(index)] = interpolate(set.times_mjd2000, series.values, time);
    }
  }
}

FieldVector make_field(double north, double east, double down) {
  const double horizontal = std::hypot(north, east);
  const double total = std::hypot(horizontal, down);
  const double decl = std::atan2(east, north) / kDegToRad;
  const double incl = std::atan2(down, horizontal) / kDegToRad;
  return FieldVector{north, east, down, total, decl, incl};
}

SphericalVector evaluate_spherical_raw(const MmaCoeffSet& set,
                                       double latitude_rad,
                                       double longitude_rad,
                                       double radius_km,
                                       double time_mjd2000) {
  std::vector<double> g;
  std::vector<double> h;
  fill_coefficients(set, time_mjd2000, g, h);

  std::vector<double> legendre(static_cast<std::size_t>(coeff_size(set.degree)));
  std::vector<double> legendre_derivative(static_cast<std::size_t>(coeff_size(set.degree)));
  std::vector<double> lon_sin(static_cast<std::size_t>(set.degree + 1));
  std::vector<double> lon_cos(static_cast<std::size_t>(set.degree + 1));
  std::vector<double> relrad(static_cast<std::size_t>(set.degree + 1));

  shc_legendre(legendre.data(), legendre_derivative.data(), set.degree, latitude_rad, nullptr);
  shc_azmsincos(lon_sin.data(), lon_cos.data(), set.degree, longitude_rad);
  if (set.internal) {
    shc_relradpow_internal(relrad.data(), set.degree, radius_km / 6371.2);
  } else {
    shc_relradpow_external(relrad.data(), set.degree, radius_km / 6371.2);
  }

  double potential = 0.0;
  double d_lat = 0.0;
  double d_lon = 0.0;
  double d_rad = 0.0;
  shc_eval(&potential,
           &d_lat,
           &d_lon,
           &d_rad,
           set.degree,
           2,
           latitude_rad,
           radius_km,
           g.data(),
           h.data(),
           legendre.data(),
           legendre_derivative.data(),
           relrad.data(),
           lon_sin.data(),
           lon_cos.data(),
           set.internal ? 1 : 0);

  return SphericalVector{-d_lat, -d_lon, -d_rad};
}

FieldVector evaluate_geodetic(const MmaCoeffSet& set,
                              const GeoPoint& point,
                              double time_mjd2000) {
  double radius = 0.0;
  double gc_lat = 0.0;
  double gc_lon = 0.0;
  geodetic2geocentric_sph(&radius,
                          &gc_lat,
                          &gc_lon,
                          point.latitude_deg,
                          point.longitude_deg,
                          point.altitude_km,
                          WGS84_A,
                          WGS84_EPS2);

  const auto field = evaluate_spherical_raw(set, gc_lat, gc_lon, radius, time_mjd2000);
  const double delta = gc_lat - point.latitude_deg * kDegToRad;
  double up = 0.0;
  double north = 0.0;
  rot2d(&up, &north, field.radial_up, field.north, std::sin(delta), std::cos(delta));
  return make_field(north, field.east, -up);
}

std::array<std::array<double, 3>, 3> dipole_rotation_matrix(double lat_deg, double lon_deg) {
  const double lat = lat_deg * kDegToRad;
  const double lon = lon_deg * kDegToRad;
  const double sin_lat = std::sin(lat);
  const double cos_lat = std::cos(lat);
  const double sin_lon = std::sin(lon);
  const double cos_lon = std::cos(lon);
  return {{
      {{sin_lat * cos_lon, -sin_lon, cos_lat * cos_lon}},
      {{sin_lat * sin_lon, cos_lon, cos_lat * sin_lon}},
      {{-cos_lat, 0.0, sin_lat}},
  }};
}

CartesianVector sph_vector_to_cart(const SphericalVector& vector,
                                   double latitude_rad,
                                   double longitude_rad) {
  double tmp = 0.0;
  CartesianVector out;
  rot2d(&tmp,
        &out.z,
        vector.radial_up,
        vector.north,
        std::sin(latitude_rad),
        std::cos(latitude_rad));
  rot2d(&out.x,
        &out.y,
        tmp,
        vector.east,
        std::sin(longitude_rad),
        std::cos(longitude_rad));
  return out;
}

SphericalVector cart_vector_to_sph(const CartesianVector& vector,
                                   double latitude_rad,
                                   double longitude_rad) {
  const double lat = -latitude_rad;
  const double lon = -longitude_rad;
  double tmp = 0.0;
  SphericalVector out;
  rot2d(&tmp, &out.east, vector.x, vector.y, std::sin(lon), std::cos(lon));
  rot2d(&out.radial_up, &out.north, tmp, vector.z, std::sin(lat), std::cos(lat));
  return out;
}

FieldVector evaluate_dipole(const MmaCoeffSet& set,
                            const GeoPoint& point,
                            double time_mjd2000) {
  const auto rotation = dipole_rotation_matrix(set.lat_ngp_deg, set.lon_ngp_deg);

  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  double radius = 0.0;
  double gc_lat = 0.0;
  double gc_lon = 0.0;
  geodetic2geocentric(&x,
                      &y,
                      &z,
                      &radius,
                      &gc_lat,
                      &gc_lon,
                      point.latitude_deg,
                      point.longitude_deg,
                      point.altitude_km,
                      WGS84_A,
                      WGS84_EPS2);

  const double dipole_x = x * rotation[0][0] + y * rotation[1][0] + z * rotation[2][0];
  const double dipole_y = x * rotation[0][1] + y * rotation[1][1] + z * rotation[2][1];
  const double dipole_z = x * rotation[0][2] + y * rotation[1][2] + z * rotation[2][2];

  double dipole_radius = 0.0;
  double dipole_lat = 0.0;
  double dipole_lon = 0.0;
  cart2sph(&dipole_radius, &dipole_lat, &dipole_lon, dipole_x, dipole_y, dipole_z);

  const auto dipole_field =
      evaluate_spherical_raw(set, dipole_lat, dipole_lon, dipole_radius, time_mjd2000);
  const auto dipole_cart = sph_vector_to_cart(dipole_field, dipole_lat, dipole_lon);

  const CartesianVector cart{
      dipole_cart.x * rotation[0][0] + dipole_cart.y * rotation[0][1] +
          dipole_cart.z * rotation[0][2],
      dipole_cart.x * rotation[1][0] + dipole_cart.y * rotation[1][1] +
          dipole_cart.z * rotation[1][2],
      dipole_cart.x * rotation[2][0] + dipole_cart.y * rotation[2][1] +
          dipole_cart.z * rotation[2][2],
  };

  const auto geodetic_sph =
      cart_vector_to_sph(cart, point.latitude_deg * kDegToRad, point.longitude_deg * kDegToRad);
  return make_field(geodetic_sph.north, geodetic_sph.east, -geodetic_sph.radial_up);
}

FieldVector add(const FieldVector& lhs, const FieldVector& rhs) {
  return make_field(lhs.north_nt + rhs.north_nt,
                    lhs.east_nt + rhs.east_nt,
                    lhs.down_nt + rhs.down_nt);
}

bool valid_at(const MmaCoeffSet& set, double time_mjd2000) {
  return !set.times_mjd2000.empty() && set.times_mjd2000.front() <= time_mjd2000 &&
         time_mjd2000 <= set.times_mjd2000.back();
}

}  // namespace

struct SwarmExternalProvider::State {
  explicit State(const SwarmModelPaths& paths) {
    const auto path_2c =
        paths.mma_2c_path.empty() ? resource_candidate(paths.resource_dir, "mma_2c.magerr")
                                  : paths.mma_2c_path;
    const auto path_2f =
        paths.mma_2f_path.empty() ? resource_candidate(paths.resource_dir, "mma_2f.magerr")
                                  : paths.mma_2f_path;

    if (std::filesystem::exists(path_2c)) {
      auto loaded = load_resource_file(path_2c);
      sets.insert(sets.end(),
                  std::make_move_iterator(loaded.begin()),
                  std::make_move_iterator(loaded.end()));
    }
    if (std::filesystem::exists(path_2f)) {
      auto loaded = load_resource_file(path_2f);
      sets.insert(sets.end(),
                  std::make_move_iterator(loaded.begin()),
                  std::make_move_iterator(loaded.end()));
    }
    if (sets.empty()) {
      throw std::runtime_error("no Swarm MMA resources were loaded");
    }
  }

  std::vector<MmaCoeffSet> sets;
};

SwarmExternalProvider::SwarmExternalProvider(SwarmModelPaths paths)
    : state_(std::make_shared<State>(paths)) {}

FieldVector SwarmExternalProvider::evaluate(const GeoPoint& point, TimePoint time) const {
  return evaluate_components(point, time).total;
}

SwarmFieldComponents SwarmExternalProvider::evaluate_components(const GeoPoint& point,
                                                                TimePoint time) const {
  if (!state_) {
    throw std::runtime_error("SwarmExternalProvider is not initialized");
  }

  const double mjd2000 = time_to_mjd2000(time);
  SwarmFieldComponents components;
  bool any = false;

  for (const auto& set : state_->sets) {
    if (!valid_at(set, mjd2000)) {
      continue;
    }
    const auto field = set.dipole ? evaluate_dipole(set, point, mjd2000)
                                  : evaluate_geodetic(set, point, mjd2000);
    if (set.internal) {
      components.secondary = add(components.secondary, field);
    } else {
      components.primary = add(components.primary, field);
    }
    any = true;
  }

  if (!any) {
    throw std::out_of_range("time is outside loaded Swarm MMA resource validity");
  }

  components.total = add(components.primary, components.secondary);
  return components;
}

TimePoint SwarmExternalProvider::validity_start() const {
  double start = std::numeric_limits<double>::infinity();
  for (const auto& set : state_->sets) {
    if (!set.times_mjd2000.empty()) {
      start = std::min(start, set.times_mjd2000.front());
    }
  }
  return mjd2000_to_time(start);
}

TimePoint SwarmExternalProvider::validity_end() const {
  double end = -std::numeric_limits<double>::infinity();
  for (const auto& set : state_->sets) {
    if (!set.times_mjd2000.empty()) {
      end = std::max(end, set.times_mjd2000.back());
    }
  }
  return mjd2000_to_time(end);
}

}  // namespace magerr
