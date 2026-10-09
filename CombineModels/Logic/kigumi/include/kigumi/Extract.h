#pragma once

#include <kigumi/Boolean_operator.h>
#include <kigumi/Face_tag.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Mixed.h>
#include <kigumi/Triangle_soup.h>

#include <utility>
#include <vector>

namespace kigumi {

template <class K, class FaceData>
class Extract {
  using Mixed_triangle_soup = kigumi::Mixed_triangle_soup<K, FaceData>;
  using Triangle_soup = kigumi::Triangle_soup<K, FaceData>;

 public:
  Triangle_soup operator()(const Mixed_triangle_soup& m, Boolean_operator op,
                           bool prefer_first) const {
    Triangle_soup soup;
    std::vector<Vertex_index> map(m.num_vertices());

    auto e_mask = exterior_mask(op);
    auto i_mask = interior_mask(op);
    auto c_mask = coplanar_mask(op, prefer_first);
    auto o_mask = opposite_mask(op, prefer_first);

    for (auto fi : m.faces()) {
      auto mask = Mask::NONE;
      switch (m.data(fi).tag) {
        case Face_tag::EXTERIOR:
          mask = e_mask;
          break;
        case Face_tag::INTERIOR:
          mask = i_mask;
          break;
        case Face_tag::COPLANAR:
          mask = c_mask;
          break;
        case Face_tag::OPPOSITE:
          mask = o_mask;
          break;
        case Face_tag::UNKNOWN:
          break;
      }

      auto from_left = m.data(fi).from_left;
      auto output_id = from_left ? (mask & Mask::A) != Mask::NONE  //
                                 : (mask & Mask::B) != Mask::NONE;
      auto output_inv = from_left ? (mask & Mask::A_INV) != Mask::NONE  //
                                  : (mask & Mask::B_INV) != Mask::NONE;
      if (!output_id && !output_inv) {
        continue;
      }

      const auto& f = m.face(fi);
      Face new_f;
      for (std::size_t i = 0; i < 3; ++i) {
        auto vi = f.at(i);
        auto& new_vi = map.at(vi.idx());
        if (new_vi == Vertex_index{}) {
          const auto& p = m.point(vi);
          new_vi = soup.add_vertex(p);
        }
        new_f.at(i) = new_vi;
      }

      if (output_inv) {
        std::swap(new_f[1], new_f[2]);
      }

      auto new_fi = soup.add_face(new_f);
      soup.data(new_fi) = m.data(fi).data;
    }

    return soup;
  }
};

}  // namespace kigumi
