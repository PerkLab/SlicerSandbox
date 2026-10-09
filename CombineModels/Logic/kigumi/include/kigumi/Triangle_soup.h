#pragma once

#include <kigumi/AABB_tree/AABB_leaf.h>
#include <kigumi/AABB_tree/AABB_tree.h>
#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Mesh_iterators.h>
#include <kigumi/Null_data.h>
#include <kigumi/io.h>
#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/kernel/Rational.h>
#include <kigumi/mesh_utility.h>

#include <boost/range/iterator_range.hpp>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>

namespace kigumi {

template <class K, class FaceData = Null_data>
class Triangle_soup {
  using Bbox = Bbox_3;
  using Face_data = FaceData;
  using Point = typename K::Point_3;
  using Triangle = typename K::Triangle_3;

 public:
  class Leaf : public AABB_leaf {
    using Bbox = Bbox_3;

   public:
    Leaf(const Bbox& bbox, Face_index fi) : AABB_leaf{bbox}, fi_{fi} {}

    Face_index face_index() const { return fi_; }

   private:
    Face_index fi_;
  };

  Triangle_soup() = default;

  ~Triangle_soup() = default;

  Triangle_soup(const Triangle_soup& other)
      : points_{other.points_}, faces_{other.faces_}, face_data_{other.face_data_} {}

  Triangle_soup(Triangle_soup&& other) noexcept
      : points_{std::move(other.points_)},
        faces_{std::move(other.faces_)},
        face_data_{std::move(other.face_data_)},
        aabb_tree_{std::move(other.aabb_tree_)} {}

  Triangle_soup& operator=(const Triangle_soup& other) {
    if (this != &other) {
      points_ = other.points_;
      faces_ = other.faces_;
      face_data_ = other.face_data_;
      aabb_tree_.reset();
    }
    return *this;
  }

  Triangle_soup& operator=(Triangle_soup&& other) noexcept {
    points_ = std::move(other.points_);
    faces_ = std::move(other.faces_);
    face_data_ = std::move(other.face_data_);
    aabb_tree_ = std::move(other.aabb_tree_);
    return *this;
  }

  Triangle_soup(std::vector<Point> points, std::vector<Face> faces, std::vector<FaceData> face_data)
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

  std::size_t num_vertices() const { return points_.size(); }

  std::size_t num_faces() const { return faces_.size(); }

  Vertex_iterator vertices_begin() const { return Vertex_iterator(Vertex_index{0}); }

  Vertex_iterator vertices_end() const { return Vertex_iterator(Vertex_index{points_.size()}); }

  auto vertices() const { return boost::make_iterator_range(vertices_begin(), vertices_end()); }

  Face_iterator faces_begin() const { return Face_iterator(Face_index{0}); }

  Face_iterator faces_end() const { return Face_iterator(Face_index{faces_.size()}); }

  auto faces() const { return boost::make_iterator_range(faces_begin(), faces_end()); }

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

  const AABB_tree<Leaf>& aabb_tree() const {
    std::lock_guard lock{aabb_tree_mutex_};

    if (!aabb_tree_) {
      std::vector<Leaf> leaves;
      leaves.reserve(num_faces());
      for (auto fi : faces()) {
        leaves.emplace_back(internal::face_bbox(*this, fi), fi);
      }
      aabb_tree_ = std::make_unique<AABB_tree<Leaf>>(std::move(leaves));
    }

    return *aabb_tree_;
  }

 private:
  std::vector<Point> points_;
  std::vector<Face> faces_;
  std::vector<Face_data> face_data_;
  mutable std::unique_ptr<AABB_tree<Leaf>> aabb_tree_;
  mutable std::mutex aabb_tree_mutex_;
};

template <class K, class FaceData>
struct Write<Triangle_soup<K, FaceData>> {
  void operator()(std::ostream& out, const Triangle_soup<K, FaceData>& t) const {
    kigumi_write<std::int32_t>(out, t.num_vertices());
    kigumi_write<std::int32_t>(out, t.num_faces());

    for (auto vi : t.vertices()) {
      const auto& p = t.point(vi);

      if (p.is_double()) {
        auto [x, y, z] = p.to_double();
        kigumi_write<bool>(out, false);
        kigumi_write<double>(out, x);
        kigumi_write<double>(out, y);
        kigumi_write<double>(out, z);
      } else {
        auto [x, y, z] = p.rational();
        kigumi_write<bool>(out, true);
        kigumi_write<Rational>(out, x);
        kigumi_write<Rational>(out, y);
        kigumi_write<Rational>(out, z);
      }
    }

    for (const auto& fi : t.faces()) {
      const auto& f = t.face(fi);
      const auto& f_data = t.data(fi);
      kigumi_write<Vertex_index>(out, f[0]);
      kigumi_write<Vertex_index>(out, f[1]);
      kigumi_write<Vertex_index>(out, f[2]);
      kigumi_write<FaceData>(out, f_data);
    }
  }
};

template <class K, class FaceData>
struct Read<Triangle_soup<K, FaceData>> {
  void operator()(std::istream& in, Triangle_soup<K, FaceData>& t) const {
    std::size_t num_vertices{};
    std::size_t num_faces{};
    kigumi_read<std::int32_t>(in, num_vertices);
    kigumi_read<std::int32_t>(in, num_faces);

    for (std::size_t i = 0; i < num_vertices; ++i) {
      bool is_exact{};
      kigumi_read<bool>(in, is_exact);

      if (!is_exact) {
        double x{};
        double y{};
        double z{};
        kigumi_read<double>(in, x);
        kigumi_read<double>(in, y);
        kigumi_read<double>(in, z);
        t.add_vertex({x, y, z});
      } else {
        Rational x;
        Rational y;
        Rational z;
        kigumi_read<Rational>(in, x);
        kigumi_read<Rational>(in, y);
        kigumi_read<Rational>(in, z);
        t.add_vertex({x, y, z});
      }
    }

    for (std::size_t i = 0; i < num_faces; ++i) {
      Face face{};
      FaceData f_data{};
      kigumi_read<Vertex_index>(in, face[0]);
      kigumi_read<Vertex_index>(in, face[1]);
      kigumi_read<Vertex_index>(in, face[2]);
      kigumi_read<FaceData>(in, f_data);
      auto fi = t.add_face(face);
      t.data(fi) = f_data;
    }
  }
};

}  // namespace kigumi
