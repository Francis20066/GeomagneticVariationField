#include "magerr/core/time.hpp"
#include "magerr/models/swarm_external_provider.hpp"
#include "magerr/models/wmm2025_provider.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl/filesystem.h>

#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

py::dict field_to_dict(const magerr::FieldVector& field) {
  py::dict out;
  out["north"] = field.north_nt;
  out["east"] = field.east_nt;
  out["down"] = field.down_nt;
  out["total"] = field.total_nt;
  out["declination"] = field.declination_deg;
  out["inclination"] = field.inclination_deg;
  out["decl"] = field.declination_deg;
  out["incl"] = field.inclination_deg;
  return out;
}

magerr::FieldVector add_field(const magerr::FieldVector& lhs,
                              const magerr::FieldVector& rhs) {
  const double north = lhs.north_nt + rhs.north_nt;
  const double east = lhs.east_nt + rhs.east_nt;
  const double down = lhs.down_nt + rhs.down_nt;
  const double horizontal = std::hypot(north, east);
  return magerr::FieldVector{
      north,
      east,
      down,
      std::hypot(horizontal, down),
      std::atan2(east, north) * 180.0 / 3.14159265358979323846,
      std::atan2(down, horizontal) * 180.0 / 3.14159265358979323846,
  };
}

std::filesystem::path module_resource_root() {
  const auto module = py::module_::import("magerr_native");
  const auto module_file =
      std::filesystem::path(py::cast<std::string>(py::str(module.attr("__file__"))));
  const auto candidate = module_file.parent_path() / "resources";
  if (std::filesystem::exists(candidate)) {
    return candidate;
  }
  return {};
}

std::filesystem::path wmm_path_or_default(const std::string& coefficient_dir) {
  if (!coefficient_dir.empty()) {
    return coefficient_dir;
  }
  const auto root = module_resource_root();
  if (!root.empty()) {
    return root / "wmm2025";
  }
  return {};
}

magerr::SwarmModelPaths swarm_paths_or_default(const std::string& resource_dir,
                                               const std::string& mma_2c_path,
                                               const std::string& mma_2f_path) {
  magerr::SwarmModelPaths paths;
  paths.resource_dir = resource_dir;
  paths.mma_2c_path = mma_2c_path;
  paths.mma_2f_path = mma_2f_path;
  if (paths.resource_dir.empty() && paths.mma_2c_path.empty() && paths.mma_2f_path.empty()) {
    const auto root = module_resource_root();
    if (!root.empty()) {
      paths.resource_dir = root / "swarm_mma";
    }
  }
  return paths;
}

magerr::GeoPoint point_from_args(double latitude, double longitude, double altitude_km) {
  return magerr::GeoPoint{latitude, longitude, altitude_km};
}

py::dict components_to_dict(const magerr::SwarmFieldComponents& components) {
  py::dict out;
  out["primary"] = field_to_dict(components.primary);
  out["secondary"] = field_to_dict(components.secondary);
  out["total"] = field_to_dict(components.total);
  return out;
}

py::dict field_at_impl(double latitude,
                       double longitude,
                       double altitude_km,
                       const std::string& time_utc,
                       const std::string& coefficient_dir,
                       const std::string& swarm_resource_dir,
                       const std::string& mma_2c_path,
                       const std::string& mma_2f_path) {
  const auto point = point_from_args(latitude, longitude, altitude_km);
  const auto time = magerr::parse_iso8601_utc(time_utc);

  magerr::Wmm2025Provider wmm(wmm_path_or_default(coefficient_dir));
  const auto main = wmm.evaluate(point, time);

  py::dict out;
  out["time"] = time_utc;
  out["main"] = field_to_dict(main);

  try {
    magerr::SwarmExternalProvider swarm(
        swarm_paths_or_default(swarm_resource_dir, mma_2c_path, mma_2f_path));
    const auto components = swarm.evaluate_components(point, time);
    out["swarm"] = components_to_dict(components);
    out["external_source"] = "swarm_mma";
    out["total"] = field_to_dict(add_field(main, components.total));
  } catch (const std::out_of_range&) {
    out["swarm"] = py::none();
    out["external_source"] = "missing";
    out["total"] = field_to_dict(main);
  }

  return out;
}

