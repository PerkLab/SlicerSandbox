#pragma once

namespace kigumi {

enum Sign : int {
  NEGATIVE = -1,
  ZERO = 0,
  POSITIVE = 1,
};

using Orientation = Sign;
using Oriented_side = Sign;
using Comparison_result = Sign;

inline constexpr Sign CLOCKWISE = NEGATIVE;
inline constexpr Sign COUNTERCLOCKWISE = POSITIVE;
inline constexpr Sign COLLINEAR = ZERO;
inline constexpr Sign COPLANAR = ZERO;

inline constexpr Sign ON_NEGATIVE_SIDE = NEGATIVE;
inline constexpr Sign ON_ORIENTED_BOUNDARY = ZERO;
inline constexpr Sign ON_POSITIVE_SIDE = POSITIVE;

inline constexpr Sign SMALLER = NEGATIVE;
inline constexpr Sign EQUAL = ZERO;
inline constexpr Sign LARGER = POSITIVE;

// NOTE: Oriented_side and Bounded_side have opposite signs.
enum Bounded_side : int {
  ON_UNBOUNDED_SIDE = -1,
  ON_BOUNDARY = 0,
  ON_BOUNDED_SIDE = 1,
};

constexpr Sign operator-(Sign s) { return static_cast<Sign>(-static_cast<int>(s)); }

constexpr Sign operator*(Sign a, Sign b) {
  return static_cast<Sign>(static_cast<int>(a) * static_cast<int>(b));
}

template <class T>
constexpr Sign sign_of(const T& x) {
  return x > 0 ? POSITIVE : x < 0 ? NEGATIVE : ZERO;
}

}  // namespace kigumi
