#include "magerr/workflow/field_workflow.hpp"

#include "magerr/core/time.hpp"

#include <algorithm>
#include <chrono>
#include <stdexcept>

namespace magerr {

FieldWorkflow::FieldWorkflow(
    std::shared_ptr<MainFieldModel> main_model,
    std::shared_ptr<ExternalFieldModel> external_model,
    std::shared_ptr<FieldPredictor> predictor,
    WorkflowConfig config)
    : main_model_(std::move(main_model)),
      external_model_(std::move(external_model)),
      predictor_(std::move(predictor)),
      config_(std::move(config)) {
  if (!main_model_) {
    throw std::invalid_argument("main_model is required");
  }
}

SeriesResponse FieldWorkflow::get_variation_series(const SeriesRequest& request) const {
  const auto times = expand_time_range(request.range);
  const auto cutover = effective_cutover();

  SeriesResponse response;
  response.samples.reserve(times.size());

  std::vector<TimePoint> future_times;
  for (const auto time : times) {
    FieldSample sample;
    sample.time = time;
    sample.decimal_year = decimal_year(time);
    sample.main = main_model_->evaluate(request.point, time);

    if (external_model_ && time <= cutover) {
      sample.external = external_model_->evaluate(request.point, time);
      sample.external_source = FieldSource::Swarm;
    } else if (time > cutover) {
      future_times.push_back(time);
      sample.external_source = FieldSource::Predictor;
    }

    response.samples.push_back(sample);
  }

  if (!future_times.empty() && predictor_) {
    const auto predicted = predictor_->forecast(request.point, response.samples, future_times);
    std::size_t predicted_index = 0;
    for (auto& sample : response.samples) {
      if (sample.external_source == FieldSource::Predictor) {
        if (predicted_index >= predicted.size()) {
          throw std::runtime_error("predictor returned fewer samples than requested");
        }
        sample.external = predicted[predicted_index++];
      }
    }
  }

  return response;
}

TimePoint FieldWorkflow::effective_cutover() const {
  auto cutover = config_.forecast_cutover.value_or(std::chrono::system_clock::now());
  if (external_model_) {
    cutover = std::min(cutover, external_model_->validity_end());
  }
  return cutover;
}

}  // namespace magerr


