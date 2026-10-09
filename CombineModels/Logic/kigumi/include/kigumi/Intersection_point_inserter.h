#pragma once

#include <kigumi/Point_list.h>
#include <kigumi/Triangle_region.h>
#include <kigumi/kernel/constructions.h>
#include <kigumi/parallel_do.h>

#include <array>
#include <boost/container_hash/hash.hpp>
#include <boost/unordered/unordered_flat_map.hpp>
#include <limits>
#include <tuple>
#include <utility>
#include <vector>

namespace kigumi {

template <class K>
class Intersection_point_inserter {
  using Line_line_intersection_key = std::array<std::size_t, 4>;
  using Plane_line_intersection_key = std::array<std::size_t, 5>;
  using Point = typename K::Point_3;
  using Point_list = kigumi::Point_list<K>;

 public:
  explicit Intersection_point_inserter(Point_list& points) : points_(points) {}

  // Returns the index of the intersection point. New points are not constructed until
  // construct_pending_points() is called.
  std::size_t insert(Triangle_region left_region, std::size_t a, std::size_t b, std::size_t c,
                     Triangle_region right_region, std::size_t p, std::size_t q, std::size_t r) {
    if (left_region == Triangle_region::LEFT_VERTEX_0) {
      return a;
    }
    if (left_region == Triangle_region::LEFT_VERTEX_1) {
      return b;
    }
    if (left_region == Triangle_region::LEFT_VERTEX_2) {
      return c;
    }
    if (right_region == Triangle_region::RIGHT_VERTEX_0) {
      return p;
    }
    if (right_region == Triangle_region::RIGHT_VERTEX_1) {
      return q;
    }
    if (right_region == Triangle_region::RIGHT_VERTEX_2) {
      return r;
    }

    if (left_region == Triangle_region::LEFT_EDGE_12) {
      std::tie(a, b, c) = std::make_tuple(b, c, a);
    } else if (left_region == Triangle_region::LEFT_EDGE_20) {
      std::tie(a, b, c) = std::make_tuple(c, a, b);
    }
    if (right_region == Triangle_region::RIGHT_EDGE_12) {
      std::tie(p, q, r) = std::make_tuple(q, r, p);
    } else if (right_region == Triangle_region::RIGHT_EDGE_20) {
      std::tie(p, q, r) = std::make_tuple(r, p, q);
    }

    if (left_region == Triangle_region::LEFT_FACE) {
      return insert_plane_line_intersection(a, b, c, p, q);
    }
    if (right_region == Triangle_region::RIGHT_FACE) {
      return insert_plane_line_intersection(p, q, r, a, b);
    }
    return insert_line_line_intersection(a, b, p, q);
  }

  // Constructs the points that were inserted since the last call, in parallel.
  void construct_pending_points() {
    parallel_do(pending_.begin(), pending_.end(), [&](const Pending_point& pending) {
      const auto& ids = pending.ids;
      if (ids[4] == kNone) {
        points_.set(pending.id, line_line_intersection(points_.at(ids[0]), points_.at(ids[1]),
                                                       points_.at(ids[2]), points_.at(ids[3])));
      } else {
        points_.set(pending.id,
                    plane_line_intersection(points_.at(ids[0]), points_.at(ids[1]),
                                            points_.at(ids[2]), points_.at(ids[3]),
                                            points_.at(ids[4])));
      }
    });
    pending_.clear();
  }

 private:
  std::size_t insert_line_line_intersection(std::size_t a, std::size_t b, std::size_t p,
                                            std::size_t q) {
    if (a > b) {
      std::swap(a, b);
    }
    if (p > q) {
      std::swap(p, q);
    }
    if (a > p) {
      std::swap(a, p);
      std::swap(b, q);
    }

    Line_line_intersection_key key{a, b, p, q};
    auto [it, inserted] =
        line_line_intersection_cache_.emplace(key, std::numeric_limits<std::size_t>::max());

    if (inserted) {
      auto id = points_.insert(Point{});
      pending_.push_back({id, {a, b, p, q, kNone}});
      it->second = id;
    }

    return it->second;
  }

  std::size_t insert_plane_line_intersection(std::size_t a, std::size_t b, std::size_t c,
                                             std::size_t p, std::size_t q) {
    if (a > b) {
      std::swap(a, b);
    }
    if (a > c) {
      std::swap(a, c);
    }
    if (b > c) {
      std::swap(b, c);
    }
    if (p > q) {
      std::swap(p, q);
    }

    Plane_line_intersection_key key{a, b, c, p, q};
    auto [it, inserted] =
        plane_line_intersection_cache_.emplace(key, std::numeric_limits<std::size_t>::max());

    if (inserted) {
      auto id = points_.insert(Point{});
      pending_.push_back({id, {a, b, c, p, q}});
      it->second = id;
    }

    return it->second;
  }

  static constexpr std::size_t kNone = std::numeric_limits<std::size_t>::max();

  struct Pending_point {
    std::size_t id;
    // Line-line intersection (a, b, p, q, kNone) or plane-line intersection (a, b, c, p, q).
    std::array<std::size_t, 5> ids;
  };

  Point_list& points_;
  std::vector<Pending_point> pending_;
  boost::unordered_flat_map<Line_line_intersection_key, std::size_t,
                            boost::hash<Line_line_intersection_key>>
      line_line_intersection_cache_;
  boost::unordered_flat_map<Plane_line_intersection_key, std::size_t,
                            boost::hash<Plane_line_intersection_key>>
      plane_line_intersection_cache_;
};

}  // namespace kigumi
