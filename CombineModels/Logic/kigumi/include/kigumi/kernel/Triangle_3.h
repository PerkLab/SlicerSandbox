#pragma once

#include <kigumi/kernel/Point_3.h>
#include <kigumi/kernel/Rational.h>
#include <kigumi/kernel/predicates.h>

#include <array>
#include <utility>

namespace kigumi {

class Triangle_3 {
 public:
  Triangle_3(Point_3 a, Point_3 b, Point_3 c)
      : vertices_{std::move(a), std::move(b), std::move(c)} {}

  const Point_3& vertex(int i) const { return vertices_.at(i % 3); }

  bool is_degenerate() const { return collinear(vertices_[0], vertices_[1], vertices_[2]); }

  Rational squared_area() const {
    auto a = vertices_[0].rational();
    auto b = vertices_[1].rational();
    auto c = vertices_[2].rational();
    std::array<Rational, 3> u{b[0] - a[0], b[1] - a[1], b[2] - a[2]};
    std::array<Rational, 3> v{c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    std::array<Rational, 3> n{u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                              u[0] * v[1] - u[1] * v[0]};
    return (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) / 4;
  }

  // Two triangles are equal if their vertices are equal up to a cyclic permutation.
  friend bool operator==(const Triangle_3& t, const Triangle_3& u) {
    for (int i = 0; i < 3; ++i) {
      if (t.vertex(0) == u.vertex(i) && t.vertex(1) == u.vertex(i + 1) &&
          t.vertex(2) == u.vertex(i + 2)) {
        return true;
      }
    }
    return false;
  }

  friend bool operator!=(const Triangle_3& t, const Triangle_3& u) { return !(t == u); }

 private:
  std::array<Point_3, 3> vertices_;
};

}  // namespace kigumi
