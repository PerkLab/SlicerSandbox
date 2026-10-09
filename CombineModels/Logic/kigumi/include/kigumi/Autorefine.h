#pragma once

#include <kigumi/Corefine.h>
#include <kigumi/Find_defects.h>
#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Triangle_soup.h>

#include <algorithm>
#include <iterator>
#include <limits>
#include <utility>
#include <vector>

namespace kigumi {

template <class K, class FaceData>
class Autorefine {
  using Point = typename K::Point_3;
  using Triangle_soup = kigumi::Triangle_soup<K, FaceData>;

 public:
  Triangle_soup operator()(const Triangle_soup& soup) const {
    Find_defects defects{soup};
    auto& trivial_degenerate = defects.trivial_degenerate_faces();
    auto& non_trivial_degenerate = defects.non_trivial_degenerate_faces();
    auto& overlapping = defects.overlapping_faces();

    constexpr auto kNoPart = std::numeric_limits<std::size_t>::max();
    std::vector<std::size_t> part(soup.num_faces(), kNoPart);
    std::size_t num_parts = 0;

    std::vector<Face_index> seen;
    for (auto fi : soup.faces()) {
      if (trivial_degenerate.contains(fi) || non_trivial_degenerate.contains(fi)) {
        continue;
      }

      auto it = overlapping.find(fi);
      if (it != overlapping.end()) {
        for (auto fi2 : it->second) {
          auto pt2 = part.at(fi2.idx());
          if (pt2 == kNoPart) {
            continue;
          }
          if (pt2 >= seen.size()) {
            seen.resize(pt2 + 1);
          }
          seen.at(pt2) = fi;
        }
      }

      auto& pt = part.at(fi.idx());
      auto it2 = std::find_if(seen.begin(), seen.end(), [fi](auto s) { return s != fi; });
      pt = static_cast<std::size_t>(std::distance(seen.begin(), it2));
      num_parts = std::max(num_parts, pt + 1);
    }

    if (num_parts == 0) {
      return {};
    }

    auto get_part = [&](std::size_t pt) {
      std::vector<Point> points;
      std::vector<Face> faces;
      std::vector<FaceData> face_data;
      std::vector<Vertex_index> vv(soup.num_vertices());
      for (auto fi : soup.faces()) {
        if (part.at(fi.idx()) != pt) {
          continue;
        }

        auto& f = soup.face(fi);
        Face g;
        for (std::size_t i = 0; i < 3; ++i) {
          auto v = f.at(i);
          auto& w = vv.at(v.idx());
          if (w == Vertex_index{}) {
            w = Vertex_index{points.size()};
            points.push_back(soup.point(v));
          }
          g.at(i) = w;
        }

        faces.push_back(g);
        face_data.push_back(soup.data(fi));
      }

      return Triangle_soup{std::move(points), std::move(faces), std::move(face_data)};
    };

    auto left = get_part(0);

    for (std::size_t pt = 1; pt < num_parts; ++pt) {
      auto right = get_part(pt);
      Corefine corefine{left, right};

      std::vector<Face> faces;
      std::vector<FaceData> face_data;
      for (auto fi : left.faces()) {
        auto [_, count] = corefine.get_left_faces(fi, std::back_inserter(faces));
        face_data.resize(face_data.size() + count, left.data(fi));
      }
      for (auto fi : right.faces()) {
        auto [_, count] = corefine.get_right_faces(fi, std::back_inserter(faces));
        face_data.resize(face_data.size() + count, right.data(fi));
      }

      left = {corefine.take_points(), std::move(faces), std::move(face_data)};
    }

    return left;
  }
};

template <class K, class FaceData>
Triangle_soup<K, FaceData> autorefine(const Triangle_soup<K, FaceData>& soup) {
  return Autorefine<K, FaceData>{}(soup);
}

}  // namespace kigumi
