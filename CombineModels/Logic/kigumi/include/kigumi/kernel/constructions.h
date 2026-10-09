#pragma once

#include <kigumi/kernel/Point_3.h>
#include <kigumi/kernel/Rational.h>
#include <kigumi/kernel/predicates.h>

#include <array>
#include <stdexcept>
#include <utility>

namespace kigumi {

namespace internal {

// Constructions are written as function objects that are generic over the number type (Integer
// or Rational) and return the homogeneous coordinates (numerators, denominator) of a point.
//
// The degree of the numerators must exceed that of the denominator by exactly one, so that the
// result scales linearly under the power-of-two scaling performed by Integer_coordinates.

template <class F, class... Points>
Point_3 construct(const F& f, const Points&... ps) {
  if (all_double(ps...)) {
    Integer_coordinates to_int{ps...};
    auto [num, den] = f(to_int(ps)...);
    if (den == 0) {
      throw std::runtime_error("degenerate construction");
    }
    auto e = to_int.exponent();
    Integer scale{1};
    scale <<= e < 0 ? -e : e;
    if (e >= 0) {
      for (auto& x : num) {
        x *= scale;
      }
    } else {
      den *= scale;
    }
    return {Rational{num[0], den}, Rational{num[1], den}, Rational{num[2], den}};
  }

  auto [num, den] = f(ps.rational()...);
  if (den == 0) {
    throw std::runtime_error("degenerate construction");
  }
  return {num[0] / den, num[1] / den, num[2] / den};
}

// The intersection point of the coplanar lines ab and pq, which must intersect at a single point.
struct Line_line_intersection_poly {
  template <class T>
  std::pair<std::array<T, 3>, T> operator()(const std::array<T, 3>& a, const std::array<T, 3>& b,
                                            const std::array<T, 3>& p,
                                            const std::array<T, 3>& q) const {
    // a + s (b - a) = p + t (q - p)  =>  s = ((p - a) x v) . (u x v) / |u x v|^2
    T ux = b[0] - a[0];
    T uy = b[1] - a[1];
    T uz = b[2] - a[2];
    T vx = q[0] - p[0];
    T vy = q[1] - p[1];
    T vz = q[2] - p[2];
    T wx = p[0] - a[0];
    T wy = p[1] - a[1];
    T wz = p[2] - a[2];
    T uvx = uy * vz - uz * vy;
    T uvy = uz * vx - ux * vz;
    T uvz = ux * vy - uy * vx;
    T wvx = wy * vz - wz * vy;
    T wvy = wz * vx - wx * vz;
    T wvz = wx * vy - wy * vx;
    T den = uvx * uvx + uvy * uvy + uvz * uvz;
    T num = wvx * uvx + wvy * uvy + wvz * uvz;
    return {{a[0] * den + num * ux, a[1] * den + num * uy, a[2] * den + num * uz}, den};
  }
};

// The intersection point of the plane abc and the line pq, which must intersect at a single point.
struct Plane_line_intersection_poly {
  template <class T>
  std::pair<std::array<T, 3>, T> operator()(const std::array<T, 3>& a, const std::array<T, 3>& b,
                                            const std::array<T, 3>& c, const std::array<T, 3>& p,
                                            const std::array<T, 3>& q) const {
    // p + t (q - p), t = n . (a - p) / n . (q - p), n = (b - a) x (c - a)
    T bax = b[0] - a[0];
    T bay = b[1] - a[1];
    T baz = b[2] - a[2];
    T cax = c[0] - a[0];
    T cay = c[1] - a[1];
    T caz = c[2] - a[2];
    T nx = bay * caz - baz * cay;
    T ny = baz * cax - bax * caz;
    T nz = bax * cay - bay * cax;
    T vx = q[0] - p[0];
    T vy = q[1] - p[1];
    T vz = q[2] - p[2];
    T den = nx * vx + ny * vy + nz * vz;
    T num = nx * (a[0] - p[0]) + ny * (a[1] - p[1]) + nz * (a[2] - p[2]);
    return {{p[0] * den + num * vx, p[1] * den + num * vy, p[2] * den + num * vz}, den};
  }
};

struct Centroid_poly {
  template <class T>
  std::pair<std::array<T, 3>, T> operator()(const std::array<T, 3>& a, const std::array<T, 3>& b,
                                            const std::array<T, 3>& c) const {
    return {{a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]}, T{3}};
  }
};

}  // namespace internal

// The intersection point of the coplanar lines ab and pq, which must intersect at a single point.
inline Point_3 line_line_intersection(const Point_3& a, const Point_3& b, const Point_3& p,
                                      const Point_3& q) {
  return internal::construct(internal::Line_line_intersection_poly{}, a, b, p, q);
}

// The intersection point of the plane abc and the line pq, which must intersect at a single point.
inline Point_3 plane_line_intersection(const Point_3& a, const Point_3& b, const Point_3& c,
                                       const Point_3& p, const Point_3& q) {
  return internal::construct(internal::Plane_line_intersection_poly{}, a, b, c, p, q);
}

inline Point_3 centroid(const Point_3& a, const Point_3& b, const Point_3& c) {
  return internal::construct(internal::Centroid_poly{}, a, b, c);
}

}  // namespace kigumi
