#pragma once

#include <kigumi/Point_list.h>
#include <kigumi/Triangle_region.h>
#include <kigumi/kernel/enum.h>
#include <kigumi/kernel/predicates.h>

#include <algorithm>
#include <array>
#include <boost/unordered/unordered_flat_map.hpp>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace kigumi {

// A constrained Delaunay triangulation of a triangle in 3D.
//
// All inserted points must lie in the (closed) triangle. The triangulation is computed in the
// projection onto a coordinate plane, which is exact since all points are exactly coplanar.
template <class K>
class Triangulation {
  using Point = typename K::Point_3;
  using Point_list = kigumi::Point_list<K>;

 public:
  using Vertex_handle = std::size_t;

  struct Intersection_of_constraints_exception : std::runtime_error {
    Intersection_of_constraints_exception() : std::runtime_error{"intersection of constraints"} {}
  };

  Triangulation(const Point_list& points, Triangle_region f, std::size_t a, std::size_t b,
                std::size_t c)
      : points_{&points}, f_{f} {
    vertex_points_ = {a, b, c};
    vertex_faces_ = {0, 0, 0};
    faces_.push_back({{0, 1, 2}, {kNone, kNone, kNone}, {false, false, false}});
    choose_projection();
    for (std::size_t ei = 0; ei < 3; ++ei) {
      edge_directions_.at(ei) = compare_lexicographically(point(ei), point((ei + 1) % 3));
    }
  }

  template <class OutputIterator>
  std::size_t get_faces(OutputIterator faces) const {
    for (const auto& f : faces_) {
      *faces++ = std::array<std::size_t, 3>{vertex_points_.at(f.v[0]), vertex_points_.at(f.v[1]),
                                            vertex_points_.at(f.v[2])};
    }
    return faces_.size();
  }

  Vertex_handle insert(std::size_t p, Triangle_region region) {
    switch (intersection(region, f_)) {
      case Triangle_region::LEFT_VERTEX_0:
      case Triangle_region::RIGHT_VERTEX_0:
        return 0;

      case Triangle_region::LEFT_VERTEX_1:
      case Triangle_region::RIGHT_VERTEX_1:
        return 1;

      case Triangle_region::LEFT_VERTEX_2:
      case Triangle_region::RIGHT_VERTEX_2:
        return 2;

      case Triangle_region::LEFT_EDGE_01:
      case Triangle_region::RIGHT_EDGE_01:
        return insert_in_edge(p, 0);

      case Triangle_region::LEFT_EDGE_12:
      case Triangle_region::RIGHT_EDGE_12:
        return insert_in_edge(p, 1);

      case Triangle_region::LEFT_EDGE_20:
      case Triangle_region::RIGHT_EDGE_20:
        return insert_in_edge(p, 2);

      case Triangle_region::LEFT_FACE:
      case Triangle_region::RIGHT_FACE:
        return insert_in_face(p);

      default:
        throw std::runtime_error("invalid region");
    }
  }

  void insert_constraint(Vertex_handle vh_i, Vertex_handle vh_j) {
    while (vh_i != vh_j) {
      vh_i = insert_constraint_part(vh_i, vh_j);
    }
  }

 private:
  static constexpr std::size_t kNone = std::numeric_limits<std::size_t>::max();

  // Vertices are in counterclockwise order. The ith edge is the one opposite v[i].
  struct Face {
    std::array<Vertex_handle, 3> v;
    // The neighbor across the ith edge, or kNone if the edge is on the boundary.
    std::array<std::size_t, 3> n;
    // Whether the ith edge is constrained.
    std::array<bool, 3> c;
  };

  using Triangle = std::array<Vertex_handle, 3>;

  const Point& point(Vertex_handle vh) const { return points_->at(vertex_points_.at(vh)); }