std::vector<std::string> expand_times(const std::string& start_time,
                                      const std::string& end_time,
                                      std::int64_t step_seconds) {
  const magerr::TimeRange range{
      magerr::parse_iso8601_utc(start_time),
      magerr::parse_iso8601_utc(end_time),
      step_seconds,
  };
  std::vector<std::string> out;
  for (const auto& time : magerr::expand_time_range(range)) {
    out.push_back(magerr::to_iso8601(time));
  }
  return out;
}

std::vector<double> sequence_to_doubles(const py::sequence& values, const char* name) {
  std::vector<double> out;
  out.reserve(static_cast<std::size_t>(py::len(values)));
  for (const auto item : values) {
    out.push_back(py::cast<double>(item));
  }
  if (out.empty()) {
    throw std::invalid_argument(std::string(name) + " must not be empty");
  }
  return out;
}

std::vector<std::string> sequence_to_strings(const py::sequence& values, const char* name) {
  std::vector<std::string> out;
  out.reserve(static_cast<std::size_t>(py::len(values)));
  for (const auto item : values) {
    out.push_back(py::cast<std::string>(item));
  }
  if (out.empty()) {
    throw std::invalid_argument(std::string(name) + " must not be empty");
  }
  return out;
}

void require_same_size(std::size_t expected, std::size_t actual, const char* name) {
  if (actual != expected) {
    throw std::invalid_argument(std::string(name) + " must have the same length as latitudes");
  }
}

}  // namespace

