#include "atomic_output.hpp"

#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <system_error>
#include <unistd.h>

namespace epoch::detail {
namespace {

// A private sibling directory keeps staging on the destination filesystem.
// mkdtemp creates it exclusively with mode 0700; no shared temporary filename
// is reopened. The CLI currently targets macOS/Linux (POSIX).
class StagingDirectory {
  public:
    explicit StagingDirectory(const std::filesystem::path& destination) {
        auto parent = destination.parent_path();
        if (parent.empty()) {
            parent = ".";
        }
        auto pattern = (parent / ".epoch-simulate-XXXXXX").string();
        if (::mkdtemp(pattern.data()) == nullptr) {
            throw std::system_error(errno, std::generic_category(),
                                    "cannot create staging directory");
        }
        directory_ = pattern;
        file_ = directory_ / "data.csv";
    }

    StagingDirectory(const StagingDirectory&) = delete;
    StagingDirectory& operator=(const StagingDirectory&) = delete;

    ~StagingDirectory() {
        std::error_code ignored;
        std::filesystem::remove(file_, ignored);
        std::filesystem::remove(directory_, ignored);
    }

    const std::filesystem::path& file() const { return file_; }

  private:
    std::filesystem::path directory_;
    std::filesystem::path file_;
};

}  // namespace

void write_atomic(const std::filesystem::path& destination,
                  const std::function<void(std::ostream&)>& write) {
    // This is only an early diagnostic. The hard-link operation below is the
    // actual no-replace guarantee, including when another writer races us.
    if (std::filesystem::exists(std::filesystem::symlink_status(destination))) {
        throw std::invalid_argument("refusing to overwrite existing output (including symlinks)");
    }
    StagingDirectory staging(destination);
    std::ofstream output(staging.file());
    if (!output) {
        throw std::runtime_error("cannot open staging file");
    }
    write(output);
    output.close();
    if (!output) {
        throw std::runtime_error("cannot finalize staging file");
    }
    // Unlike rename(), link creation never replaces an existing directory entry.
    // Only a fully written, closed file becomes visible at the requested path.
    std::filesystem::create_hard_link(staging.file(), destination);
}

}  // namespace epoch::detail