  // Use the projection that drops the coordinate with the largest normal component (the first one
  // in case of a tie). The choice is exact and depends only on the plane, so that coplanar faces
  // are triangulated in the same projection.
  void choose_projection() {
    const auto& pa = point(0);
    const auto& pb = point(1);
    const auto& pc = point(2);

    // n[k] is the kth component of the normal vector (b - a) x (c - a).
    auto approx_normal = [&](int k) {
      return internal::Orientation_2_poly{(k + 1) % 3, (k + 2) % 3}(pa.approx(), pb.approx(),
                                                                    pc.approx());
    };
    auto exact_normal = [&](int k) {
      return internal::Orientation_2_poly{(k + 1) % 3, (k + 2) % 3}(pa.rational(), pb.rational(),
                                                                    pc.rational());
    };
    auto abs_interval = [](const Interval& x) {
      if (x.inf() >= 0.0) {
        return x;
      }
      if (x.sup() <= 0.0) {
        return -x;
      }
      return Interval{0.0, std::max(-x.inf(), x.sup())};
    };
    // Whether |n[a]| > |n[b]|.
    auto is_larger = [&](int a, int b) {
      auto x = abs_interval(approx_normal(a));
      auto y = abs_interval(approx_normal(b));
      if (x.inf() > y.sup()) {
        return true;
      }
      if (x.sup() < y.inf()) {
        return false;
      }
      return abs(exact_normal(a)) > abs(exact_normal(b));
    };

    auto k = 0;
    for (auto c : {1, 2}) {
      if (is_larger(c, k)) {
        k = c;
      }
    }
    i_ = (k + 1) % 3;
    j_ = (k + 2) % 3;
    sign_ = orientation_2(i_, j_, pa, pb, pc);
    if (sign_ == ZERO) {
      throw std::runtime_error("degenerate face");
    }
  }

  // The orientation with respect to the orientation of the triangle.
  Orientation orientation(const Point& p, const Point& q, const Point& r) const {
    return sign_ * orientation_2(i_, j_, p, q, r);
  }

  Orientation orientation(Vertex_handle p, Vertex_handle q, Vertex_handle r) const {
    return orientation(point(p), point(q), point(r));
  }

  // POSITIVE if p is inside the circumcircle of the counterclockwise triangle (p0, p1, p2).
  //
  // Cocircular cases are resolved by a symbolic perturbation, so that the result never is
  // ON_ORIENTED_BOUNDARY, and the Delaunay triangulation is unique regardless of the insertion
  // order. This is required for overlapping coplanar faces of the two meshes to be triangulated
  // identically.
  //
  // The perturbation is that of O. Devillers and M. Teillaud, "Perturbations for Delaunay and
  // weighted Delaunay 3D triangulations", Computational Geometry 44(3), 2011, in the plane. The
  // predicate is the sign of the determinant whose rows are (x, y, x^2 + y^2, 1) for p0, p1, p2,
  // and p. The lifted coordinate x^2 + y^2 of each point is raised by an infinitesimal, which is
  // larger by orders of magnitude for lexicographically larger points. The determinant is linear in
  // the lifted column, so when it vanishes, the sign of the perturbed determinant is that of the
  // first nonzero cofactor of the lifted column, taking the rows from the largest point down.
  // Expanding the cofactors, that of the row of p is -orientation(p0, p1, p2), and that of the row
  // of p_k is the orientation of (p0, p1, p2) with p_k replaced by p.
  Oriented_side side_of_circle(Vertex_handle p0, Vertex_handle p1, Vertex_handle p2,
                               Vertex_handle p) const {
    auto os = sign_ * side_of_oriented_circle_2(i_, j_, point(p0), point(p1), point(p2), point(p));
    if (os != ON_ORIENTED_BOUNDARY) {
      return os;
    }

    const std::array<Vertex_handle, 4> rows{p0, p1, p2, p};
    auto lifted_cofactor = [&](std::size_t k) {
      if (k == 3) {
        return -orientation(p0, p1, p2);
      }
      std::array<Vertex_handle, 3> t{p0, p1, p2};
      t.at(k) = p;
      return orientation(t[0], t[1], t[2]);
    };

    std::array<std::size_t, 4> by_perturbation{0, 1, 2, 3};
    std::sort(by_perturbation.begin(), by_perturbation.end(), [&](std::size_t a, std::size_t b) {
      return compare_lexicographically(point(rows.at(a)), point(rows.at(b))) == LARGER;
    });
    for (auto k : by_perturbation) {
      if (auto s = lifted_cofactor(k); s != ZERO) {
        return s;
      }
    }

    // All four points are collinear, so that there is no circle through p0, p1, and p2.
    return ON_NEGATIVE_SIDE;
  }

  static int index_of(const Face& f, Vertex_handle vh) {
    for (int i = 0; i < 3; ++i) {
      if (f.v.at(i) == vh) {
        return i;
      }
    }
    throw std::logic_error("vertex not found in face");
  }

  static int index_of_neighbor(const Face& f, std::size_t fi) {
    for (int i = 0; i < 3; ++i) {
      if (f.n.at(i) == fi) {
        return i;
      }
    }
    throw std::logic_error("neighbor not found in face");
  }

