#include "magerr/models/swarm_external_provider.hpp"

#include <stdexcept>

namespace magerr {

SwarmExternalProvider::SwarmExternalProvider(SwarmModelPaths paths)
    : paths_(std::move(paths)) {}

FieldVector SwarmExternalProvider::evaluate(const GeoPoint&, TimePoint) const {
  throw std::logic_error(
      "SwarmExternalProvider C++ implementation is not ported yet. "
      "Port geoist.model.magmod parser_mio/parser_mma, coefficient classes, "
      "spherical harmonic evaluator, and dipole rotations behind this interface.");
}

TimePoint SwarmExternalProvider::validity_start() const {
  return TimePoint::min();
}

TimePoint SwarmExternalProvider::validity_end() const {
  return TimePoint::max();
}

}  // namespace magerr

