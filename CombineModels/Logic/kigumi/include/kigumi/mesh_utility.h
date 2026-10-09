#pragma once

#include <kigumi/Mesh_indices.h>
#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/kernel/constructions.h>
#include <kigumi/kernel/enum.h>
#include <kigumi/kernel/predicates.h>

namespace kigumi {

template <class K, class FaceData>
class Triangle_soup;

template <class K, class FaceData>
class Triangle_mesh;

namespace internal {

// Facilities for avoiding construction of intermediate kernel objects.

template <class K, class FaceData>
Bbox_3 face_bbox(const Triangle_soup<K, FaceData>& m, Face_index fi) {
  const auto& f = m.face(fi);
  return m.point(f[0]).bbox() + m.point(f[1]).bbox() + m.point(f[2]).bbox();
}

template <class K, class FaceData>
typename K::Point_3 face_centroid(const Triangle_soup<K, FaceData>& m, Face_index fi) {
  const auto& f = m.face(fi);
  return centroid(m.point(f[0]), m.point(f[1]), m.point(f[2]));
}

template <class K, class FaceData>
typename K::Point_3 face_centroid(const Triangle_mesh<K, FaceData>& m, Face_index fi) {
  const auto& f = m.face(fi);
  return centroid(m.point(f[0]), m.point(f[1]), m.point(f[2]));
}

template <class K, class FaceData>
Oriented_side oriented_side_of_face_supporting_plane(const Triangle_soup<K, FaceData>& m,
                                                           Face_index fi,
                                                           const typename K::Point_3& p) {
  const auto& f = m.face(fi);
  return orientation(m.point(f[0]), m.point(f[1]), m.point(f[2]), p);
}

}  // namespace internal

}  // namespace kigumi