  // Pairs of (face, index of vh in the face) around vh.
  std::vector<std::pair<std::size_t, int>> faces_around(Vertex_handle vh) const {
    std::vector<std::pair<std::size_t, int>> result;
    auto start = vertex_faces_.at(vh);

    // Counterclockwise.
    auto fi = start;
    while (true) {
      auto k = index_of(faces_.at(fi), vh);
      result.emplace_back(fi, k);
      auto next = faces_.at(fi).n.at((k + 1) % 3);
      if (next == start) {
        return result;
      }
      if (next == kNone) {
        break;
      }
      fi = next;
    }

    // Clockwise.
    fi = start;
    while (true) {
      auto k = index_of(faces_.at(fi), vh);
      auto next = faces_.at(fi).n.at((k + 2) % 3);
      if (next == kNone) {
        break;
      }
      fi = next;
      result.emplace_back(fi, index_of(faces_.at(fi), vh));
    }
    return result;
  }

  Vertex_handle new_vertex(std::size_t p) {
    vertex_points_.push_back(p);
    vertex_faces_.push_back(kNone);
    return vertex_points_.size() - 1;
  }

  Vertex_handle insert_in_edge(std::size_t p, std::size_t ei) {
    auto it = id_to_vh_.find(p);
    if (it != id_to_vh_.end()) {
      return it->second;
    }

    const auto& pp = points_->at(p);
    auto& on_edge = edge_vertices_.at(ei);
    auto dir = edge_directions_.at(ei);
    auto pos = std::lower_bound(on_edge.begin(), on_edge.end(), pp,
                                [&](Vertex_handle vh, const Point& q) {
                                  return compare_lexicographically(point(vh), q) == dir;
                                });
    if (pos != on_edge.end() && point(*pos) == pp) {
      id_to_vh_.emplace(p, *pos);
      return *pos;
    }

    auto u = pos == on_edge.begin() ? ei : *(pos - 1);
    auto w = pos == on_edge.end() ? (ei + 1) % 3 : *pos;

    std::size_t fi = kNone;
    int e{};
    for (auto [fj, k] : faces_around(u)) {
      if (faces_.at(fj).v.at((k + 1) % 3) == w) {
        fi = fj;
        e = (k + 2) % 3;
        break;
      }
    }
    if (fi == kNone) {
      throw std::logic_error("boundary edge not found");
    }

    auto vh = new_vertex(p);
    on_edge.insert(pos, vh);
    id_to_vh_.emplace(p, vh);
    split_edge(fi, e, vh);
    return vh;
  }

  Vertex_handle insert_in_face(std::size_t p) {
    auto it = id_to_vh_.find(p);
    if (it != id_to_vh_.end()) {
      return it->second;
    }

    const auto& pp = points_->at(p);
    auto fi = locate(pp);
    const auto& f = faces_.at(fi);

    std::array<Orientation, 3> o{};
    auto num_zeros = 0;
    for (int e = 0; e < 3; ++e) {
      o.at(e) = orientation(point(f.v.at((e + 1) % 3)), point(f.v.at((e + 2) % 3)), pp);
      if (o.at(e) == ZERO) {
        ++num_zeros;
      }
    }

    Vertex_handle vh{};
    if (num_zeros == 0) {
      vh = new_vertex(p);
      split_face(fi, vh);
    } else if (num_zeros == 1) {
      auto e = static_cast<int>(std::find(o.begin(), o.end(), ZERO) - o.begin());
      vh = new_vertex(p);
      split_edge(fi, e, vh);
    } else {
      // The point coincides with an existing vertex.
      auto k = static_cast<int>(std::find_if(o.begin(), o.end(), [](auto x) { return x != ZERO; }) -
                                o.begin());
      vh = f.v.at(k);
    }
    id_to_vh_.emplace(p, vh);
    return vh;
  }

