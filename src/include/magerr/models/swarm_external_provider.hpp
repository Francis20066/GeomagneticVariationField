#pragma once

#include "magerr/models/field_model.hpp"

#include <filesystem>

namespace magerr {

struct SwarmModelPaths {
  std::filesystem::path mio_2c_path;
  std::filesystem::path mma_2f_path;
};

class SwarmExternalProvider final : public ExternalFieldModel {
 public:
  explicit SwarmExternalProvider(SwarmModelPaths paths);

  FieldVector evaluate(const GeoPoint& point, TimePoint time) const override;
  TimePoint validity_start() const override;
  TimePoint validity_end() const override;

 private:
  SwarmModelPaths paths_;
};

}  // namespace magerr

