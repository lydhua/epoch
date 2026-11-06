#pragma once

#include <filesystem>
#include <functional>
#include <iosfwd>

namespace epoch::detail {

// Invoke write against private staging, then atomically publish without replace.
// Exceptions discard staging; unsupported hard links fail rather than fall back.
void write_atomic(const std::filesystem::path& destination,
                  const std::function<void(std::ostream&)>& write);

}  // namespace epoch::detail
