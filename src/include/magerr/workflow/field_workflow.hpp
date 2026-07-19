#pragma once

#include "magerr/models/field_model.hpp"

#include <memory>
#include <optional>

namespace magerr {

struct WorkflowConfig {
  std::optional<TimePoint> forecast_cutover;
};

class FieldWorkflow {
 public:
  FieldWorkflow(
      std::shared_ptr<MainFieldModel> main_model,
      std::shared_ptr<ExternalFieldModel> external_model,
      std::shared_ptr<FieldPredictor> predictor,
      WorkflowConfig config = {});

  SeriesResponse get_variation_series(const SeriesRequest& request) const;

 private:
  TimePoint effective_cutover() const;

  std::shared_ptr<MainFieldModel> main_model_;
  std::shared_ptr<ExternalFieldModel> external_model_;
  std::shared_ptr<FieldPredictor> predictor_;
  WorkflowConfig config_;
};

}  // namespace magerr

