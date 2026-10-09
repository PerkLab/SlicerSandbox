#pragma once

#include <kigumi/Boolean_operator.h>
#include <kigumi/Extract.h>
#include <kigumi/Face_tag.h>
#include <kigumi/Mix.h>
#include <kigumi/Mixed.h>
#include <kigumi/Region.h>
#include <kigumi/Warnings.h>

#include <algorithm>
#include <iterator>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

namespace kigumi {

template <class K, class FaceData>
class Boolean_region_builder {
  using Extract = kigumi::Extract<K, FaceData>;
  using Mix = kigumi::Mix<K, FaceData>;
  using Mixed_face_data = kigumi::Mixed_face_data<FaceData>;
  using Mixed_triangle_soup = kigumi::Mixed_triangle_soup<K, FaceData>;
  using Point = typename K::Point_3;
  using Region = kigumi::Region<K, FaceData>;

 public:
  Boolean_region_builder(const Region& a, const Region& b) {
    first_kind_ = a.kind_;
    second_kind_ = b.kind_;

    if (a.is_empty_or_full() && b.is_empty_or_full()) {
      return;
    }

    if (a.is_empty_or_full() || b.is_empty_or_full()) {
      std::vector<Point> points;
      points.reserve(a.boundary_.num_vertices() + b.boundary_.num_vertices());
      std::transform(a.boundary_.vertices_begin(), a.boundary_.vertices_end(),
                     std::back_inserter(points), [&](auto vi) { return a.boundary_.point(vi); });
      std::transform(b.boundary_.vertices_begin(), b.boundary_.vertices_end(),
                     std::back_inserter(points), [&](auto vi) { return b.boundary_.point(vi); });

      std::vector<Face> faces;
      faces.reserve(a.boundary_.num_faces() + b.boundary_.num_faces());
      std::transform(a.boundary_.faces_begin(), a.boundary_.faces_end(), std::back_inserter(faces),
                     [&](auto fi) { return a.boundary_.face(fi); });
      std::transform(b.boundary_.faces_begin(), b.boundary_.faces_end(), std::back_inserter(faces),
                     [&](auto fi) { return b.boundary_.face(fi); });

      // std::tie is used since structured bindings cannot be captured by lambda expressions.
      Face_tag first_tag{};
      Face_tag second_tag{};
      std::tie(first_tag, second_tag) =
          a.is_empty() || b.is_full() ? std::make_pair(Face_tag::INTERIOR, Face_tag::EXTERIOR)
                                      : std::make_pair(Face_tag::EXTERIOR, Face_tag::INTERIOR);

      std::vector<Mixed_face_data> face_data;
      face_data.reserve(faces.size());
      std::transform(a.boundary_.faces_begin(), a.boundary_.faces_end(),
                     std::back_inserter(face_data), [&, first_tag](auto fi) -> Mixed_face_data {
                       return {.from_left = true, .tag = first_tag, .data = a.boundary_.data(fi)};
                     });
      std::transform(b.boundary_.faces_begin(), b.boundary_.faces_end(),
                     std::back_inserter(face_data), [&, second_tag](auto fi) -> Mixed_face_data {
                       return {.from_left = false, .tag = second_tag, .data = b.boundary_.data(fi)};
                     });

      m_ = {std::move(points), std::move(faces), std::move(face_data)};
      return;
    }

    std::tie(m_, warnings_) = Mix{}(a.boundary_, b.boundary_);
  }

  Region operator()(Boolean_operator op, bool prefer_first = true) const {
    auto soup = Extract{}(m_, op, prefer_first);
    if (soup.num_faces() != 0) {
      return Region{std::move(soup)};
    }

    if (first_kind_ == Region_kind::EMPTY || second_kind_ == Region_kind::EMPTY) {
      auto a = first_kind_ != Region_kind::EMPTY;
      auto b = second_kind_ != Region_kind::EMPTY;
      return apply(op, a, b) ? Region::full() : Region::empty();
    }

    if (first_kind_ == Region_kind::FULL || second_kind_ == Region_kind::FULL) {
      auto a = first_kind_ == Region_kind::FULL;
      auto b = second_kind_ == Region_kind::FULL;
      return apply(op, a, b) ? Region::full() : Region::empty();
    }

    switch (op) {
      case Boolean_operator::V:
      case Boolean_operator::A:
      case Boolean_operator::B:
      case Boolean_operator::C:
      case Boolean_operator::D:
        return Region::full();

      case Boolean_operator::K:
      case Boolean_operator::L:
      case Boolean_operator::M:
      case Boolean_operator::X:
      case Boolean_operator::O:
        return Region::empty();

      default:
        break;
    }

    if (op == Boolean_operator::E || op == Boolean_operator::J) {
      if (std::all_of(m_.faces_begin(), m_.faces_end(),
                      [&](auto fi) { return m_.data(fi).tag == Face_tag::COPLANAR; })) {
        return apply(op, false, false) ? Region::full() : Region::empty();
      }

      if (std::all_of(m_.faces_begin(), m_.faces_end(),
                      [&](auto fi) { return m_.data(fi).tag == Face_tag::OPPOSITE; })) {
        return apply(op, false, true) ? Region::full() : Region::empty();
      }
    }

    throw std::runtime_error("input meshes are inconsistently oriented");
  }

  Warnings warnings() const { return warnings_; }

 private:
  static bool apply(Boolean_operator op, bool a, bool b) {
    switch (op) {
      case Boolean_operator::V:  // The universe
        return true;
      case Boolean_operator::A:  // A \cup B
        return a || b;
      case Boolean_operator::B:  // (B \setminus A)^c
        return a || !b;
      case Boolean_operator::C:  // (A \setminus B)^c
        return !a || b;
      case Boolean_operator::D:  // (A \cap B)^c
        return !a || !b;
      case Boolean_operator::E:  // (A \triangle B)^c
        return a == b;
      case Boolean_operator::F:  // A^c
        return !a;
      case Boolean_operator::G:  // B^c
        return !b;
      case Boolean_operator::H:  // B
        return b;
      case Boolean_operator::I:  // A
        return a;
      case Boolean_operator::J:  // A \triangle B
        return a != b;
      case Boolean_operator::K:  // A \cap B
        return a && b;
      case Boolean_operator::L:  // A \setminus B
        return a && !b;
      case Boolean_operator::M:  // B \setminus A
        return !a && b;
      case Boolean_operator::X:  // (A \cup B)^c
        return !a && !b;
      case Boolean_operator::O:  // The empty set
        return false;
      default:
        throw std::runtime_error("invalid operator");
    }
  }

  Region_kind first_kind_;
  Region_kind second_kind_;
  Mixed_triangle_soup m_;
  Warnings warnings_{};
};

}  // namespace kigumi
