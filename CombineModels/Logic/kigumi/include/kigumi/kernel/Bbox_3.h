#pragma once

#include <algorithm>
#include <array>
#include <limits>

namespace kigumi {

class Bbox_3 {
 public:
  // Constructs an empty bounding box.
  Bbox_3() = default;

  Bbox_3(double xmin, double ymin, double zmin, double xmax, double ymax, double zmax)
      : min_{xmin, ymin, zmin}, max_{xmax, ymax, zmax} {}

  double xmin() const { return min_[0]; }

  double ymin() const { return min_[1]; }

  double zmin() const { return min_[2]; }

  double xmax() const { return max_[0]; }

  double ymax() const { return max_[1]; }

  double zmax() const { return max_[2]; }

  double min(int i) const { return min_.at(i); }

  double max(int i) const { return max_.at(i); }

  Bbox_3& operator+=(const Bbox_3& other) {
    for (std::size_t i = 0; i < 3; ++i) {
      min_[i] = std::min(min_[i], other.min_[i]);
      max_[i] = std::max(max_[i], other.max_[i]);
    }
    return *this;
  }

  friend Bbox_3 operator+(Bbox_3 a, const Bbox_3& b) { return a += b; }

 private:
  static constexpr auto kInf = std::numeric_limits<double>::infinity();

  std::array<double, 3> min_{kInf, kInf, kInf};
  std::array<double, 3> max_{-kInf, -kInf, -kInf};
};

inline bool do_intersect(const Bbox_3& a, const Bbox_3& b) {
  for (int i = 0; i < 3; ++i) {
    if (a.max(i) < b.min(i) || b.max(i) < a.min(i)) {
      return false;
    }
  }
  return true;
}

}  // namespace kigumi
