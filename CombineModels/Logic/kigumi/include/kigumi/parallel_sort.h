#pragma once

#include <kigumi/threading.h>

#include <algorithm>
#include <barrier>
#include <functional>
#include <iterator>
#include <thread>
#include <vector>

namespace kigumi {

template <class RandomAccessIterator, class Compare>
void parallel_sort(RandomAccessIterator first, RandomAccessIterator last, Compare comp) {
  auto size = static_cast<std::size_t>(std::distance(first, last));
  if (size == 0) {
    return;
  }

  auto num_threads = std::min(Threading_context::current().num_threads(), (size + 1023) / 1024);
  if (num_threads == 1) {
    std::sort(first, last, comp);
    return;
  }

  std::vector<RandomAccessIterator> partitions;
  std::vector<std::thread> threads;
  std::barrier barrier(static_cast<std::ptrdiff_t>(num_threads));

  partitions.reserve(num_threads + 1);
  auto size_per_thread = size / num_threads;
  for (std::size_t tid = 0; tid < num_threads; ++tid) {
    partitions.push_back(first + tid * size_per_thread);
  }
  partitions.push_back(last);

  threads.reserve(num_threads);
  for (std::size_t tid = 0; tid < num_threads; ++tid) {
    threads.emplace_back([&barrier, &comp, num_threads, &partitions, tid] {
      {
        auto first = partitions.at(tid);
        auto last = partitions.at(tid + 1);
        std::sort(first, last, comp);
      }

      std::size_t sorted_distance{1};
      while (sorted_distance < num_threads) {
        barrier.arrive_and_wait();
        if (tid % (2 * sorted_distance) == 0) {
          auto first = partitions.at(tid);
          auto middle = partitions.at(std::min(tid + sorted_distance, num_threads));
          auto last = partitions.at(std::min(tid + 2 * sorted_distance, num_threads));
          std::inplace_merge(first, middle, last, comp);
        }
        sorted_distance *= 2;
      }
    });
  }

  for (auto& thread : threads) {
    thread.join();
  }
}

template <class RandomAccessIterator>
void parallel_sort(RandomAccessIterator first, RandomAccessIterator last) {
  parallel_sort(first, last, std::less{});
}

}  // namespace kigumi
