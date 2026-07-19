#include "magerr/models/wmm2025_provider.hpp"

#include "magerr/core/time.hpp"

extern "C" {
#include "GeomagnetismHeader.h"
}

#include <algorithm>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <utility>

namespace magerr {
namespace {

std::filesystem::path resolve_wmm_cof(std::filesystem::path coefficient_path) {
  if (!coefficient_path.empty()) {
    if (std::filesystem::is_directory(coefficient_path)) {
      coefficient_path /= "WMM.COF";
    }
    if (std::filesystem::exists(coefficient_path)) {
      return coefficient_path;
    }
    throw std::runtime_error("WMM.COF not found: " + coefficient_path.string());
  }

  const auto cwd = std::filesystem::current_path();
  const std::filesystem::path candidates[] = {
#ifdef MAGERR_DEFAULT_RESOURCE_DIR
      std::filesystem::path(MAGERR_DEFAULT_RESOURCE_DIR) / "wmm2025" / "WMM.COF",
#endif
      cwd / "src" / "resources" / "wmm2025" / "WMM.COF",
      cwd / "resources" / "wmm2025" / "WMM.COF",
      cwd / "WMM.COF",
  };

  for (const auto& candidate : candidates) {
    if (std::filesystem::exists(candidate)) {
      return candidate;
    }
  }

  throw std::runtime_error(
      "WMM.COF not found; pass coefficient_dir or set the working directory to the project root");
}

int model_term_count(const MAGtype_MagneticModel& model) {
  return (std::max(model.nMax, model.nMaxSecVar) + 1) *
         (std::max(model.nMax, model.nMaxSecVar) + 2) / 2;
}

}  // namespace

struct Wmm2025Provider::State {
  explicit State(const std::filesystem::path& coefficient_path) {
    MAGtype_MagneticModel* loaded[1] = {nullptr};
    auto path_text = coefficient_path.string();
    if (!MAG_robustReadMagModels(path_text.data(), &loaded, 1) || loaded[0] == nullptr) {
      throw std::runtime_error("failed to read WMM.COF: " + coefficient_path.string());
    }

    model = loaded[0];
    timed_terms = model_term_count(*model);
    MAG_SetDefaults(&ellipsoid, &geoid);
    geoid.UseGeoid = 0;
    geoid.Geoid_Initialized = 0;
  }

  ~State() {
    if (model != nullptr) {
      MAG_FreeMagneticModelMemory(model);
    }
  }

  MAGtype_MagneticModel* model = nullptr;
  int timed_terms = 0;
  MAGtype_Ellipsoid ellipsoid{};
  MAGtype_Geoid geoid{};
};

Wmm2025Provider::Wmm2025Provider(std::filesystem::path coefficient_dir)
    : state_(std::make_unique<State>(resolve_wmm_cof(std::move(coefficient_dir)))) {}

Wmm2025Provider::~Wmm2025Provider() = default;
Wmm2025Provider::Wmm2025Provider(Wmm2025Provider&&) noexcept = default;
Wmm2025Provider& Wmm2025Provider::operator=(Wmm2025Provider&&) noexcept = default;

FieldVector Wmm2025Provider::evaluate(const GeoPoint& point, TimePoint time) const {
  if (!state_ || state_->model == nullptr) {
    throw std::runtime_error("WMM2025 provider is not initialized");
  }

  MAGtype_CoordGeodetic geodetic{};
  geodetic.HeightAboveEllipsoid = point.altitude_km;
  geodetic.phi = point.latitude_deg;
  geodetic.lambda = point.longitude_deg;
  geodetic.UseGeoid = 0;

  MAGtype_CoordSpherical spherical{};
  MAG_GeodeticToSpherical(state_->ellipsoid, geodetic, &spherical);

  MAGtype_Date date{};
  date.DecimalYear = decimal_year(time);

  MAGtype_MagneticModel* timed_model = MAG_AllocateModelMemory(state_->timed_terms);
  if (timed_model == nullptr) {
    throw std::runtime_error("failed to allocate WMM timed model");
  }

  MAGtype_GeoMagneticElements elements{};
  try {
    MAG_TimelyModifyMagneticModel(date, state_->model, timed_model);
    MAG_Geomag(state_->ellipsoid, spherical, geodetic, timed_model, &elements);
    MAG_CalculateGridVariation(geodetic, &elements);
  } catch (...) {
    MAG_FreeMagneticModelMemory(timed_model);
    throw;
  }
  MAG_FreeMagneticModelMemory(timed_model);

  return FieldVector{
      elements.X,
      elements.Y,
      elements.Z,
      elements.F,
      elements.Decl,
      elements.Incl,
  };
}

}  // namespace magerr
