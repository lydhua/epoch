#include "epoch/simulator.hpp"

#include <cmath>
#include <iomanip>
#include <locale>
#include <ostream>
#include <random>
#include <stdexcept>
#include <vector>

namespace epoch {
namespace {

// Explicit conversion avoids implementation-dependent std::*_distribution draws.
double unit_random(std::mt19937_64& engine) {
    return static_cast<double>(engine() >> 11) * 0x1.0p-53;
}

double between(std::mt19937_64& engine, double low, double high) {
    return low + (high - low) * unit_random(engine);
}

}  // namespace

void validate(const SimulationConfig& config) {
    if (config.sessions == 0 || config.users == 0 || config.reviews_per_session == 0) {
        throw std::invalid_argument("sessions, users, and reviews must be positive");
    }
    if (!std::isfinite(config.min_half_life_days) || !std::isfinite(config.max_half_life_days) ||
        config.min_half_life_days <= 0 || config.max_half_life_days < config.min_half_life_days ||
        config.max_half_life_days > 3650) {
        throw std::invalid_argument("half-life bounds must satisfy 0 < min <= max <= 3650 days");
    }
    // Bounds are resource guards, not claims about realistic learning behavior.
    if (config.sessions > 1000000 || config.users > 1000000 || config.reviews_per_session > 100) {
        throw std::invalid_argument("maximum: 1000000 sessions/users and 100 reviews per session");
    }
}

double recall_probability(double elapsed_days, double half_life_days) {
    if (!std::isfinite(elapsed_days) || elapsed_days < 0 || !std::isfinite(half_life_days) ||
        half_life_days <= 0) {
        throw std::invalid_argument(
            "elapsed days must be finite/nonnegative; half-life finite/positive");
    }
    return std::exp2(-elapsed_days / half_life_days);
}

void write_simulation(std::ostream& output, const SimulationConfig& config) {
    validate(config);
    if (!output) {
        throw std::runtime_error("simulation output stream is not writable");
    }
    std::mt19937_64 engine(config.seed);
    std::vector<double> user_half_lives;
    user_half_lives.reserve(config.users);
    for (std::uint32_t user = 0; user < config.users; ++user) {
        user_half_lives.push_back(std::exp(between(engine, std::log(config.min_half_life_days),
                                                   std::log(config.max_half_life_days))));
    }

    output.imbue(std::locale::classic());
    output << std::setprecision(17);
    output << "schema_version,seed,session_id,user_id,item_id,review_index,"
              "elapsed_days,time_days,prior_successes,success,solve_seconds,"
              "oracle_half_life_days,oracle_recall_probability\n";
    for (std::uint32_t session = 0; session < config.sessions; ++session) {
        const auto user = session % config.users;
        // Each session has a distinct item; user effects persist across sessions.
        const double difficulty = between(engine, 0.7, 1.5);
        double half_life = user_half_lives[user] / difficulty;
        double time_days = 0;
        std::uint32_t prior_successes = 0;
        for (std::uint32_t review = 0; review < config.reviews_per_session; ++review) {
            // Delays do not use hidden learner parameters: no oracle scheduling.
            const double elapsed = std::exp(between(engine, std::log(0.25), std::log(30.0)));
            time_days += elapsed;
            const double probability = recall_probability(elapsed, half_life);
            const bool success = unit_random(engine) < probability;
            const double seconds = between(engine, 300, 2400) * difficulty * (success ? 1.0 : 1.5);
            output << 1 << ',' << config.seed << ',' << session << ',' << user << ',' << session
                   << ',' << review << ',' << elapsed << ',' << time_days << ',' << prior_successes
                   << ',' << static_cast<int>(success) << ',' << seconds << ',' << half_life << ','
                   << probability << '\n';
            if (!output) {
                throw std::runtime_error("failed to write simulation output");
            }
            // An attempt includes studying the solution, even after failure.
            half_life *= success ? 1.35 : 1.1;
            prior_successes += static_cast<std::uint32_t>(success);
        }
    }
    if (!output) {
        throw std::runtime_error("failed to write simulation output");
    }
}

}  // namespace epoch
