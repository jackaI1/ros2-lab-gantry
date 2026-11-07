#pragma once
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace gantry_monitor {
struct Limits {
  std::array<double, 3> upper{0.22, 0.16, 0.08};
  double margin{0.0005};
  double speed{0.06};
};
// Stateless logic makes every message independently safe to evaluate.
inline std::string check(const std::vector<std::string>& names,
                         const std::vector<double>& position,
                         const std::vector<double>& velocity,
                         const Limits& limits = {}) {
  const std::array<std::string, 3> joints{"x_joint", "y_joint", "z_joint"};
  if (names.size() != position.size() || names.size() != velocity.size())
    return "invalid_feedback";
  for (std::size_t axis = 0; axis < joints.size(); ++axis) {
    std::size_t found = names.size();
    for (std::size_t i = 0; i < names.size(); ++i) {
      if (names[i] == joints[axis]) {
        if (found != names.size()) return "invalid_feedback";
        found = i;
      }
    }
    if (found == names.size() || !std::isfinite(position[found]) ||
        !std::isfinite(velocity[found])) return "invalid_feedback";
    if (position[found] <= limits.margin || position[found] >= limits.upper[axis]-limits.margin)
      return joints[axis] + " limit switch";
    if (std::abs(velocity[found]) > limits.speed) return joints[axis] + " overspeed";
  }
  return "OK";
}
}  // namespace gantry_monitor
