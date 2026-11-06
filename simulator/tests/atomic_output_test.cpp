#include "../src/atomic_output.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <system_error>
#include <unistd.h>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

class Workspace {
  public:
    explicit Workspace(const std::filesystem::path& parent) {
        auto pattern = (parent / "atomic-output-test-XXXXXX").string();
        require(::mkdtemp(pattern.data()) != nullptr, "cannot create test workspace");
        root = pattern;
    }

    Workspace(const Workspace&) = delete;
    Workspace& operator=(const Workspace&) = delete;

    ~Workspace() {
        std::error_code ignored;
        std::filesystem::remove(root / "output.csv", ignored);
        std::filesystem::remove(root / "unexpected.csv", ignored);
        std::filesystem::remove(root, ignored);
    }

    std::filesystem::path root;
};

template <typename Function>
void rejects_collision(Function write) {
    try {
        write();
    } catch (const std::filesystem::filesystem_error& error) {
        require(error.code() == std::errc::file_exists, "expected destination-exists error");
        return;
    }
    throw std::runtime_error("publication must not replace a competing destination");
}

void publication_tests(const std::filesystem::path& parent) {
    Workspace workspace(parent);
    const auto output = workspace.root / "output.csv";
    const auto unexpected = workspace.root / "unexpected.csv";

    // Deterministically create a competing entry AFTER the initial check and
    // BEFORE publication. No scheduling assumptions, sleep, or polling needed.
    rejects_collision([&] {
        epoch::detail::write_atomic(output, [&](std::ostream& staging) {
            require(!std::filesystem::exists(output), "partial final output must not be visible");
            staging << "candidate";
            std::ofstream winner(output);
            winner << "winner";
            require(static_cast<bool>(winner), "cannot create competing file");
        });
    });
    std::ifstream winner(output);
    std::string contents;
    std::getline(winner, contents);
    winner.close();
    require(contents == "winner", "competing file must remain unchanged");
    require(std::distance(std::filesystem::directory_iterator(workspace.root),
                          std::filesystem::directory_iterator{}) == 1,
            "collision must clean up staging");
    std::filesystem::remove(output);

    rejects_collision([&] {
        epoch::detail::write_atomic(output, [&](std::ostream& staging) {
            staging << "candidate";
            std::filesystem::create_symlink("unexpected.csv", output);
        });
    });
    require(std::filesystem::is_symlink(output), "competing symlink must remain unchanged");
    require(!std::filesystem::exists(unexpected), "publication must not follow competing symlink");
    std::filesystem::remove(output);
    require(std::filesystem::is_empty(workspace.root), "symlink collision must clean up staging");

    try {
        epoch::detail::write_atomic(output, [](std::ostream& staging) {
            staging << "partial";
            throw std::runtime_error("injected writer failure");
        });
        throw std::logic_error("writer failure should propagate");
    } catch (const std::runtime_error& error) {
        require(std::string(error.what()) == "injected writer failure", "wrong writer error");
    }
    require(std::filesystem::is_empty(workspace.root), "writer failure must discard staging");

    try {
        epoch::detail::write_atomic(output, [](std::ostream& staging) {
            staging << "partial";
            staging.setstate(std::ios::badbit);
        });
        throw std::logic_error("bad stream should prevent publication");
    } catch (const std::runtime_error& error) {
        require(std::string(error.what()) == "cannot finalize staging file", "wrong stream error");
    }
    require(std::filesystem::is_empty(workspace.root), "bad stream must discard staging");

    epoch::detail::write_atomic(output, [&](std::ostream& staging) {
        staging << "complete";
        require(!std::filesystem::exists(output), "final path appears only after successful write");
    });
    std::ifstream published(output);
    std::getline(published, contents);
    require(contents == "complete", "complete output must be published");
    require(std::distance(std::filesystem::directory_iterator(workspace.root),
                          std::filesystem::directory_iterator{}) == 1,
            "success must clean up staging");
}

}  // namespace

int main(int argc, char* argv[]) {
    try {
        require(argc == 2, "test requires a scratch parent directory");
        publication_tests(argv[1]);
        std::cout << "All atomic publication checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
