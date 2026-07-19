#pragma once

#include "magerr/models/field_model.hpp"

#include <filesystem>
#include <memory>

namespace magerr {

struct SwarmModelPaths {
  std::filesystem::path resource_dir;
  std::filesystem::path mma_2c_path;
  std::filesystem::path mma_2f_path;
};

struct SwarmFieldComponents {
  FieldVector primary;
  FieldVector secondary;
  FieldVector total;
};

class SwarmExternalProvider final : public ExternalFieldModel {
 public:
  explicit SwarmExternalProvider(SwarmModelPaths paths);

  FieldVector evaluate(const GeoPoint& point, TimePoint time) const override;
  SwarmFieldComponents evaluate_components(const GeoPoint& point, TimePoint time) const;
  TimePoint validity_start() const override;
  TimePoint validity_end() const override;

 private:
  struct State;
  std::shared_ptr<State> state_;
};

}  // namespace magerr
