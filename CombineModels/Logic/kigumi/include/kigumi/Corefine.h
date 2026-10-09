#pragma once

#include <kigumi/Face_face_intersection.h>
#include <kigumi/Face_tag.h>
#include <kigumi/Find_coplanar_faces.h>
#include <kigumi/Find_possibly_intersecting_faces.h>
#include <kigumi/Intersection_point_inserter.h>
#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Point_list.h>
#include <kigumi/Triangle_region.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/Triangulation.h>
#include <kigumi/parallel_do.h>

#include <algorithm>
#include <boost/container/static_vector.hpp>
#include <boost/iterator/function_output_iterator.hpp>
#include <boost/range/iterator_range.hpp>
#include <boost/unordered/unordered_flat_map.hpp>
#include <functional>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <tuple>
#include <utility>
#include <vector>

namespace kigumi {

template <class K, class FaceData>
class Corefine {
  using Face_face_intersection = kigumi::Face_face_intersection<K>;
  using Find_coplanar_faces = kigumi::Find_coplanar_faces<K, FaceData>;
  using Find_possibly_intersecting_faces = kigumi::Find_possibly_intersecting_faces<K, FaceData>;
  using Intersection_point_inserter = kigumi::Intersection_point_inserter<K>;
  using Point = typename K::Point_3;
  using Point_list = kigumi::Point_list<K>;
  using Triangle_soup = kigumi::Triangle_soup<K, FaceData>;
  using Triangulation = kigumi::Triangulation<K>;

