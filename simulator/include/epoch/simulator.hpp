#pragma once

#include <cstdint>
#include <iosfwd>

namespace epoch {

struct SimulationConfig {
    std::uint64_t seed = 42;
    std::uint32_t sessions = 1000;
    std::uint32_t users = 100;
    std::uint32_t reviews_per_session = 8;
    double min_half_life_days = 1.0;
    double max_half_life_days = 14.0;
};

// A session is one synthetic learner-item trajectory containing several reviews.
// Ground-truth parameters are exported for diagnostics, never as model features.
void validate(const SimulationConfig& config);
double recall_probability(double elapsed_days, double half_life_days);
void write_simulation(std::ostream& output, const SimulationConfig& config);

}  // namespace epoch