  // Returns a face that contains p (in its closure).
  std::size_t locate(const Point& p) {
    auto fi = last_face_ < faces_.size() ? last_face_ : 0;
    auto max_steps = 4 * faces_.size() + 16;

    for (std::size_t step = 0; step < max_steps; ++step) {
      const auto& f = faces_.at(fi);
      auto start = static_cast<int>(next_random() % 3);
      auto moved = false;
      for (int j = 0; j < 3; ++j) {
        auto e = (start + j) % 3;
        if (f.n.at(e) == kNone) {
          continue;
        }
        if (orientation(point(f.v.at((e + 1) % 3)), point(f.v.at((e + 2) % 3)), p) == NEGATIVE) {
          fi = f.n.at(e);
          moved = true;
          break;
        }
      }
      if (!moved) {
        return fi;
      }
    }

    // The walk did not terminate; fall back to a linear search.
    for (fi = 0; fi < faces_.size(); ++fi) {
      const auto& f = faces_.at(fi);
      auto inside = true;
      for (int e = 0; e < 3 && inside; ++e) {
        inside = orientation(point(f.v.at((e + 1) % 3)), point(f.v.at((e + 2) % 3)), p) != NEGATIVE;
      }
      if (inside) {
        return fi;
      }
    }

    throw std::runtime_error("point is outside the triangle");
  }

  void split_face(std::size_t fi, Vertex_handle vh) {
    auto [a, b, c] = faces_.at(fi).v;
    auto new_faces = retriangulate({fi}, {{a, b, vh}, {b, c, vh}, {c, a, vh}}, {});
    restore_delaunay(vh, new_faces);
  }

  // Splits the eth edge of the face and its neighbor at vh, which lies in the interior of the edge.
  void split_edge(std::size_t fi, int e, Vertex_handle vh) {
    const auto& f = faces_.at(fi);
    auto x = f.v.at(e);
    auto u = f.v.at((e + 1) % 3);
    auto w = f.v.at((e + 2) % 3);
    auto gi = f.n.at(e);
    auto constrained = f.c.at(e);

    std::vector<std::size_t> old_faces{fi};
    std::vector<Triangle> new_triangles{{x, u, vh}, {x, vh, w}};
    if (gi != kNone) {
      const auto& g = faces_.at(gi);
      auto y = g.v.at(index_of_neighbor(g, fi));
      old_faces.push_back(gi);
      new_triangles.push_back({y, w, vh});
      new_triangles.push_back({y, vh, u});
    }

    std::vector<std::pair<Vertex_handle, Vertex_handle>> constraints;
    if (constrained) {
      constraints.emplace_back(u, vh);
      constraints.emplace_back(vh, w);
    }

    std::vector<std::pair<Vertex_handle, Vertex_handle>> boundary_edges;
    if (gi == kNone) {
      boundary_edges.emplace_back(u, vh);
      boundary_edges.emplace_back(vh, w);
    }

    auto new_faces = retriangulate(old_faces, new_triangles, constraints, boundary_edges);
    restore_delaunay(vh, new_faces);
  }

  // Lawson's flip algorithm for the faces incident to a newly inserted vertex.
  void restore_delaunay(Vertex_handle vh, std::vector<std::size_t> stack) {
    while (!stack.empty()) {
      auto fi = stack.back();
      stack.pop_back();

      const auto& f = faces_.at(fi);
      auto k = std::find(f.v.begin(), f.v.end(), vh) - f.v.begin();
      if (k == 3) {
        continue;
      }
      auto gi = f.n.at(k);
      if (gi == kNone || f.c.at(k)) {
        continue;
      }

      const auto& g = faces_.at(gi);
      auto y = g.v.at(index_of_neighbor(g, fi));
      auto u = f.v.at((k + 1) % 3);
      auto w = f.v.at((k + 2) % 3);
      if (side_of_circle(vh, u, w, y) == POSITIVE) {
        auto new_faces = retriangulate({fi, gi}, {{vh, u, y}, {vh, y, w}}, {});
        stack.insert(stack.end(), new_faces.begin(), new_faces.end());
      }
    }
  }

