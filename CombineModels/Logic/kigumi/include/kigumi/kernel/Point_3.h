#pragma once

#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/kernel/Interval.h>
#include <kigumi/kernel/Rational.h>

#include <array>
#include <boost/container_hash/hash.hpp>
#include <memory>

namespace kigumi {

// An immutable point with exact rational coordinates.
//
// Points whose coordinates are all representable as doubles (e.g., input points) store only the
// doubles. Other points (e.g., intersection points) additionally store the exact rational
// coordinates, which are shared between copies. The representation is canonical: equal points
// always have the same representation, and the enclosing intervals are a function of the exact
// coordinates.
class Point_3 {
 public:
  Point_3() : Point_3{0.0, 0.0, 0.0} {}

  Point_3(double x, double y, double z) : approx_{Interval{x}, Interval{y}, Interval{z}} {}

  Point_3(const Rational& x, const Rational& y, const Rational& z)
      : approx_{enclose(x), enclose(y), enclose(z)} {
    if (!approx_[0].is_point() || !approx_[1].is_point() || !approx_[2].is_point()) {
      exact_ = std::make_shared<const std::array<Rational, 3>>(std::array<Rational, 3>{x, y, z});
    }
  }

  // Returns true if all coordinates are exactly representable as doubles.
  bool is_double() const { return !exact_; }

  // Intervals that contain the exact coordinates.
  const std::array<Interval, 3>& approx() const { return approx_; }

  Rational x() const { return coord(0); }

  Rational y() const { return coord(1); }

  Rational z() const { return coord(2); }

  Rational coord(int i) const {
    return exact_ ? exact_->at(i) : Rational{approx_.at(i).inf()};
  }

  std::array<Rational, 3> rational() const {
    if (exact_) {
      return *exact_;
    }
    return {Rational{approx_[0].inf()}, Rational{approx_[1].inf()}, Rational{approx_[2].inf()}};
  }

  // The coordinates rounded to the nearest doubles.
  std::array<double, 3> to_double() const {
    if (exact_) {
      return {kigumi::to_double((*exact_)[0]), kigumi::to_double((*exact_)[1]),
              kigumi::to_double((*exact_)[2])};
    }
    return {approx_[0].inf(), approx_[1].inf(), approx_[2].inf()};
  }

  Bbox_3 bbox() const {
    return {approx_[0].inf(), approx_[1].inf(), approx_[2].inf(),
            approx_[0].sup(), approx_[1].sup(), approx_[2].sup()};
  }

  std::size_t hash() const {
    std::size_t seed{};
    for (const auto& x : approx_) {
      // Normalize -0.0 to 0.0.
      boost::hash_combine(seed, x.inf() == 0.0 ? 0.0 : x.inf());
    }
    return seed;
  }

  friend bool operator==(const Point_3& a, const Point_3& b) {
    for (std::size_t i = 0; i < 3; ++i) {
      if (a.approx_[i].inf() != b.approx_[i].inf() || a.approx_[i].sup() != b.approx_[i].sup()) {
        return false;
      }
    }
    if (a.exact_ == b.exact_) {
      // Both are doubles, or they share the coordinates.
      return true;
    }
    if (!a.exact_ || !b.exact_) {
      return false;
    }
    return *a.exact_ == *b.exact_;
  }

  friend bool operator!=(const Point_3& a, const Point_3& b) { return !(a == b); }

 private:
  std::array<Interval, 3> approx_;
  std::shared_ptr<const std::array<Rational, 3>> exact_;
};

}  // namespace kigumi