 public:
  Corefine(const Triangle_soup& left, const Triangle_soup& right) : left_{left}, right_{right} {
    std::cout << "Finding face pairs..." << std::endl;

    points_.start_uniqueness_check();
    points_.reserve(left_.num_vertices() + right_.num_vertices());
    for (auto vi : left_.vertices()) {
      left_point_ids_.push_back(points_.insert(left_.point(vi)));
    }
    for (auto vi : right_.vertices()) {
      right_point_ids_.push_back(points_.insert(right_.point(vi)));
    }
    points_.stop_uniqueness_check();

    std::tie(left_face_tags_, right_face_tags_) =
        Find_coplanar_faces{}(left_, right_, left_point_ids_, right_point_ids_);

    auto pairs =
        Find_possibly_intersecting_faces{}(left_, right_, left_face_tags_, right_face_tags_);

    std::cout << "Finding symbolic intersections..." << std::endl;

    std::size_t num_intersections{};
    parallel_do(
        pairs.begin(), pairs.end(),
        [&] {
          return std::make_tuple(std::vector<Intersection_info>{}, std::size_t{},
                                 Face_face_intersection{points_});
        },
        [&](const auto& pair, auto& local_state) {
          auto& [local_infos, local_num_intersections, face_face_intersection] = local_state;
          auto [left_fi, right_fi] = pair;
          const auto& left_face = left_.face(left_fi);
          const auto& right_face = right_.face(right_fi);
          auto a = left_point_ids_.at(left_face[0].idx());
          auto b = left_point_ids_.at(left_face[1].idx());
          auto c = left_point_ids_.at(left_face[2].idx());
          auto p = right_point_ids_.at(right_face[0].idx());
          auto q = right_point_ids_.at(right_face[1].idx());
          auto r = right_point_ids_.at(right_face[2].idx());
          auto sym_inters = face_face_intersection(a, b, c, p, q, r);
          if (sym_inters.empty()) {
            return;
          }
          local_infos.emplace_back(left_fi, right_fi, sym_inters);
          local_num_intersections += sym_inters.size();
        },
        [&](auto& local_state) {
          auto& [local_infos, local_num_intersections, face_face_intersection] = local_state;
          if (infos_.empty()) {
            infos_ = std::move(local_infos);
          } else {
            infos_.insert(infos_.end(), local_infos.begin(), local_infos.end());
          }
          num_intersections += local_num_intersections;
        });

    std::cout << "Constructing intersection points..." << std::endl;

    auto num_points_before_insertion = points_.size();

    points_.reserve(num_points_before_insertion + num_intersections / 2);
    Intersection_point_inserter inserter(points_);
    for (auto& info : infos_) {
      const auto& left_face = left_.face(info.left_fi);
      const auto& right_face = right_.face(info.right_fi);
      auto a = left_point_ids_.at(left_face[0].idx());
      auto b = left_point_ids_.at(left_face[1].idx());
      auto c = left_point_ids_.at(left_face[2].idx());
      auto p = right_point_ids_.at(right_face[0].idx());
      auto q = right_point_ids_.at(right_face[1].idx());
      auto r = right_point_ids_.at(right_face[2].idx());
      for (auto sym_inter : info.symbolic_intersections) {
        auto left_region = intersection(sym_inter, Triangle_region::LEFT_FACE);
        auto right_region = intersection(sym_inter, Triangle_region::RIGHT_FACE);
        auto id = inserter.insert(left_region, a, b, c, right_region, p, q, r);
        info.intersections.push_back(id);
      }
    }

    inserter.construct_pending_points();

    std::cout << "Triangulating..." << std::endl;

    auto left_fi_less = [](const Intersection_info& a, const Intersection_info& b) -> bool {
      return a.left_fi < b.left_fi;
    };
    std::sort(infos_.begin(), infos_.end(), left_fi_less);

    std::vector<boost::iterator_range<typename decltype(infos_)::const_iterator>> ranges;
    for (auto first = infos_.begin(); first != infos_.end();) {
      auto last = std::upper_bound(first + 1, infos_.end(), *first, left_fi_less);
      ranges.emplace_back(first, last);
      first = last;
    }

    left_triangulations_.reserve(ranges.size());
    for (const auto& range : ranges) {
      const auto& any_info = range.front();
      auto fi = any_info.left_fi;
      left_triangulations_.emplace(fi, std::nullopt);
    }

    try {
      parallel_do(ranges.begin(), ranges.end(), [&](const auto& range) {
        const auto& any_info = range.front();
        auto fi = any_info.left_fi;
        const auto& f = left_.face(fi);
        auto a = left_point_ids_.at(f[0].idx());
        auto b = left_point_ids_.at(f[1].idx());
        auto c = left_point_ids_.at(f[2].idx());

        auto& triangulation =
            left_triangulations_.at(fi).emplace(points_, Triangle_region::LEFT_FACE, a, b, c);
        for (const auto& info : range) {
          insert_intersection(triangulation, info);
        }
      });
    } catch (const typename Triangulation::Intersection_of_constraints_exception&) {
      throw std::runtime_error("the second mesh has self-intersections");
    }

    auto right_fi_less = [](const Intersection_info& a, const Intersection_info& b) -> bool {
      return a.right_fi < b.right_fi;
    };
    std::sort(infos_.begin(), infos_.end(), right_fi_less);

    ranges.clear();
    for (auto first = infos_.begin(); first != infos_.end();) {
      auto last = std::upper_bound(first + 1, infos_.end(), *first, right_fi_less);
      ranges.emplace_back(first, last);
      first = last;
    }

    right_triangulations_.reserve(ranges.size());
    for (const auto& range : ranges) {
      const auto& any_info = range.front();
      auto fi = any_info.right_fi;
      right_triangulations_.emplace(fi, std::nullopt);
    }

    try {
      parallel_do(ranges.begin(), ranges.end(), [&](const auto& range) {
        const auto& any_info = range.front();
        auto fi = any_info.right_fi;
        const auto& f = right_.face(fi);
        auto a = right_point_ids_.at(f[0].idx());
        auto b = right_point_ids_.at(f[1].idx());
        auto c = right_point_ids_.at(f[2].idx());

        auto& triangulation = right_triangulations_.at(any_info.right_fi)
                                  .emplace(points_, Triangle_region::RIGHT_FACE, a, b, c);
        for (const auto& info : range) {
          insert_intersection(triangulation, info);
        }
      });
    } catch (const typename Triangulation::Intersection_of_constraints_exception&) {
      throw std::runtime_error("the first mesh has self-intersections");
    }
  }

