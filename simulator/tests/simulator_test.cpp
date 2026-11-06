#include "epoch/simulator.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <streambuf>
#include <string>
#include <vector>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

template <typename Function>
void rejects(Function function) {
    try {
        function();
    } catch (const std::invalid_argument&) {
        return;
    }
    throw std::runtime_error("expected invalid_argument");
}

std::vector<std::string> random_values(const std::string& csv) {
    std::istringstream input(csv);
    std::string line;
    std::getline(input, line);  // Header.
    std::vector<std::string> values;
    while (std::getline(input, line)) {
        std::istringstream row(line);
        std::string field;
        int column = 0;
        while (std::getline(row, field, ',')) {
            // Elapsed time, duration, and hidden half-life, not seed metadata.
            if (column == 6 || column == 10 || column == 11) {
                values.push_back(field);
            }
            ++column;
        }
    }
    return values;
}

}  // namespace

int main() {
    try {
        require(epoch::recall_probability(0, 5) == 1, "zero elapsed recall");
        require(epoch::recall_probability(5, 5) == 0.5, "half-life definition");
        double previous = 1;
        for (int day = 0; day <= 1000; ++day) {
            const double probability = epoch::recall_probability(day, 5);
            require(probability >= 0 && probability <= previous, "bounded monotone recall");
            previous = probability;
        }
        require(epoch::recall_probability(4, 10) > epoch::recall_probability(4, 2),
                "individual forgetting rates");
        rejects([] { epoch::recall_probability(-1, 2); });
        rejects([] { epoch::recall_probability(1, 0); });
        rejects([] { epoch::recall_probability(std::numeric_limits<double>::infinity(), 2); });
        rejects([] { epoch::recall_probability(1, std::numeric_limits<double>::quiet_NaN()); });

        epoch::SimulationConfig config;
        config.sessions = 4;
        config.users = 2;
        config.reviews_per_session = 3;
        std::ostringstream first;
        std::ostringstream repeat;
        epoch::write_simulation(first, config);
        epoch::write_simulation(repeat, config);
        require(first.str() == repeat.str(), "seed reproducibility");
        config.seed += 1;
        std::ostringstream different;
        epoch::write_simulation(different, config);
        require(random_values(first.str()) != random_values(different.str()),
                "seed changes sampled values, not just metadata");

        config.sessions = 0;
        rejects([&] { epoch::validate(config); });
        config.sessions = 4;
        config.users = 0;
        rejects([&] { epoch::validate(config); });
        config.users = 2;
        config.reviews_per_session = 101;
        rejects([&] { epoch::validate(config); });
        config.reviews_per_session = 3;
        config.min_half_life_days = 20;
        rejects([&] { epoch::validate(config); });
        config.min_half_life_days = std::numeric_limits<double>::quiet_NaN();
        rejects([&] { epoch::validate(config); });

        config.min_half_life_days = 1;
        std::ostream broken(nullptr);
        bool write_failed = false;
        try {
            epoch::write_simulation(broken, config);
        } catch (const std::runtime_error&) {
            write_failed = true;
        }
        require(write_failed, "output errors must propagate");
        std::cout << "All simulator unit checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
