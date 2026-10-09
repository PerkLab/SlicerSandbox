#pragma once

#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/kernel/Interval.h>
#include <kigumi/kernel/Point_3.h>

#include <algorithm>
#include <limits>
#include <utility>

namespace kigumi {

// The ray that starts at source() and passes through second_point().
class Ray_3 {
 public:
  Ray_3(Point_3 source, Point_3 second_point)
      : source_{std::move(source)}, second_point_{std::move(second_point)} {}

  const Point_3& source() const { return source_; }

  const Point_3& second_point() const { return second_point_; }

 private:
  Point_3 source_;
  Point_3 second_point_;
};

// Returns false only if the ray certainly does not intersect the box.
inline bool do_intersect(const Bbox_3& bbox, const Ray_3& ray) {
  // The ray is s + t d (t >= 0). The range of t inside the box is shrunk with slab tests, using
  // interval arithmetic to be conservative.
  auto t_min = 0.0;
  auto t_max = std::numeric_limits<double>::infinity();

  for (int i = 0; i < 3; ++i) {
    const auto& s = ray.source().approx()[i];
    auto d = ray.second_point().approx()[i] - s;

    if (d.inf() > 0.0 || d.sup() < 0.0) {
      auto t1 = (Interval{bbox.min(i)} - s) / d;
      auto t2 = (Interval{bbox.max(i)} - s) / d;
      const auto& t_enter = d.inf() > 0.0 ? t1 : t2;
      const auto& t_exit = d.inf() > 0.0 ? t2 : t1;
      t_min = std::max(t_min, t_enter.inf());
      t_max = std::min(t_max, t_exit.sup());
    } else if (d.inf() == 0.0 && d.sup() == 0.0) {
      // The ray is parallel to the slab.
      if (s.sup() < bbox.min(i) || s.inf() > bbox.max(i)) {
        return false;
      }
    }

    if (t_min > t_max) {
      return false;
    }
  }

  return true;
}

}  // namespace kigumi
