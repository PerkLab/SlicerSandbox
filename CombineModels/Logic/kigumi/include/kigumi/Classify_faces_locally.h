#pragma once

#include <kigumi/Face_tag.h>
#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Mixed.h>
#include <kigumi/Propagate_face_tags.h>
#include <kigumi/Warnings.h>
#include <kigumi/kernel/enum.h>
#include <kigumi/kernel/predicates.h>

#include <algorithm>
#include <array>
#include <stdexcept>
#include <utility>
#include <vector>

namespace kigumi {

template <class K, class FaceData>
class Classify_faces_locally {
  using Point = typename K::Point_3;
  using Propagate_face_tags = kigumi::Propagate_face_tags<K, FaceData>;

 public:
  Warnings operator()(Mixed_triangle_mesh<K, FaceData>& m, const Edge& edge,
                      const Edge_set& border_edges) const {
    bool found_untagged_face{};
    for (auto fi : m.faces_around_edge(edge)) {
      if (m.data(fi).tag == Face_tag::UNKNOWN) {
        found_untagged_face = true;
        break;
      }
    }
    if (!found_untagged_face) {
      return {};
    }

    const auto& p = m.point(edge[0]);
    const auto& q = m.point(edge[1]);
    Radial_frame frame{p, q};

    faces_.clear();
    for (auto fi : m.faces_around_edge(edge)) {
      // The face is either pqr or qpr.
      const auto& f = m.face(fi);

      std::size_t i{};  // The index of the vertex p.
      std::size_t j{};  // The index of the vertex q.
      while (f.at(i) != edge[0]) {
        ++i;
      }
      while (f.at(j) != edge[1]) {
        ++j;
      }

      std::size_t k{3 - (i + j)};  // The index of the vertex r.
      const auto& r = m.point(f.at(k));

      auto orientation = j == (i + 1) % 3 ? COUNTERCLOCKWISE  // The face is pqr.
                                          : CLOCKWISE;        // The face is qpr.

      faces_.emplace_back(fi, f.at(k), &r, frame.radial_bin(r), orientation);
    }

    // Sort the faces radially around the edge.

    std::sort(faces_.begin(), faces_.end(), Radial_ordering{&p, &q});

    // Tag coplanar/opposite faces first.

    for (std::size_t i = 0; i < faces_.size(); ++i) {
      auto j = (i + 1) % faces_.size();
      const auto& f = faces_.at(i);
      auto& f_data = m.data(f.fi);
      const auto& g = faces_.at(j);
      auto& g_data = m.data(g.fi);

      if (f.vi_r == g.vi_r) {
        auto tag = f.orientation == g.orientation ? Face_tag::COPLANAR : Face_tag::OPPOSITE;
        f_data.tag = tag;
        g_data.tag = tag;
      }
    }

    // Find pairs of non-overlapping and non-orientable faces and tag them.

    auto is_undefined_configuration = true;
    // At the end of the loop, the kth face is tagged as either interior or exterior.
    std::size_t k{};
    for (std::size_t i = 0; i < faces_.size(); ++i) {
      auto j = (i + 1) % faces_.size();
      const auto& f = faces_.at(i);
      auto& f_data = m.data(f.fi);
      const auto& g = faces_.at(j);
      auto& g_data = m.data(g.fi);

      if (f_data.tag == Face_tag::COPLANAR || f_data.tag == Face_tag::OPPOSITE ||
          g_data.tag == Face_tag::COPLANAR || g_data.tag == Face_tag::OPPOSITE) {
        continue;
      }

      // Neither f nor g is overlapping with adjacent faces.

      if (f.orientation == g.orientation) {
        if (f.orientation == COUNTERCLOCKWISE) {
          f_data.tag = Face_tag::INTERIOR;
          g_data.tag = Face_tag::EXTERIOR;
        } else {
          f_data.tag = Face_tag::EXTERIOR;
          g_data.tag = Face_tag::INTERIOR;
        }
        is_undefined_configuration = false;
        k = j;
      }
    }

    if (!is_undefined_configuration) {
      // Check consistency and tag rest of the faces.

      // An example case of an inconsistent configuration:
      //
      //                 Right, Int.
      //                    //|
      //                    //|
      //                    //|
      //             /////////|/////////
      //   Left, ??? ---------+--------- Left, Ext.
      //          :
      //   Should be tagged as interior according to global classification.

      auto consistent = true;
      for (auto dry_run : {true, false}) {
        auto tag = m.data(faces_.at(k).fi).tag;
        auto orientation = faces_.at(k).orientation;
        // Go around and return to the starting point to check consistency.
        for (std::size_t i = k + 1; i <= k + faces_.size(); ++i) {
          const auto& f = faces_.at(i % faces_.size());
          auto& f_data = m.data(f.fi);

          if (f.orientation == orientation) {
            tag = tag == Face_tag::EXTERIOR ? Face_tag::INTERIOR : Face_tag::EXTERIOR;
          }
          orientation = f.orientation;

          if (f_data.tag == Face_tag::UNKNOWN) {
            if (!dry_run) {
              f_data.tag = tag;
            }
          } else if ((f_data.tag == Face_tag::EXTERIOR || f_data.tag == Face_tag::INTERIOR) &&
                     f_data.tag != tag) {
            consistent = false;
            break;
          }
        }

        if (!consistent) {
          // Leave unknown faces to the global classifier.
          break;
        }
      }
    }

    // Propagate the tags.

    Warnings warnings{};

    for (const auto& f : faces_) {
      const auto& f_data = m.data(f.fi);
      if (f_data.tag != Face_tag::UNKNOWN) {
        warnings |= propagate_face_tags_(m, border_edges, f.fi);
      }
    }

    return warnings;
  }

