#pragma once

#include <kigumi/Face_tag.h>
#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Mixed.h>
#include <kigumi/Warnings.h>

#include <queue>

namespace kigumi {

template <class K, class FaceData>
class Propagate_face_tags {
  using Mixed_triangle_mesh = kigumi::Mixed_triangle_mesh<K, FaceData>;

 public:
  Warnings operator()(Mixed_triangle_mesh& m, const Edge_set& border_edges, Face_index seed) const {
    const auto& data = m.data(seed);
    auto from_left = data.from_left;
    auto tag = data.tag;

    Warnings warnings{};

    queue_.push(seed);
    while (!queue_.empty()) {
      auto fi = queue_.front();
      queue_.pop();

      for (auto fi2 : m.faces_around_face(fi, border_edges)) {
        auto& tag2 = m.data(fi2).tag;
        if (tag2 == Face_tag::UNKNOWN) {
          tag2 = tag;
          queue_.push(fi2);
        } else if (tag2 != tag) {
          if (from_left) {
            warnings |= Warnings::FIRST_MESH_PARTIALLY_INTERSECTS_WITH_SECOND_MESH;
          } else {
            warnings |= Warnings::SECOND_MESH_PARTIALLY_INTERSECTS_WITH_FIRST_MESH;
          }
        }
      }
    }

    return warnings;
  }

 private:
  mutable std::queue<Face_index> queue_;
};

}  // namespace kigumi
