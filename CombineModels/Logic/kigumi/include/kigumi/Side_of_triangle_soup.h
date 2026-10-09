#pragma once

#include <kigumi/Mesh_indices.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/kernel/enum.h>
#include <kigumi/kernel/predicates.h>
#include <kigumi/mesh_utility.h>

#include <algorithm>
#include <iterator>
#include <stdexcept>
#include <vector>

namespace kigumi {

template <class K, class FaceData>
class Side_of_triangle_soup {
  using FT = typename K::FT;
  using Leaf = typename kigumi::Triangle_soup<K, FaceData>::Leaf;
  using Point = typename K::Point_3;
  using Ray = typename K::Ray_3;
  using Triangle_soup = kigumi::Triangle_soup<K, FaceData>;

 public:
  Oriented_side operator()(const Triangle_soup& soup, const Point& p) const {
    if (soup.num_faces() == 0) {
      throw std::runtime_error("triangle soup must not be empty");
    }

    const auto& tree = soup.aabb_tree();

    for (auto fi_trg : soup.faces()) {
      leaves_.clear();
      intersections_.clear();

      auto p_trg = internal::face_centroid(soup, fi_trg);

      if (p == p_trg) {
        return ON_ORIENTED_BOUNDARY;
      }

      Ray ray{p, p_trg};
      tree.get_intersecting_leaves(std::back_inserter(leaves_), ray);

      auto degenerate = false;
      for (const auto* leaf : leaves_) {
        auto fi = leaf->face_index();
        const auto& f = soup.face(fi);
        const auto& a = soup.point(f[0]);
        const auto& b = soup.point(f[1]);
        const auto& c = soup.point(f[2]);

        auto o_src = orientation(a, b, c, p);
        auto o_trg = orientation(a, b, c, p_trg);

        if (o_src == ZERO) {
          if (contains_coplanar_point(a, b, c, p)) {
            return ON_ORIENTED_BOUNDARY;
          }
          if (o_trg == ZERO) {
            // The ray lies in the plane of the triangle and might touch it.
            degenerate = true;
          }
          continue;
        }

        if (!pierces(p, p_trg, a, b, c)) {
          continue;
        }

        // The line through the ray pierces the closed triangle. Compute the parameter t of the
        // intersection point p + t (p_trg - p), which is positive if the ray hits the triangle.
        auto d_src = orientation_determinant(a, b, c, p);
        auto d_trg = orientation_determinant(a, b, c, p_trg);
        auto denom = d_src - d_trg;
        if (denom == 0) {
          // The ray is parallel to the plane.
          continue;
        }
        FT t = d_src / denom;
        if (t <= 0) {
          continue;
        }
        intersections_.push_back({std::move(t), fi, pierces_interior(p, p_trg, a, b, c)});
      }

      if (degenerate) {
        continue;
      }

      if (intersections_.empty()) {
        // The point is outside the convex boundary of the mesh, etc.
        throw std::runtime_error("cannot determine the side of the point");
      }

      auto nearest = std::min_element(
          intersections_.begin(), intersections_.end(),
          [](const auto& x, const auto& y) { return x.distance < y.distance; });
      if (!nearest->interior) {
        // The ray touches or passes through an edge or a vertex.
        continue;
      }
      auto num_nearest =
          std::count_if(intersections_.begin(), intersections_.end(),
                        [&](const auto& x) { return x.distance == nearest->distance; });
      if (num_nearest >= 2) {
        // The ray passes through overlapping triangles.
        continue;
      }

      return internal::oriented_side_of_face_supporting_plane(soup, nearest->fi, p);
    }

    // Should not happen.
    throw std::runtime_error("cannot determine the side of the point");
  }

 private:
  struct Intersection {
    // The parameter along the ray, which is proportional to the distance.
    FT distance;
    Face_index fi;
    bool interior;
  };

  // Whether the line st intersects the closed triangle abc, which is not coplanar with st.
  static bool pierces(const Point& s, const Point& t, const Point& a, const Point& b,
                      const Point& c) {
    auto o1 = orientation(s, t, a, b);
    auto o2 = orientation(s, t, b, c);
    auto o3 = orientation(s, t, c, a);
    return (o1 >= 0 && o2 >= 0 && o3 >= 0) || (o1 <= 0 && o2 <= 0 && o3 <= 0);
  }

  // Whether the line st intersects the interior of the triangle abc.
  static bool pierces_interior(const Point& s, const Point& t, const Point& a, const Point& b,
                               const Point& c) {
    auto o1 = orientation(s, t, a, b);
    auto o2 = orientation(s, t, b, c);
    auto o3 = orientation(s, t, c, a);
    return o1 != ZERO && o1 == o2 && o2 == o3;
  }

  // Whether the closed triangle abc contains p, which is coplanar with the triangle.
  static bool contains_coplanar_point(const Point& a, const Point& b, const Point& c,
                                      const Point& p) {
    auto o = coplanar_orientation(a, b, c);
    return coplanar_orientation(a, b, p) != -o && coplanar_orientation(b, c, p) != -o &&
           coplanar_orientation(c, a, p) != -o;
  }

  mutable std::vector<const Leaf*> leaves_;
  mutable std::vector<Intersection> intersections_;
};

}  // namespace kigumi
