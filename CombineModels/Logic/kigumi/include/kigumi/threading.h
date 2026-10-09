#pragma once

#include <kigumi/Context.h>

#include <algorithm>
#include <thread>

namespace kigumi {

class Threading_options {
 public:
  std::size_t num_threads() const { return num_threads_; }

  void set_num_threads(std::size_t num_threads) {
    num_threads_ =
        std::clamp(num_threads, std::size_t{1},
                   static_cast<std::size_t>(std::max(1U, std::thread::hardware_concurrency())));
  }

 private:
  std::size_t num_threads_{std::max(1U, std::thread::hardware_concurrency())};
};

using Threading_context = Context<Threading_options>;

}  // namespace kigumi
