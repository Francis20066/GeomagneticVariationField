#include "magerr/core/time.hpp"
#include "magerr/models/wmm2025_provider.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl/filesystem.h>
#include <pybind11/stl.h>

#include <filesystem>

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
  return out;
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
      .def("evaluate", [](const magerr::Wmm2025Provider& provider,
                          double latitude,
                          double longitude,
                          double altitude_km,
                          const std::string& time_utc) {
        return provider.evaluate(
            magerr::GeoPoint{latitude, longitude, altitude_km},
            magerr::parse_iso8601_utc(time_utc));
      });

  m.def("wmm_main_field",
        [](double latitude,
           double longitude,
           double altitude_km,
           const std::string& time_utc,
           const std::string& coefficient_dir) {
          magerr::Wmm2025Provider provider(coefficient_dir);
          return field_to_dict(provider.evaluate(
              magerr::GeoPoint{latitude, longitude, altitude_km},
              magerr::parse_iso8601_utc(time_utc)));
        },
        py::arg("latitude"),
        py::arg("longitude"),
        py::arg("altitude_km"),
        py::arg("time_utc"),
        py::arg("coefficient_dir") = "");
}


