#pragma once

#include <kigumi/kernel/Interval.h>
#include <kigumi/kernel/Point_3.h>
#include <kigumi/kernel/Rational.h>
#include <kigumi/kernel/enum.h>

#include <algorithm>
#include <array>
#include <climits>
#include <cmath>
#include <cstdint>
#include <optional>

namespace kigumi {

namespace internal {

// Polynomials are written once as function objects that are generic over the number type
// (Interval, Integer, or Rational) and evaluated in stages by filtered_sign().
//
// All polynomials must be homogeneous in coordinate differences, so that the sign is invariant
// under the power-of-two scaling performed by Integer_coordinates.

// Converts the coordinates of double points to integers that share a common power-of-two scale.
class Integer_coordinates {
 public:
  template <class... Points>
  explicit Integer_coordinates(const Points&... ps) {
    (update_exponent(ps), ...);
    if (exponent_ == INT_MAX) {
      exponent_ = 0;
    }
  }

  // The common scale is 2^exponent().
  int exponent() const { return exponent_; }

  std::array<Integer, 3> operator()(const Point_3& p) const {
    const auto& a = p.approx();
    return {to_integer(a[0].inf()), to_integer(a[1].inf()), to_integer(a[2].inf())};
  }

 private:
  static constexpr int kMantissaDigits = 53;

  void update_exponent(const Point_3& p) {
    for (const auto& x : p.approx()) {
      if (x.inf() != 0.0) {
        int e{};
        std::frexp(x.inf(), &e);
        exponent_ = std::min(exponent_, e - kMantissaDigits);
      }
    }
  }

  Integer to_integer(double x) const {
    if (x == 0.0) {
      return 0;
    }
    int e{};
    auto f = std::frexp(x, &e);
    auto m = static_cast<std::int64_t>(std::ldexp(f, kMantissaDigits));
    Integer result{m < 0 ? -m : m};
    result <<= e - kMantissaDigits - exponent_;
    return m < 0 ? Integer{-result} : result;
  }

  int exponent_{INT_MAX};
};

template <class... Points>
bool all_double(const Points&... ps) {
  return (ps.is_double() && ...);
}

template <class F, class... Points>
Sign exact_sign(const F& f, const Points&... ps) {
  if (all_double(ps...)) {
    Integer_coordinates to_int{ps...};
    return sign_of(f(to_int(ps)...));
  }
  return sign_of(f(ps.rational()...));
}

template <class F, class... Points>
Sign filtered_sign(const F& f, const Points&... ps) {
  if (auto s = f(ps.approx()...).certain_sign()) {
    return *s;
  }
  return exact_sign(f, ps...);
}

// Coordinate differences must be zero or within [1 / max, max] for the static filters to be
// valid; this rules out underflow and overflow (and NaNs).
inline bool in_filter_range(double d, double max) {
  auto a = std::abs(d);
  return a == 0.0 || (a >= 1.0 / max && a <= max);
}

inline constexpr double kOrient2dMaxDiff = 0x1p450;
inline constexpr double kOrient3dMaxDiff = 0x1p300;
inline constexpr double kIncircleMaxDiff = 0x1p200;

// Error bounds from Shewchuk, "Adaptive Precision Floating-Point Arithmetic and Fast Robust
// Geometric Predicates" (1997).
inline constexpr double kEpsilon = 0x1p-53;
inline constexpr double kOrient2dErrorBound = (3.0 + 16.0 * kEpsilon) * kEpsilon;
inline constexpr double kOrient3dErrorBound = (7.0 + 56.0 * kEpsilon) * kEpsilon;
inline constexpr double kIncircleErrorBound = (10.0 + 96.0 * kEpsilon) * kEpsilon;

inline std::optional<Sign> static_sign(double det, double permanent, double error_bound) {
  if (permanent == 0.0) {
    // Every term is exactly zero.
    return ZERO;
  }
  if (std::abs(det) > error_bound * permanent) {
    return sign_of(det);
  }
  return std::nullopt;
}

struct Orientation_3_poly {
  // det[q - p, r - p, s - p]
  template <class T>
  T operator()(const std::array<T, 3>& p, const std::array<T, 3>& q, const std::array<T, 3>& r,
               const std::array<T, 3>& s) const {
    T ax = q[0] - p[0];
    T ay = q[1] - p[1];
    T az = q[2] - p[2];
    T bx = r[0] - p[0];
    T by = r[1] - p[1];
    T bz = r[2] - p[2];
    T cx = s[0] - p[0];
    T cy = s[1] - p[1];
    T cz = s[2] - p[2];
    T m1 = by * cz - bz * cy;
    T m2 = bz * cx - bx * cz;
    T m3 = bx * cy - by * cx;
    return ax * m1 + ay * m2 + az * m3;
  }