  // Replaces old_faces with new_triangles, which must triangulate the same region.
  // constraints are the constrained edges in the interior of the region or on its new boundary.
  // boundary_edges are the (directed) edges on the boundary of the triangle that result from
  // splitting a boundary edge of the region. Returns the indices of the new faces.
  std::vector<std::size_t> retriangulate(
      const std::vector<std::size_t>& old_faces, const std::vector<Triangle>& new_triangles,
      const std::vector<std::pair<Vertex_handle, Vertex_handle>>& constraints,
      const std::vector<std::pair<Vertex_handle, Vertex_handle>>& boundary_edges = {}) {
    struct Outer_edge {
      Vertex_handle u;
      Vertex_handle w;
      std::size_t neighbor;
      int neighbor_edge;
      bool constrained;
    };

    if (new_triangles.size() < old_faces.size()) {
      throw std::logic_error("retriangulation must not reduce the number of faces");
    }

    auto is_old = [&](std::size_t fi) {
      return std::find(old_faces.begin(), old_faces.end(), fi) != old_faces.end();
    };

    std::vector<Outer_edge> outer_edges;
    for (auto fi : old_faces) {
      const auto& f = faces_.at(fi);
      for (int e = 0; e < 3; ++e) {
        auto gi = f.n.at(e);
        if (gi != kNone && is_old(gi)) {
          continue;
        }
        auto ge = gi == kNone ? -1 : index_of_neighbor(faces_.at(gi), fi);
        outer_edges.push_back({f.v.at((e + 1) % 3), f.v.at((e + 2) % 3), gi, ge, f.c.at(e)});
      }
    }

    std::vector<std::size_t> ids;
    for (std::size_t t = 0; t < new_triangles.size(); ++t) {
      if (t < old_faces.size()) {
        ids.push_back(old_faces.at(t));
      } else {
        ids.push_back(faces_.size());
        faces_.emplace_back();
      }
      faces_.at(ids.back()) = {new_triangles.at(t), {kNone, kNone, kNone}, {false, false, false}};
    }

    auto is_constrained = [&](Vertex_handle u, Vertex_handle w) {
      return std::any_of(constraints.begin(), constraints.end(), [&](const auto& c) {
        return (c.first == u && c.second == w) || (c.first == w && c.second == u);
      });
    };

    for (std::size_t t = 0; t < new_triangles.size(); ++t) {
      auto& f = faces_.at(ids.at(t));
      for (int e = 0; e < 3; ++e) {
        auto u = f.v.at((e + 1) % 3);
        auto w = f.v.at((e + 2) % 3);

        auto outer = std::find_if(outer_edges.begin(), outer_edges.end(),
                                  [&](const auto& o) { return o.u == u && o.w == w; });
        if (outer != outer_edges.end()) {
          f.n.at(e) = outer->neighbor;
          f.c.at(e) = outer->constrained;
          if (outer->neighbor != kNone) {
            faces_.at(outer->neighbor).n.at(outer->neighbor_edge) = ids.at(t);
          }
          continue;
        }

        auto found = false;
        for (std::size_t s = 0; s < new_triangles.size() && !found; ++s) {
          if (s == t) {
            continue;
          }
          const auto& g = new_triangles.at(s);
          for (int ge = 0; ge < 3; ++ge) {
            if (g.at((ge + 1) % 3) == w && g.at((ge + 2) % 3) == u) {
              f.n.at(e) = ids.at(s);
              f.c.at(e) = is_constrained(u, w);
              found = true;
              break;
            }
          }
        }
        if (!found && std::find(boundary_edges.begin(), boundary_edges.end(),
                                std::make_pair(u, w)) != boundary_edges.end()) {
          f.c.at(e) = is_constrained(u, w);
          found = true;
        }
        if (!found) {
          throw std::logic_error("inconsistent retriangulation");
        }
      }
    }

    for (auto fi : ids) {
      for (auto vh : faces_.at(fi).v) {
        vertex_faces_.at(vh) = fi;
      }
    }
    last_face_ = ids.back();

    return ids;
  }

  void set_constrained(std::size_t fi, int e) {
    auto& f = faces_.at(fi);
    f.c.at(e) = true;
    auto gi = f.n.at(e);
    if (gi != kNone) {
      auto& g = faces_.at(gi);
      g.c.at(index_of_neighbor(g, fi)) = true;
    }
  }

  // Whether q lies in the direction of r from p, given that p, q, and r are collinear.
  bool is_in_direction(Vertex_handle p, Vertex_handle q, Vertex_handle r) const {
    return compare_lexicographically(point(p), point(q)) ==
           compare_lexicographically(point(p), point(r));
  }

