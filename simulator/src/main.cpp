#include "atomic_output.hpp"
#include "epoch/simulator.hpp"

#include <charconv>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {

std::uint64_t integer(std::string_view text) {
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size()) {
        throw std::invalid_argument("expected an unsigned integer: " + std::string(text));
    }
    return value;
}

std::uint32_t count(std::string_view text) {
    const auto value = integer(text);
    if (value > std::numeric_limits<std::uint32_t>::max()) {
        throw std::invalid_argument("count exceeds uint32 range");
    }
    return static_cast<std::uint32_t>(value);
}

}  // namespace

int main(int argc, char* argv[]) {
    try {
        epoch::SimulationConfig config;
        std::filesystem::path output_path;
        for (int index = 1; index < argc; ++index) {
            const std::string_view option(argv[index]);
            if (option == "--help") {
                std::cout << "Usage: epoch-simulate --output PATH [--sessions N] [--users N] "
                             "[--reviews N] [--seed N]\n"
                             "Defaults: 1000 sessions, 100 users, 8 reviews, seed 42.\n"
                             "Output must not already exist. Parent directories must exist.\n";
                return 0;
            }
            if (index + 1 == argc) {
                throw std::invalid_argument("missing value for " + std::string(option));
            }
            const std::string_view value(argv[++index]);
            if (option == "--output") {
                output_path = value;
            } else if (option == "--sessions") {
                config.sessions = count(value);
            } else if (option == "--users") {
                config.users = count(value);
            } else if (option == "--reviews") {
                config.reviews_per_session = count(value);
            } else if (option == "--seed") {
                config.seed = integer(value);
            } else {
                throw std::invalid_argument("unknown option: " + std::string(option));
            }
        }
        epoch::validate(config);
        if (output_path.empty()) {
            throw std::invalid_argument("--output is required (use --help for usage)");
        }
        epoch::detail::write_atomic(
            output_path, [&](std::ostream& output) { epoch::write_simulation(output, config); });
        std::cout << "Wrote " << config.sessions << " sessions ("
                  << static_cast<std::uint64_t>(config.sessions) * config.reviews_per_session
                  << " reviews), seed " << config.seed << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "epoch-simulate: " << error.what() << '\n';
        return 1;
    }
}