  static std::optional<Sign> static_filter(const Point_3& p, const Point_3& q, const Point_3& r,
                                           const Point_3& s) {
    const auto& pa = p.approx();
    const auto& qa = q.approx();
    const auto& ra = r.approx();
    const auto& sa = s.approx();
    std::array<double, 3> a{qa[0].inf() - pa[0].inf(), qa[1].inf() - pa[1].inf(),
                            qa[2].inf() - pa[2].inf()};
    std::array<double, 3> b{ra[0].inf() - pa[0].inf(), ra[1].inf() - pa[1].inf(),
                            ra[2].inf() - pa[2].inf()};
    std::array<double, 3> c{sa[0].inf() - pa[0].inf(), sa[1].inf() - pa[1].inf(),
                            sa[2].inf() - pa[2].inf()};
    for (std::size_t i = 0; i < 3; ++i) {
      if (!in_filter_range(a[i], kOrient3dMaxDiff) || !in_filter_range(b[i], kOrient3dMaxDiff) ||
          !in_filter_range(c[i], kOrient3dMaxDiff)) {
        return std::nullopt;
      }
    }
    auto bycz = b[1] * c[2];
    auto bzcy = b[2] * c[1];
    auto bzcx = b[2] * c[0];
    auto bxcz = b[0] * c[2];
    auto bxcy = b[0] * c[1];
    auto bycx = b[1] * c[0];
    auto det = a[0] * (bycz - bzcy) + a[1] * (bzcx - bxcz) + a[2] * (bxcy - bycx);
    auto permanent = std::abs(a[0]) * (std::abs(bycz) + std::abs(bzcy)) +
                     std::abs(a[1]) * (std::abs(bzcx) + std::abs(bxcz)) +
                     std::abs(a[2]) * (std::abs(bxcy) + std::abs(bycx));
    return static_sign(det, permanent, kOrient3dErrorBound);
  }
};

// The orientation of (p, q, r) projected onto the (i, j) coordinate plane.
struct Orientation_2_poly {
  int i;
  int j;

  // det[p - r, q - r]
  template <class T>
  T operator()(const std::array<T, 3>& p, const std::array<T, 3>& q,
               const std::array<T, 3>& r) const {
    T pi = p[i] - r[i];
    T pj = p[j] - r[j];
    T qi = q[i] - r[i];
    T qj = q[j] - r[j];
    return pi * qj - pj * qi;
  }

  std::optional<Sign> static_filter(const Point_3& p, const Point_3& q, const Point_3& r) const {
    auto pi = p.approx()[i].inf() - r.approx()[i].inf();
    auto pj = p.approx()[j].inf() - r.approx()[j].inf();
    auto qi = q.approx()[i].inf() - r.approx()[i].inf();
    auto qj = q.approx()[j].inf() - r.approx()[j].inf();
    if (!in_filter_range(pi, kOrient2dMaxDiff) || !in_filter_range(pj, kOrient2dMaxDiff) ||
        !in_filter_range(qi, kOrient2dMaxDiff) || !in_filter_range(qj, kOrient2dMaxDiff)) {
      return std::nullopt;
    }
    auto left = pi * qj;
    auto right = pj * qi;
    return static_sign(left - right, std::abs(left) + std::abs(right), kOrient2dErrorBound);
  }
};

// The side of s with respect to the circle through (p, q, r), projected onto the (i, j)
// coordinate plane. POSITIVE if s is inside the circle and (p, q, r) is counterclockwise.
struct Side_of_oriented_circle_2_poly {
  int i;
  int j;

  template <class T>
  T operator()(const std::array<T, 3>& p, const std::array<T, 3>& q, const std::array<T, 3>& r,
               const std::array<T, 3>& s) const {
    T adx = p[i] - s[i];
    T ady = p[j] - s[j];
    T bdx = q[i] - s[i];
    T bdy = q[j] - s[j];
    T cdx = r[i] - s[i];
    T cdy = r[j] - s[j];
    T alift = adx * adx + ady * ady;
    T blift = bdx * bdx + bdy * bdy;
    T clift = cdx * cdx + cdy * cdy;
    return alift * (bdx * cdy - cdx * bdy) + blift * (cdx * ady - adx * cdy) +
           clift * (adx * bdy - bdx * ady);
  }

