#pragma once

#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Mesh_iterators.h>
#include <kigumi/Null_data.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/parallel_sort.h>

#include <boost/range/iterator_range.hpp>
#include <utility>
#include <vector>

namespace kigumi {

// Example 1:
//
//      3       2     indices_   face_indices_
//       +-----+            |        |
//      / \ b / \           0:  0 -> a:  (0, 1, 2)
//     / c \ / a \                   b:  (0, 2, 3)
//    +-----+-----+                  c:  (0, 3, 4)
//   4      0      1        3:  1 -> a
//                          4:  2 -> a
//                                   b
//                          6:  3 -> b
//                                   c
//                          8:  4 -> c
//                          9:  END
//
// Example 2:
//
//       5            indices_   face_indices_
//       +                  |        |
//      / \   + 4           0:  0 -> a:  (0, 1, 2)
//     / a \                1:  1 -> a
//    +-----+    + 3        2
//   0       1              2
//                          2
//       + 2                2:  5 -> a
//                          3:  END

template <class K, class FaceData = Null_data>
class Triangle_mesh {
  using Bbox = Bbox_3;
  using Face_data = FaceData;
  using Point = typename K::Point_3;
  using Triangle = typename K::Triangle_3;

 public:
  Triangle_mesh() = default;

  ~Triangle_mesh() = default;

  Triangle_mesh(const Triangle_mesh& other)
      : points_{other.points_},
        faces_{other.faces_},
        face_data_{other.face_data_},
        indices_{other.indices_},
        face_indices_{other.face_indices_} {}

  Triangle_mesh(Triangle_mesh&& other) noexcept
      : points_{std::move(other.points_)},
        faces_{std::move(other.faces_)},
        face_data_{std::move(other.face_data_)},
        indices_{std::move(other.indices_)},
        face_indices_{std::move(other.face_indices_)} {}

  Triangle_mesh& operator=(const Triangle_mesh& other) {
    if (this != &other) {
      points_ = other.points_;
      faces_ = other.faces_;
      face_data_ = other.face_data_;
      indices_ = other.indices_;
      face_indices_ = other.face_indices_;
    }
    return *this;
  }

  Triangle_mesh& operator=(Triangle_mesh&& other) noexcept {
    points_ = std::move(other.points_);
    faces_ = std::move(other.faces_);
    face_data_ = std::move(other.face_data_);
    indices_ = std::move(other.indices_);
    face_indices_ = std::move(other.face_indices_);
    return *this;
  }

  Triangle_mesh(std::vector<Point> points, std::vector<Face> faces, std::vector<FaceData> face_data)
      : points_{std::move(points)}, faces_{std::move(faces)}, face_data_{std::move(face_data)} {}

  Vertex_index add_vertex(const Point& p) {
    points_.push_back(p);
    return Vertex_index{points_.size() - 1};
  }

  Face_index add_face(const Face& face) {
    faces_.push_back(face);
    face_data_.emplace_back();
    return Face_index{faces_.size() - 1};
  }

  void finalize() {
    std::vector<std::pair<Vertex_index, Face_index>> map;
    map.reserve(3 * faces_.size());
    {
      Face_index fi{0};
      for (const auto& face : faces_) {
        map.emplace_back(face[0], fi);
        map.emplace_back(face[1], fi);
        map.emplace_back(face[2], fi);
        ++fi;
      }
    }

    parallel_sort(map.begin(), map.end());

    face_indices_.reserve(3 * faces_.size());
    indices_.reserve(points_.size() + 1);
    std::size_t index{};
    std::ptrdiff_t prev_v{-1};
    for (auto [vi, fi] : map) {
      face_indices_.push_back(fi);

      auto v = static_cast<std::ptrdiff_t>(vi.idx());
      for (std::ptrdiff_t i = 0; i < v - prev_v; ++i) {
        indices_.push_back(index);
      }
      prev_v = v;
      ++index;
    }
    indices_.push_back(index);
  }

  std::size_t num_vertices() const { return points_.size(); }

  std::size_t num_faces() const { return faces_.size(); }

  Vertex_iterator vertices_begin() const { return Vertex_iterator(Vertex_index{0}); }

  Vertex_iterator vertices_end() const { return Vertex_iterator(Vertex_index{points_.size()}); }

  auto vertices() const { return boost::make_iterator_range(vertices_begin(), vertices_end()); }

  Face_iterator faces_begin() const { return Face_iterator(Face_index{0}); }

  Face_iterator faces_end() const { return Face_iterator(Face_index{faces_.size()}); }

  auto faces() const { return boost::make_iterator_range(faces_begin(), faces_end()); }

  auto faces_around_edge(const Edge& edge) const {
    auto i_it = face_indices_.begin() + indices_.at(edge[0].idx());
    auto i_end = face_indices_.begin() + indices_.at(edge[0].idx() + 1);
    auto j_it = face_indices_.begin() + indices_.at(edge[1].idx());
    auto j_end = face_indices_.begin() + indices_.at(edge[1].idx() + 1);
    return boost::make_iterator_range(Face_around_edge_iterator(i_it, i_end, j_it, j_end),
                                      Face_around_edge_iterator(i_end, i_end, j_end, j_end));
  }

  auto faces_around_face(Face_index fi, const Edge_set& border_edges) const {
    const auto& f = face(fi);
    auto e1 = make_edge(f[0], f[1]);
    auto e2 = make_edge(f[1], f[2]);
    auto e3 = make_edge(f[2], f[0]);
    auto end1 = faces_around_edge(e1).end();
    auto it1 = border_edges.contains(e1) ? end1 : faces_around_edge(e1).begin();
    auto end2 = faces_around_edge(e2).end();
    auto it2 = border_edges.contains(e2) ? end2 : faces_around_edge(e2).begin();
    auto end3 = faces_around_edge(e3).end();
    auto it3 = border_edges.contains(e3) ? end3 : faces_around_edge(e3).begin();
    return boost::make_iterator_range(
        Face_around_face_iterator(fi, it1, end1, it2, end2, it3, end3),
        Face_around_face_iterator(fi, end1, end1, end2, end2, end3, end3));
  }

  Face_data& data(Face_index fi) { return face_data_.at(fi.idx()); }

  const Face_data& data(Face_index fi) const { return face_data_.at(fi.idx()); }

  const Face& face(Face_index fi) const { return faces_.at(fi.idx()); }

  const Point& point(Vertex_index vi) const { return points_.at(vi.idx()); }

  Triangle triangle(Face_index fi) const {
    const auto& f = face(fi);
    return {point(f[0]), point(f[1]), point(f[2])};
  }

  Bbox bbox() const {
    Bbox bbox;
    for (const auto& p : points_) {
      bbox += p.bbox();
    }
    return bbox;
  }

  Triangle_soup<K, FaceData> take_triangle_soup() {
    return {std::move(points_), std::move(faces_), std::move(face_data_)};
  }

 private:
  std::vector<Point> points_;
  std::vector<Face> faces_;
  std::vector<Face_data> face_data_;
  std::vector<std::size_t> indices_;
  std::vector<Face_index> face_indices_;
};

}  // namespace kigumi
