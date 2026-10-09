#pragma once

#include <kigumi/threading.h>

#include <algorithm>
#include <atomic>
#include <cstddef>
#include <exception>
#include <iterator>
#include <mutex>
#include <thread>
#include <vector>

namespace kigumi {

template <class RandomAccessIterator, class Init, class Body, class Post>
void parallel_do(RandomAccessIterator first, RandomAccessIterator last, Init init, Body body,
                 Post post) {
  auto size = static_cast<std::size_t>(std::distance(first, last));
  if (size == 0) {
    return;
  }

  auto num_threads = std::min(Threading_context::current().num_threads(), size);
  if (num_threads == 1) {
    auto local_state = init();
    for (auto it = first; it != last; ++it) {
      body(*it, local_state);
    }
    post(local_state);
    return;
  }

  std::vector<std::thread> threads;
  std::atomic<std::size_t> next_index{};
  std::mutex mutex;
  std::exception_ptr exception_ptr;

  threads.reserve(num_threads);
  for (std::size_t tid = 0; tid < num_threads; ++tid) {
    threads.emplace_back([&] {
      auto local_state = init();

      try {
        while (true) {
          auto index = next_index++;
          if (index >= size) {
            break;
          }

          body(*(first + index), local_state);

          if (exception_ptr) {
            return;
          }
        }

        std::lock_guard lock{mutex};
        post(local_state);
      } catch (...) {
        std::lock_guard lock{mutex};
        if (!exception_ptr) {
          exception_ptr = std::current_exception();
        }
      }
    });
  }

  for (auto& thread : threads) {
    thread.join();
  }

  if (exception_ptr) {
    std::rethrow_exception(exception_ptr);
  }
}

template <class RandomAccessIterator, class Body>
void parallel_do(RandomAccessIterator first, RandomAccessIterator last, Body body) {
  parallel_do(
      first, last, [] { return nullptr; }, [&](const auto& item, auto) { body(item); },
      [](auto) {});
}

}  // namespace kigumi
