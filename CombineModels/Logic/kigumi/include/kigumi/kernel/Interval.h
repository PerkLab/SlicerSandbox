#pragma once

#include <kigumi/kernel/enum.h>

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>

namespace kigumi {

namespace internal {

// The next representable double toward +infinity (NaN and +infinity are returned as is).
inline double next_up(double x) {
  if (std::isnan(x) || x == std::numeric_limits<double>::infinity()) {
    return x;
  }
  if (x == 0.0) {
    return std::numeric_limits<double>::denorm_min();
  }
  auto bits = std::bit_cast<std::uint64_t>(x);
  bits = x > 0.0 ? bits + 1 : bits - 1;
  return std::bit_cast<double>(bits);
}

// The next representable double toward -infinity (NaN and -infinity are returned as is).
inline double next_down(double x) { return -next_up(-x); }

}  // namespace internal

// A closed interval of doubles that is guaranteed to contain the exact result of a computation.
//
// Each operation is performed in the default rounding mode (round to nearest), and the result is
// widened outward by one ulp. Since the rounding error of a single operation is at most half an
// ulp, this yields a rigorous enclosure without switching the rounding mode. Overflow produces
// infinities or NaNs, which make the sign uncertain.
class Interval {
 public:
  Interval() = default;

  // NOLINTNEXTLINE(google-explicit-constructor)
  Interval(double x) : lo_{x}, hi_{x} {}

  Interval(double lo, double hi) : lo_{lo}, hi_{hi} {}

  double inf() const { return lo_; }

  double sup() const { return hi_; }

  bool is_point() const { return lo_ == hi_; }

  // Returns the sign if it is certain.
  std::optional<Sign> certain_sign() const {
    if (lo_ > 0.0) {
      return POSITIVE;
    }
    if (hi_ < 0.0) {
      return NEGATIVE;
    }
    if (lo_ == 0.0 && hi_ == 0.0) {
      return ZERO;
    }
    return std::nullopt;
  }

  friend Interval operator-(const Interval& a) { return {-a.hi_, -a.lo_}; }

  friend Interval operator+(const Interval& a, const Interval& b) {
    return {internal::next_down(a.lo_ + b.lo_), internal::next_up(a.hi_ + b.hi_)};
  }

  friend Interval operator-(const Interval& a, const Interval& b) {
    return {internal::next_down(a.lo_ - b.hi_), internal::next_up(a.hi_ - b.lo_)};
  }

  friend Interval operator*(const Interval& a, const Interval& b) {
    if (a.is_point() && b.is_point()) {
      auto p = a.lo_ * b.lo_;
      return {internal::next_down(p), internal::next_up(p)};
    }
    auto p1 = a.lo_ * b.lo_;
    auto p2 = a.lo_ * b.hi_;
    auto p3 = a.hi_ * b.lo_;
    auto p4 = a.hi_ * b.hi_;
    return {internal::next_down(std::min({p1, p2, p3, p4})),
            internal::next_up(std::max({p1, p2, p3, p4}))};
  }

  // The result is (-infinity, +infinity) if b contains zero.
  friend Interval operator/(const Interval& a, const Interval& b) {
    if (!(b.lo_ > 0.0 || b.hi_ < 0.0)) {
      constexpr auto kInf = std::numeric_limits<double>::infinity();
      return {-kInf, kInf};
    }
    auto q1 = a.lo_ / b.lo_;
    auto q2 = a.lo_ / b.hi_;
    auto q3 = a.hi_ / b.lo_;
    auto q4 = a.hi_ / b.hi_;
    return {internal::next_down(std::min({q1, q2, q3, q4})),
            internal::next_up(std::max({q1, q2, q3, q4}))};
  }

  Interval& operator+=(const Interval& other) { return *this = *this + other; }

  Interval& operator-=(const Interval& other) { return *this = *this - other; }

  Interval& operator*=(const Interval& other) { return *this = *this * other; }

 private:
  double lo_{};
  double hi_{};
};

}  // namespace kigumi
