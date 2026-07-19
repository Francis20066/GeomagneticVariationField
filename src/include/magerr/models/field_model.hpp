#pragma once

#include "magerr/core/types.hpp"

#include <vector>

namespace magerr {

class MainFieldModel {
 public:
  virtual ~MainFieldModel() = default;
  virtual FieldVector evaluate(const GeoPoint& point, TimePoint time) const = 0;
};

class ExternalFieldModel {
 public:
  virtual ~ExternalFieldModel() = default;
  virtual FieldVector evaluate(const GeoPoint& point, TimePoint time) const = 0;
  virtual TimePoint validity_start() const = 0;
  virtual TimePoint validity_end() const = 0;
};

class FieldPredictor {
 public:
  virtual ~FieldPredictor() = default;

  virtual std::vector<FieldVector> forecast(
      const GeoPoint& point,
      const std::vector<FieldSample>& history,
      const std::vector<TimePoint>& future_times) const = 0;
};

}  // namespace magerr