  std::optional<Sign> static_filter(const Point_3& p, const Point_3& q, const Point_3& r,
                                    const Point_3& s) const {
    auto adx = p.approx()[i].inf() - s.approx()[i].inf();
    auto ady = p.approx()[j].inf() - s.approx()[j].inf();
    auto bdx = q.approx()[i].inf() - s.approx()[i].inf();
    auto bdy = q.approx()[j].inf() - s.approx()[j].inf();
    auto cdx = r.approx()[i].inf() - s.approx()[i].inf();
    auto cdy = r.approx()[j].inf() - s.approx()[j].inf();
    for (auto d : {adx, ady, bdx, bdy, cdx, cdy}) {
      if (!in_filter_range(d, kIncircleMaxDiff)) {
        return std::nullopt;
      }
    }
    auto bdxcdy = bdx * cdy;
    auto cdxbdy = cdx * bdy;
    auto cdxady = cdx * ady;
    auto adxcdy = adx * cdy;
    auto adxbdy = adx * bdy;
    auto bdxady = bdx * ady;
    auto alift = adx * adx + ady * ady;
    auto blift = bdx * bdx + bdy * bdy;
    auto clift = cdx * cdx + cdy * cdy;
    auto det = alift * (bdxcdy - cdxbdy) + blift * (cdxady - adxcdy) + clift * (adxbdy - bdxady);
    auto permanent = (std::abs(bdxcdy) + std::abs(cdxbdy)) * alift +
                     (std::abs(cdxady) + std::abs(adxcdy)) * blift +
                     (std::abs(adxbdy) + std::abs(bdxady)) * clift;
    return static_sign(det, permanent, kIncircleErrorBound);
  }
};

// Evaluates a polynomial that has a static filter for double inputs.
template <class F, class... Points>
Sign statically_filtered_sign(const F& f, const Points&... ps) {
  if (all_double(ps...)) {
    if (auto s = f.static_filter(ps...)) {
      return *s;
    }
    return exact_sign(f, ps...);
  }
  return filtered_sign(f, ps...);
}

}  // namespace internal

// Returns POSITIVE if s lies on the positive side of the oriented plane through p, q, and r.
inline Orientation orientation(const Point_3& p, const Point_3& q, const Point_3& r,
                               const Point_3& s) {
  return internal::statically_filtered_sign(internal::Orientation_3_poly{}, p, q, r, s);
}

// The orientation of (p, q, r) projected onto the (i, j) coordinate plane.
inline Orientation orientation_2(int i, int j, const Point_3& p, const Point_3& q,
                                 const Point_3& r) {
  return internal::statically_filtered_sign(internal::Orientation_2_poly{i, j}, p, q, r);
}

// POSITIVE if s is inside the circle through (p, q, r) projected onto the (i, j) coordinate plane
// and (p, q, r) is counterclockwise in that plane.
inline Oriented_side side_of_oriented_circle_2(int i, int j, const Point_3& p, const Point_3& q,
                                               const Point_3& r, const Point_3& s) {
  return internal::statically_filtered_sign(internal::Side_of_oriented_circle_2_poly{i, j}, p, q,
                                            r, s);
}

inline Comparison_result compare_coordinate(const Point_3& p, const Point_3& q, int i) {
  const auto& a = p.approx().at(i);
  const auto& b = q.approx().at(i);
  if (a.sup() < b.inf()) {
    return SMALLER;
  }
  if (a.inf() > b.sup()) {
    return LARGER;
  }
  if (a.is_point() && b.is_point()) {
    return EQUAL;
  }
  auto x = p.coord(i);
  auto y = q.coord(i);
  return x < y ? SMALLER : y < x ? LARGER : EQUAL;
}

inline Comparison_result compare_lexicographically(const Point_3& p, const Point_3& q) {
  for (int i = 0; i < 3; ++i) {
    auto c = compare_coordinate(p, q, i);
    if (c != EQUAL) {
      return c;
    }
  }
  return EQUAL;
}

// For coplanar points p, q, and r, returns COLLINEAR if they are collinear, and otherwise
// POSITIVE or NEGATIVE consistently for all triples of points in the same plane.
inline Orientation coplanar_orientation(const Point_3& p, const Point_3& q, const Point_3& r) {
  auto o = orientation_2(0, 1, p, q, r);
  if (o != COLLINEAR) {
    return o;
  }
  o = orientation_2(1, 2, p, q, r);
  if (o != COLLINEAR) {
    return o;
  }
  return orientation_2(0, 2, p, q, r);
}

inline bool collinear(const Point_3& p, const Point_3& q, const Point_3& r) {
  return orientation_2(0, 1, p, q, r) == COLLINEAR && orientation_2(1, 2, p, q, r) == COLLINEAR &&
         orientation_2(0, 2, p, q, r) == COLLINEAR;
}

// The exact value of det[q - p, r - p, s - p].
inline Rational orientation_determinant(const Point_3& p, const Point_3& q, const Point_3& r,
                                        const Point_3& s) {
  return internal::Orientation_3_poly{}(p.rational(), q.rational(), r.rational(), s.rational());
}

}  // namespace kigumi