  // Inserts the constraint from a toward b, up to the first vertex on the segment.
  // Returns that vertex.
  Vertex_handle insert_constraint_part(Vertex_handle a, Vertex_handle b) {
    auto around = faces_around(a);

    for (auto [fi, k] : around) {
      const auto& f = faces_.at(fi);
      if (f.v.at((k + 1) % 3) == b) {
        set_constrained(fi, (k + 2) % 3);
        return b;
      }
      if (f.v.at((k + 2) % 3) == b) {
        set_constrained(fi, (k + 1) % 3);
        return b;
      }
    }

    for (auto [fi, k] : around) {
      const auto& f = faces_.at(fi);
      auto u = f.v.at((k + 1) % 3);
      auto w = f.v.at((k + 2) % 3);

      auto ou = orientation(a, u, b);
      if (ou == ZERO && is_in_direction(a, u, b)) {
        set_constrained(fi, (k + 2) % 3);
        return u;
      }

      auto ow = orientation(a, w, b);
      if (ow == ZERO && is_in_direction(a, w, b)) {
        set_constrained(fi, (k + 1) % 3);
        return w;
      }

      if (ou == POSITIVE && ow == NEGATIVE) {
        return insert_crossing_constraint(fi, k, a, b);
      }
    }

    throw std::logic_error("constraint direction not found");
  }

  // Inserts the constraint from a toward b, starting from the face whose edge opposite a (the kth
  // vertex) is crossed by the constraint. Returns the vertex where the constraint ends.
  Vertex_handle insert_crossing_constraint(std::size_t fi, int k, Vertex_handle a,
                                           Vertex_handle b) {
    std::vector<std::size_t> crossed_faces{fi};
    // Vertices on the left and right of the segment ab, from a toward b.
    std::vector<Vertex_handle> left;
    std::vector<Vertex_handle> right;

    auto r = faces_.at(fi).v.at((k + 1) % 3);
    auto l = faces_.at(fi).v.at((k + 2) % 3);
    right.push_back(r);
    left.push_back(l);

    auto cur = fi;
    auto e = k;
    Vertex_handle end{};
    while (true) {
      const auto& f = faces_.at(cur);
      if (f.c.at(e)) {
        throw Intersection_of_constraints_exception{};
      }
      auto gi = f.n.at(e);
      if (gi == kNone) {
        throw std::logic_error("constraint leaves the triangle");
      }
      crossed_faces.push_back(gi);

      const auto& g = faces_.at(gi);
      auto y = g.v.at(index_of_neighbor(g, cur));
      if (y == b) {
        end = b;
        break;
      }

      auto o = orientation(a, b, y);
      if (o == ZERO) {
        end = y;
        break;
      }
      if (o == POSITIVE) {
        left.push_back(y);
        e = index_of(g, l);
        l = y;
      } else {
        right.push_back(y);
        e = index_of(g, r);
        r = y;
      }
      cur = gi;
    }

    std::vector<Triangle> new_triangles;
    triangulate_pseudo_polygon(a, end, left, 0, left.size(), new_triangles);
    std::reverse(right.begin(), right.end());
    triangulate_pseudo_polygon(end, a, right, 0, right.size(), new_triangles);

    retriangulate(crossed_faces, new_triangles, {{a, end}});
    return end;
  }

  // Triangulates the polygon a, b, chain[last - 1], ..., chain[first], where the chain lies on the
  // left of ab and is ordered from a toward b, so that the result is constrained Delaunay.
  void triangulate_pseudo_polygon(Vertex_handle a, Vertex_handle b,
                                  const std::vector<Vertex_handle>& chain, std::size_t first,
                                  std::size_t last, std::vector<Triangle>& triangles) const {
    if (first >= last) {
      return;
    }

    auto ci = first;
    for (auto i = first + 1; i < last; ++i) {
      if (side_of_circle(a, b, chain.at(ci), chain.at(i)) == POSITIVE) {
        ci = i;
      }
    }

    auto c = chain.at(ci);
    triangles.push_back({a, b, c});
    triangulate_pseudo_polygon(a, c, chain, first, ci, triangles);
    triangulate_pseudo_polygon(c, b, chain, ci + 1, last, triangles);
  }

  std::uint32_t next_random() {
    // A linear congruential generator, for reproducible results.
    random_state_ = random_state_ * 1664525U + 1013904223U;
    return random_state_ >> 16;
  }

  const Point_list* points_;
  Triangle_region f_;
  int i_{};
  int j_{};
  Orientation sign_{ZERO};
  std::array<Comparison_result, 3> edge_directions_{};
  std::vector<std::size_t> vertex_points_;
  std::vector<std::size_t> vertex_faces_;
  std::vector<Face> faces_;
  // Vertices in the interior of the edges of the triangle, sorted from the start vertex.
  std::array<std::vector<Vertex_handle>, 3> edge_vertices_;
  boost::unordered_flat_map<std::size_t, Vertex_handle> id_to_vh_;
  std::size_t last_face_{};
  std::uint32_t random_state_{};
};

}  // namespace kigumi
