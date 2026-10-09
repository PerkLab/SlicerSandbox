#pragma once

#include <kigumi/Face_tag.h>
#include <kigumi/Triangle_mesh.h>
#include <kigumi/Triangle_soup.h>

namespace kigumi {

template <class FaceData>
struct Mixed_face_data {
  bool from_left{};
  Face_tag tag{};
  FaceData data{};
};

template <class K, class FaceData>
using Mixed_triangle_mesh = Triangle_mesh<K, Mixed_face_data<FaceData>>;

template <class K, class FaceData>
using Mixed_triangle_soup = Triangle_soup<K, Mixed_face_data<FaceData>>;

}  // namespace kigumi
