#pragma once

#include <boost/unordered/unordered_flat_map.hpp>
#include <utility>
#include <vector>

namespace kigumi {

template <class K>
struct Point_3_hash {
  std::size_t operator()(const typename K::Point_3& p) const noexcept { return p.hash(); }
};

template <class K>
class Point_list {
  using Point = typename K::Point_3;

 public:
  const Point& at(std::size_t i) const { return points_.at(i); }

  auto begin() const { return points_.begin(); }

  auto end() const { return points_.end(); }

  std::size_t insert(const Point& p) { return insert(Point{p}); }

  // Replaces the point at index i. Must not be called during a uniqueness check.
  void set(std::size_t i, Point p) { points_.at(i) = std::move(p); }

  std::size_t insert(Point&& p) {
    if (!check_uniqueness_) {
      points_.push_back(std::move(p));
      return points_.size() - 1;
    }

    auto [it, inserted] = point_to_index_.emplace(p, points_.size());

    if (inserted) {
      points_.push_back(std::move(p));
    }

    return it->second;
  }

  std::vector<Point> take_points() { return std::move(points_); }

  void reserve(std::size_t capacity) {
    points_.reserve(capacity);
    if (!check_uniqueness_) {
      return;
    }

    point_to_index_.reserve(capacity);
  }

  std::size_t size() const { return points_.size(); }

  void start_uniqueness_check() { check_uniqueness_ = true; }

  void stop_uniqueness_check() {
    check_uniqueness_ = false;
    point_to_index_ = {};
  }

 private:
  std::vector<Point> points_;
  boost::unordered_flat_map<Point, std::size_t, Point_3_hash<K>> point_to_index_;
  bool check_uniqueness_{};
};

}  // namespace kigumi