PYBIND11_MODULE(magerr_native, m) {
  m.doc() = "MagErr native magnetic-field core";

  py::class_<magerr::GeoPoint>(m, "GeoPoint")
      .def(py::init<>())
      .def_readwrite("latitude_deg", &magerr::GeoPoint::latitude_deg)
      .def_readwrite("longitude_deg", &magerr::GeoPoint::longitude_deg)
      .def_readwrite("altitude_km", &magerr::GeoPoint::altitude_km);

  py::class_<magerr::FieldVector>(m, "FieldVector")
      .def_readonly("north_nt", &magerr::FieldVector::north_nt)
      .def_readonly("east_nt", &magerr::FieldVector::east_nt)
      .def_readonly("down_nt", &magerr::FieldVector::down_nt)
      .def_readonly("total_nt", &magerr::FieldVector::total_nt)
      .def_readonly("declination_deg", &magerr::FieldVector::declination_deg)
      .def_readonly("inclination_deg", &magerr::FieldVector::inclination_deg);

  py::class_<magerr::Wmm2025Provider>(m, "Wmm2025Provider")
      .def(py::init<std::filesystem::path>(), py::arg("coefficient_dir") = "")
      .def("evaluate",
           [](const magerr::Wmm2025Provider& provider,
              double latitude,
              double longitude,
              double altitude_km,
              const std::string& time_utc) {
             return provider.evaluate(point_from_args(latitude, longitude, altitude_km),
                                      magerr::parse_iso8601_utc(time_utc));
           });

  py::class_<magerr::SwarmExternalProvider>(m, "SwarmExternalProvider")
      .def(py::init([](const std::string& resource_dir,
                       const std::string& mma_2c_path,
                       const std::string& mma_2f_path) {
             return std::make_unique<magerr::SwarmExternalProvider>(
                 swarm_paths_or_default(resource_dir, mma_2c_path, mma_2f_path));
           }),
           py::arg("resource_dir") = "",
           py::arg("mma_2c_path") = "",
           py::arg("mma_2f_path") = "")
      .def("evaluate_components",
           [](const magerr::SwarmExternalProvider& provider,
              double latitude,
              double longitude,
              double altitude_km,
              const std::string& time_utc) {
             return components_to_dict(provider.evaluate_components(
                 point_from_args(latitude, longitude, altitude_km),
                 magerr::parse_iso8601_utc(time_utc)));
           });

  m.def("wmm_main_field",
        [](double latitude,
           double longitude,
           double altitude_km,
           const std::string& time_utc,
           const std::string& coefficient_dir) {
          magerr::Wmm2025Provider provider(wmm_path_or_default(coefficient_dir));
          return field_to_dict(provider.evaluate(point_from_args(latitude, longitude, altitude_km),
                                                 magerr::parse_iso8601_utc(time_utc)));
        },
        py::arg("latitude"),
        py::arg("longitude"),
        py::arg("altitude_km"),
        py::arg("time_utc"),
        py::arg("coefficient_dir") = "");

  m.def("swarm_mma_field",
        [](double latitude,
           double longitude,
           double altitude_km,
           const std::string& time_utc,
           const std::string& component,
           const std::string& resource_dir,
           const std::string& mma_2c_path,
           const std::string& mma_2f_path) {
          magerr::SwarmExternalProvider provider(
              swarm_paths_or_default(resource_dir, mma_2c_path, mma_2f_path));
          const auto components = provider.evaluate_components(
              point_from_args(latitude, longitude, altitude_km),
              magerr::parse_iso8601_utc(time_utc));
          if (component == "primary") {
            return field_to_dict(components.primary);
          }
          if (component == "secondary") {
            return field_to_dict(components.secondary);
          }
          if (component == "components") {
            return components_to_dict(components);
          }
          return field_to_dict(components.total);
        },
        py::arg("latitude"),
        py::arg("longitude"),
        py::arg("altitude_km"),
        py::arg("time_utc"),
        py::arg("component") = "total",
        py::arg("resource_dir") = "",
        py::arg("mma_2c_path") = "",
        py::arg("mma_2f_path") = "");

  m.def("field_at",
        &field_at_impl,
        py::arg("latitude"),
        py::arg("longitude"),
        py::arg("altitude_km"),
        py::arg("time_utc"),
        py::arg("coefficient_dir") = "",
        py::arg("swarm_resource_dir") = "",
        py::arg("mma_2c_path") = "",
        py::arg("mma_2f_path") = "");

  m.def("get_variation_series",
        [](double latitude,
           double longitude,
           double altitude_km,
           const std::string& start_time,
           const std::string& end_time,
           std::int64_t step_seconds,
           const std::string& coefficient_dir,
           const std::string& swarm_resource_dir,
           const std::string& mma_2c_path,
           const std::string& mma_2f_path) {
          py::list out;
          for (const auto& time : expand_times(start_time, end_time, step_seconds)) {
            out.append(field_at_impl(latitude,
                                     longitude,
                                     altitude_km,
                                     time,
                                     coefficient_dir,
                                     swarm_resource_dir,
                                     mma_2c_path,
                                     mma_2f_path));
          }
          return out;
        },
        py::arg("latitude"),
        py::arg("longitude"),
        py::arg("altitude_km"),
        py::arg("start_time"),
        py::arg("end_time"),
        py::arg("step_seconds") = 60,
        py::arg("coefficient_dir") = "",
        py::arg("swarm_resource_dir") = "",
        py::arg("mma_2c_path") = "",
        py::arg("mma_2f_path") = "");

  m.def("field_at_batch",
        [](const py::sequence& latitudes,
           const py::sequence& longitudes,
           const py::sequence& altitude_km,
           const py::sequence& time_utc,
           const std::string& coefficient_dir,
           const std::string& swarm_resource_dir,
           const std::string& mma_2c_path,
           const std::string& mma_2f_path) {
          const auto lat = sequence_to_doubles(latitudes, "latitudes");
          const auto lon = sequence_to_doubles(longitudes, "longitudes");
          const auto alt = sequence_to_doubles(altitude_km, "altitude_km");
          const auto times = sequence_to_strings(time_utc, "time_utc");
          require_same_size(lat.size(), lon.size(), "longitudes");
          require_same_size(lat.size(), alt.size(), "altitude_km");
          require_same_size(lat.size(), times.size(), "time_utc");

          py::list out;
          for (std::size_t i = 0; i < lat.size(); ++i) {
            out.append(field_at_impl(lat[i],
                                     lon[i],
                                     alt[i],
                                     times[i],
                                     coefficient_dir,
                                     swarm_resource_dir,
                                     mma_2c_path,
                                     mma_2f_path));
          }
          return out;
        },
        py::arg("latitudes"),
        py::arg("longitudes"),
        py::arg("altitude_km"),
        py::arg("time_utc"),
        py::arg("coefficient_dir") = "",
        py::arg("swarm_resource_dir") = "",
        py::arg("mma_2c_path") = "",
        py::arg("mma_2f_path") = "");
}
