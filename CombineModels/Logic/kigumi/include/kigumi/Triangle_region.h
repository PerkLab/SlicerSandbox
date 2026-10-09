#pragma once

#include <cstdint>
#include <stdexcept>
#include <tuple>

namespace kigumi {

enum class Triangle_region : std::uint8_t {
  LEFT_VERTEX_0 = 1,
  LEFT_VERTEX_1 = 2,
  LEFT_VERTEX_2 = 4,
  LEFT_EDGE_01 = LEFT_VERTEX_0 | LEFT_VERTEX_1,
  LEFT_EDGE_12 = LEFT_VERTEX_1 | LEFT_VERTEX_2,
  LEFT_EDGE_20 = LEFT_VERTEX_2 | LEFT_VERTEX_0,
  LEFT_FACE = LEFT_VERTEX_0 | LEFT_VERTEX_1 | LEFT_VERTEX_2,
  RIGHT_VERTEX_0 = 8,
  RIGHT_VERTEX_1 = 16,
  RIGHT_VERTEX_2 = 32,
  RIGHT_EDGE_01 = RIGHT_VERTEX_0 | RIGHT_VERTEX_1,
  RIGHT_EDGE_12 = RIGHT_VERTEX_1 | RIGHT_VERTEX_2,
  RIGHT_EDGE_20 = RIGHT_VERTEX_2 | RIGHT_VERTEX_0,
  RIGHT_FACE = RIGHT_VERTEX_0 | RIGHT_VERTEX_1 | RIGHT_VERTEX_2,
};

constexpr Triangle_region convex_hull(Triangle_region r1, Triangle_region r2) {
  return static_cast<Triangle_region>(static_cast<std::uint8_t>(r1) |
                                      static_cast<std::uint8_t>(r2));
}

constexpr Triangle_region intersection(Triangle_region r1, Triangle_region r2) {
  return static_cast<Triangle_region>(static_cast<std::uint8_t>(r1) &
                                      static_cast<std::uint8_t>(r2));
}

inline std::tuple<Triangle_region, Triangle_region> edge_vertices(Triangle_region edge) {
  switch (edge) {
    case Triangle_region::LEFT_EDGE_01:
      return {Triangle_region::LEFT_VERTEX_0, Triangle_region::LEFT_VERTEX_1};
    case Triangle_region::LEFT_EDGE_12:
      return {Triangle_region::LEFT_VERTEX_1, Triangle_region::LEFT_VERTEX_2};
    case Triangle_region::LEFT_EDGE_20:
      return {Triangle_region::LEFT_VERTEX_2, Triangle_region::LEFT_VERTEX_0};
    case Triangle_region::RIGHT_EDGE_01:
      return {Triangle_region::RIGHT_VERTEX_0, Triangle_region::RIGHT_VERTEX_1};
    case Triangle_region::RIGHT_EDGE_12:
      return {Triangle_region::RIGHT_VERTEX_1, Triangle_region::RIGHT_VERTEX_2};
    case Triangle_region::RIGHT_EDGE_20:
      return {Triangle_region::RIGHT_VERTEX_2, Triangle_region::RIGHT_VERTEX_0};
    default:
      throw std::invalid_argument("the region must be an edge");
  }
}

inline std::tuple<Triangle_region, Triangle_region, Triangle_region> face_edges(
    Triangle_region face) {
  switch (face) {
    case Triangle_region::LEFT_FACE:
      return {Triangle_region::LEFT_EDGE_01, Triangle_region::LEFT_EDGE_12,
              Triangle_region::LEFT_EDGE_20};
    case Triangle_region::RIGHT_FACE:
      return {Triangle_region::RIGHT_EDGE_01, Triangle_region::RIGHT_EDGE_12,
              Triangle_region::RIGHT_EDGE_20};
    default:
      throw std::invalid_argument("the region must be a face");
  }
}

inline std::tuple<Triangle_region, Triangle_region, Triangle_region> face_vertices(
    Triangle_region face) {
  switch (face) {
    case Triangle_region::LEFT_FACE:
      return {Triangle_region::LEFT_VERTEX_0, Triangle_region::LEFT_VERTEX_1,
              Triangle_region::LEFT_VERTEX_2};
    case Triangle_region::RIGHT_FACE:
      return {Triangle_region::RIGHT_VERTEX_0, Triangle_region::RIGHT_VERTEX_1,
              Triangle_region::RIGHT_VERTEX_2};
    default:
      throw std::invalid_argument("the region must be a face");
  }
}

inline int dimension(Triangle_region region) {
  switch (region) {
    case Triangle_region::LEFT_VERTEX_0:
    case Triangle_region::LEFT_VERTEX_1:
    case Triangle_region::LEFT_VERTEX_2:
    case Triangle_region::RIGHT_VERTEX_0:
    case Triangle_region::RIGHT_VERTEX_1:
    case Triangle_region::RIGHT_VERTEX_2:
      return 0;
    case Triangle_region::LEFT_EDGE_01:
    case Triangle_region::LEFT_EDGE_12:
    case Triangle_region::LEFT_EDGE_20:
    case Triangle_region::RIGHT_EDGE_01:
    case Triangle_region::RIGHT_EDGE_12:
    case Triangle_region::RIGHT_EDGE_20:
      return 1;
    case Triangle_region::LEFT_FACE:
    case Triangle_region::RIGHT_FACE:
      return 2;
    default:
      throw std::invalid_argument("the region must be a simplex");
  }
}

inline bool is_left_region(Triangle_region region) {
  return convex_hull(region, Triangle_region::LEFT_FACE) == Triangle_region::LEFT_FACE;
}

}  // namespace kigumi