  Edge_set get_intersecting_edges() const {
    Edge_set edges;

    for (const auto& info : infos_) {
      auto n = info.intersections.size();
      if (n < 2) {
        continue;
      }

      for (std::size_t i = 0; i < n; ++i) {
        auto j = i < n - 1 ? i + 1 : 0;
        auto a = info.intersections.at(i);
        auto b = info.intersections.at(j);
        edges.insert(make_edge(Vertex_index{a}, Vertex_index{b}));
      }
    }

    return edges;
  }

  template <class OutputIterator>
  std::pair<Face_tag, std::size_t> get_left_faces(Face_index fi, OutputIterator faces) const {
    auto tag = left_face_tags_.at(fi.idx());
    auto count = get_faces(left_, fi, left_triangulations_, left_point_ids_, faces);
    return {tag, count};
  }

  template <class OutputIterator>
  std::pair<Face_tag, std::size_t> get_right_faces(Face_index fi, OutputIterator faces) const {
    auto tag = right_face_tags_.at(fi.idx());
    auto count = get_faces(right_, fi, right_triangulations_, right_point_ids_, faces);
    return {tag, count};
  }

  std::vector<Point> take_points() { return points_.take_points(); }

 private:
  struct Intersection_info {
    Face_index left_fi;
    Face_index right_fi;
    boost::container::static_vector<Triangle_region, 6> symbolic_intersections;
    boost::container::static_vector<std::size_t, 6> intersections;
  };

  template <class OutputIterator>
  std::size_t get_faces(const Triangle_soup& soup, Face_index fi,
                        const boost::unordered_flat_map<Face_index, std::optional<Triangulation>,
                                                        std::hash<Face_index>>& triangulations,
                        const std::vector<std::size_t>& point_ids, OutputIterator faces) const {
    auto it = triangulations.find(fi);
    if (it != triangulations.end()) {
      return it->second.value().get_faces(
          boost::make_function_output_iterator([&](const auto& face) {
            auto [a, b, c] = face;
            *faces++ = {Vertex_index{a}, Vertex_index{b}, Vertex_index{c}};
          }));
    }

    const auto& f = soup.face(fi);
    auto a = Vertex_index{point_ids.at(f[0].idx())};
    auto b = Vertex_index{point_ids.at(f[1].idx())};
    auto c = Vertex_index{point_ids.at(f[2].idx())};
    *faces++ = {a, b, c};
    return 1;
  }

  void insert_intersection(Triangulation& triangulation, const Intersection_info& info) {
    using Vertex_handle = typename Triangulation::Vertex_handle;
    Vertex_handle first{};
    Vertex_handle last{};
    for (std::size_t i = 0; i < info.intersections.size(); ++i) {
      auto id = info.intersections.at(i);
      auto sym = info.symbolic_intersections.at(i);
      auto cur = triangulation.insert(id, sym);
      if (i == 0) {
        first = cur;
      } else {
        triangulation.insert_constraint(last, cur);
      }
      last = cur;
    }
    if (info.intersections.size() > 2) {
      triangulation.insert_constraint(last, first);
    }
  }

  const Triangle_soup& left_;
  boost::unordered_flat_map<Face_index, std::optional<Triangulation>, std::hash<Face_index>>
      left_triangulations_;
  const Triangle_soup& right_;
  boost::unordered_flat_map<Face_index, std::optional<Triangulation>, std::hash<Face_index>>
      right_triangulations_;
  Point_list points_;
  std::vector<std::size_t> left_point_ids_;
  std::vector<std::size_t> right_point_ids_;
  std::vector<Face_tag> left_face_tags_;
  std::vector<Face_tag> right_face_tags_;
  std::vector<Intersection_info> infos_;
};

}  // namespace kigumi
