#pragma once

#include <kigumi/io.h>

namespace kigumi {

// Used as a substitute for std::nullptr_t to avoid a build error with MSVC.
struct Null_data {};

template <>
struct Write<Null_data> {
  void operator()(std::ostream& /*out*/, const Null_data& /*t*/) const {
    // no-op
  }
};

template <>
struct Read<Null_data> {
  void operator()(std::istream& /*in*/, Null_data& /*t*/) const {
    // no-op
  }
};

}  // namespace kigumi
