#pragma once

#include <kigumi/kernel/Interval.h>

#include <boost/multiprecision/cpp_int.hpp>
#include <limits>

namespace kigumi {

// Expression templates are disabled so that `auto` and generic code always hold values.
using Integer = boost::multiprecision::number<boost::multiprecision::cpp_int_backend<>,
                                              boost::multiprecision::et_off>;
using Rational = boost::multiprecision::number<boost::multiprecision::cpp_rational_backend,
                                               boost::multiprecision::et_off>;

inline double to_double(double x) { return x; }

inline double to_double(const Rational& x) { return x.convert_to<double>(); }

// Returns the tightest interval of doubles that contains x.
inline Interval enclose(const Rational& x) {
  constexpr auto kInf = std::numeric_limits<double>::infinity();
  constexpr auto kMax = std::numeric_limits<double>::max();

  auto d = to_double(x);
  if (d > kMax) {
    return {kMax, kInf};
  }
  if (d < -kMax) {
    return {-kInf, -kMax};
  }

  auto lo = d;
  auto hi = d;
  while (lo > -kMax && Rational{lo} > x) {
    lo = internal::next_down(lo);
  }
  while (hi < kMax && Rational{hi} < x) {
    hi = internal::next_up(hi);
  }
  return {lo, hi};
}

}  // namespace kigumi
