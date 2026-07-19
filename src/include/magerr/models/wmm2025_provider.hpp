#pragma once

#include "magerr/models/field_model.hpp"

#include <filesystem>

namespace magerr {

class Wmm2025Provider final : public MainFieldModel {
 public:
  explicit Wmm2025Provider(std::filesystem::path coefficient_dir = {});

  FieldVector evaluate(const GeoPoint& point, TimePoint time) const override;

 private:
  std::filesystem::path coefficient_dir_;
};

}  // namespace magerr

