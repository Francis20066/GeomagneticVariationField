#pragma once

#include "magerr/models/field_model.hpp"

#include <filesystem>
#include <memory>

namespace magerr {

class Wmm2025Provider final : public MainFieldModel {
 public:
  explicit Wmm2025Provider(std::filesystem::path coefficient_dir = {});
  ~Wmm2025Provider() override;

  Wmm2025Provider(const Wmm2025Provider&) = delete;
  Wmm2025Provider& operator=(const Wmm2025Provider&) = delete;
  Wmm2025Provider(Wmm2025Provider&&) noexcept;
  Wmm2025Provider& operator=(Wmm2025Provider&&) noexcept;

  FieldVector evaluate(const GeoPoint& point, TimePoint time) const override;

 private:
  struct State;
  std::unique_ptr<State> state_;
};

}  // namespace magerr