 private:
  // The orthogonal frame (u, v, n) with n = q - p, in which faces around the edge pq are sorted.
  //
  // u is orthogonal to n and avoids the smallest component of n, and v = n x u.
  class Radial_frame {
   public:
    Radial_frame(const Point& p, const Point& q) : p_{&p}, q_{&q} {
      std::array<Rational, 3> n{q.x() - p.x(), q.y() - p.y(), q.z() - p.z()};
      if (n[0] == 0) {
        kind_ = Kind::X;
      } else if (n[1] == 0) {
        kind_ = Kind::Y;
      } else if (n[2] == 0) {
        kind_ = Kind::Z;
      } else {
        auto a = abs(n[0]);
        auto b = abs(n[1]);
        auto c = abs(n[2]);
        if (a <= b && a <= c) {
          kind_ = Kind::ZERO_X;
        } else if (b <= a && b <= c) {
          kind_ = Kind::ZERO_Y;
        } else {
          kind_ = Kind::ZERO_Z;
        }
      }
    }

    // Classifies the direction of r - p in the (u, v) plane into eight bins in counterclockwise
    // order, starting from +u.
    int radial_bin(const Point& r) const {
      auto u = internal::filtered_sign(Coordinate{kind_, 0}, *p_, *q_, r);
      auto v = internal::filtered_sign(Coordinate{kind_, 1}, *p_, *q_, r);

      if (u > 0) {
        if (v > 0) {
          return 1;  // 1st quadrant
        }
        if (v < 0) {
          return 7;  // 4th quadrant
        }
        return 0;  // +u
      }

      if (u < 0) {
        if (v > 0) {
          return 3;  // 2nd quadrant
        }
        if (v < 0) {
          return 5;  // 3rd quadrant
        }
        return 4;  // -u
      }

      if (v > 0) {
        return 2;  // +v
      }
      if (v < 0) {
        return 6;  // -v
      }

      throw std::runtime_error("degenerate face");
    }

   private:
    enum class Kind {
      X,       // u = (1, 0, 0)
      Y,       // u = (0, 1, 0)
      Z,       // u = (0, 0, 1)
      ZERO_X,  // u = (0, -n_z, n_y)
      ZERO_Y,  // u = (-n_z, 0, n_x)
      ZERO_Z,  // u = (-n_y, n_x, 0)
    };

    // The u (index 0) or v (index 1) coordinate of r - p, which is a homogeneous polynomial in
    // coordinate differences.
    struct Coordinate {
      Kind kind;
      int index;

      template <class T>
      T operator()(const std::array<T, 3>& p, const std::array<T, 3>& q,
                   const std::array<T, 3>& r) const {
        std::array<T, 3> n{q[0] - p[0], q[1] - p[1], q[2] - p[2]};
        std::array<T, 3> w{r[0] - p[0], r[1] - p[1], r[2] - p[2]};
        std::array<T, 3> u{};
        switch (kind) {
          case Kind::X:
            u = {T{1}, T{0}, T{0}};
            break;
          case Kind::Y:
            u = {T{0}, T{1}, T{0}};
            break;
          case Kind::Z:
            u = {T{0}, T{0}, T{1}};
            break;
          case Kind::ZERO_X:
            u = {T{0}, -n[2], n[1]};
            break;
          case Kind::ZERO_Y:
            u = {-n[2], T{0}, n[0]};
            break;
          case Kind::ZERO_Z:
            u = {-n[1], n[0], T{0}};
            break;
        }
        if (index == 0) {
          return w[0] * u[0] + w[1] * u[1] + w[2] * u[2];
        }
        std::array<T, 3> v{n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2],
                           n[0] * u[1] - n[1] * u[0]};
        return w[0] * v[0] + w[1] * v[1] + w[2] * v[2];
      }
    };

    const Point* p_;
    const Point* q_;
    Kind kind_{};
  };

  struct Face_around_edge {
    Face_index fi;
    Vertex_index vi_r;
    const Point* r;
    int radial_bin;
    Orientation orientation;

    Face_around_edge(Face_index fi, Vertex_index vi_r, const Point* r, int radial_bin,
                     Orientation orientation)
        : fi{fi}, vi_r{vi_r}, r{r}, radial_bin{radial_bin}, orientation{orientation} {}
  };

  // Sorts faces counterclockwise around the edge pq, viewed from q.
  struct Radial_ordering {
    const Point* p;
    const Point* q;

    bool operator()(const Face_around_edge& f, const Face_around_edge& g) const {
      if (f.vi_r == g.vi_r) {
        return false;
      }
      if (f.radial_bin != g.radial_bin) {
        return f.radial_bin < g.radial_bin;
      }
      // det[(f.r - p)_uv, (g.r - p)_uv] = |u|^2 det[q - p, f.r - p, g.r - p].
      return orientation(*p, *q, *f.r, *g.r) == POSITIVE;
    }
  };

  mutable std::vector<Face_around_edge> faces_;
  mutable Propagate_face_tags propagate_face_tags_;
};

}  // namespace kigumi
