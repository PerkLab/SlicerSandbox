#pragma once

#include <kigumi/Point_list.h>
#include <kigumi/Triangle_region.h>
#include <kigumi/kernel/enum.h>
#include <kigumi/kernel/predicates.h>

#include <algorithm>
#include <array>
#include <boost/container/static_vector.hpp>
#include <boost/container_hash/hash.hpp>
#include <boost/unordered/unordered_flat_map.hpp>
#include <utility>
#include <vector>

namespace kigumi {

template <class K>
class Face_face_intersection {
  using Orientation_3_key = std::array<std::size_t, 4>;
  using Orientation_3_key_hash = boost::hash<Orientation_3_key>;
  using Orientation_3_map =
      boost::unordered_flat_map<Orientation_3_key, Orientation, Orientation_3_key_hash>;
  using Point_list = kigumi::Point_list<K>;

 public:
  explicit Face_face_intersection(const Point_list& points) : points_(points) {}

  boost::container::static_vector<Triangle_region, 6> operator()(std::size_t a, std::size_t b,
                                                                 std::size_t c, std::size_t p,
                                                                 std::size_t q,
                                                                 std::size_t r) const {
    intersections_.clear();
    orientation_3_cache_.clear();

    auto fabc = Triangle_region::LEFT_FACE;
    auto fpqr = Triangle_region::RIGHT_FACE;

    auto [eab, ebc, eca] = face_edges(fabc);
    auto [epq, eqr, erp] = face_edges(fpqr);

    auto apqr = orientation(a, p, q, r);
    auto bpqr = orientation(b, p, q, r);
    auto cpqr = orientation(c, p, q, r);
    auto pabc = orientation(p, a, b, c);
    auto qabc = orientation(q, a, b, c);
    auto rabc = orientation(r, a, b, c);

    edge_face_intersection(eab, a, b, fpqr, p, q, r, apqr, bpqr);
    edge_face_intersection(ebc, b, c, fpqr, p, q, r, bpqr, cpqr);
    edge_face_intersection(eca, c, a, fpqr, p, q, r, cpqr, apqr);
    edge_face_intersection(epq, p, q, fabc, a, b, c, pabc, qabc);
    edge_face_intersection(eqr, q, r, fabc, a, b, c, qabc, rabc);
    edge_face_intersection(erp, r, p, fabc, a, b, c, rabc, pabc);

    boost::container::static_vector<Triangle_region, 6> result;

    if (intersections_.size() <= 2) {
      for (const auto& inter : intersections_) {
        result.push_back(convex_hull(inter.first, inter.second));
      }
    } else {
      boost::container::static_vector<std::pair<std::size_t, std::size_t>, 6> edges;
      auto size = intersections_.size();
      for (std::size_t i = 0; i < size - 1; ++i) {
        auto ri = intersections_.at(i);
        for (std::size_t j = i + 1; j < size; ++j) {
          auto rj = intersections_.at(j);
          if (dimension(convex_hull(ri.first, rj.first)) == 1 ||
              dimension(convex_hull(ri.second, rj.second)) == 1) {
            edges.emplace_back(i, j);
          }
        }
      }

      boost::container::static_vector<bool, 6> visited(size, false);
      std::size_t i{};
      while (true) {
        const auto& inter = intersections_.at(i);
        result.push_back(convex_hull(inter.first, inter.second));
        visited.at(i) = true;

        if (result.size() == size) {
          break;
        }

        for (auto [j, k] : edges) {
          if (j == i && !visited.at(k)) {
            i = k;
            break;
          }
          if (k == i && !visited.at(j)) {
            i = j;
            break;
          }
        }
      }
    }

    return result;
  }

 private:
  // 1. a, p, q, r: inclusive; b: exclusive.
  // 2. The cases where va is in the interior of epq, eqr, or erp are handled,
  //    while the cases where vp, vq, or vr is in the interior of eab are not.
  // 3. Intersections between regions of the same dimension are handled only if
  //    eab and fpqr are left and right regions, respectively.
  void edge_face_intersection(Triangle_region eab, std::size_t a, std::size_t b,
                              Triangle_region fpqr, std::size_t p, std::size_t q, std::size_t r,
                              Orientation apqr, Orientation bpqr) const {
    if (apqr * bpqr > 0) {
      // No intersections.
      return;
    }

    if (apqr == 0 && bpqr == 0) {
      edge_face_intersection_2d(eab, a, b, fpqr, p, q, r);
      return;
    }

    auto abpq = orientation(a, b, p, q);
    auto abqr = orientation(a, b, q, r);
    auto abrp = orientation(a, b, r, p);

    if (abpq * abqr < 0 || abqr * abrp < 0 || abrp * abpq < 0) {
      // No intersections.
      return;
    }

    auto [va, vb] = edge_vertices(eab);
    auto [epq, eqr, erp] = face_edges(fpqr);
    auto [vp, vq, vr] = face_vertices(fpqr);

    auto first = eab;
    if (apqr == 0) {
      first = va;
    } else if (bpqr == 0) {
      // Case 1.
      return;
    }

    auto second = fpqr;
    if (abpq == 0 && abqr == 0) {
      second = vq;
    } else if (abqr == 0 && abrp == 0) {
      second = vr;
    } else if (abrp == 0 && abpq == 0) {
      second = vp;
    } else if (abpq == 0) {
      second = epq;
    } else if (abqr == 0) {
      second = eqr;
    } else if (abrp == 0) {
      second = erp;
    }

    if (dimension(first) == 1 && dimension(second) == 0) {
      // Case 2.
      return;
    }

    if (dimension(first) == dimension(second) && !is_left_region(first)) {
      // Case 3.
      return;
    }

    insert(first, second);
  }

  // 1. a, p, q, r: inclusive; b: exclusive.
  // 2. The cases where va is in the interior of epq, eqr, or erp are handled,
  //    while the cases where vp, vq, or vr is in the interior of eab are not.
  // 3. Intersections between regions of the same dimension are handled only if
  //    eab and fpqr are left and right regions, respectively.
  void edge_face_intersection_2d(Triangle_region eab, std::size_t a, std::size_t b,
                                 Triangle_region fpqr, std::size_t p, std::size_t q,
                                 std::size_t r) const {
    auto [va, vb] = edge_vertices(eab);

    auto apq = orientation(a, p, q);
    auto aqr = orientation(a, q, r);
    auto arp = orientation(a, r, p);
    auto bpq = orientation(b, p, q);
    auto bqr = orientation(b, q, r);
    auto brp = orientation(b, r, p);

    auto vertex_face_intersections = 0;
    if (apq * aqr > 0 && aqr * arp > 0 && arp * apq > 0) {
      insert(va, fpqr);
      ++vertex_face_intersections;
    }
    if (bpq * bqr > 0 && bqr * brp > 0 && brp * bpq > 0) {
      // Case 1.
      ++vertex_face_intersections;
    }
    if (vertex_face_intersections == 2) {
      return;
    }

    auto [epq, eqr, erp] = face_edges(fpqr);

    auto abp = orientation(a, b, p);
    auto abq = orientation(a, b, q);
    auto abr = orientation(a, b, r);

    edge_edge_intersection_2d(eab, a, b, epq, p, q, abp, abq, apq, bpq);
    edge_edge_intersection_2d(eab, a, b, eqr, q, r, abq, abr, aqr, bqr);
    edge_edge_intersection_2d(eab, a, b, erp, r, p, abr, abp, arp, brp);
  }

  // 1. a, p: inclusive; b, q: exclusive.
  // 2. The case where va is in the interior of epq is handled,
  //    while the case where vp is in the interior of eab is not.
  // 3. Intersections between regions of the same dimension are handled only if
  //    eab and epq are left and right regions, respectively.
  void edge_edge_intersection_2d(Triangle_region eab, std::size_t a, std::size_t b,
                                 Triangle_region epq, std::size_t p, std::size_t q,
                                 Orientation abp, Orientation abq,
                                 Orientation apq, Orientation bpq) const {
    if (abp * abq > 0 || apq * bpq > 0) {
      // No intersections.
      return;
    }

    if (abp == 0 && abq == 0) {
      edge_edge_intersection_1d(eab, a, b, epq, p, q);
      return;
    }

    auto [va, vb] = edge_vertices(eab);
    auto [vp, vq] = edge_vertices(epq);

    auto first = eab;
    if (apq == 0) {
      first = va;
    } else if (bpq == 0) {
      // Case 1.
      return;
    }

    auto second = epq;
    if (abp == 0) {
      second = vp;
    } else if (abq == 0) {
      // Case 1.
      return;
    }

    if (dimension(first) == 1 && dimension(second) == 0) {
      // Case 2.
      return;
    }

    if (dimension(first) == dimension(second) && !is_left_region(first)) {
      // Case 3.
      return;
    }

    insert(first, second);
  }

  // 1. a, p: inclusive; b, q: exclusive.
  // 2. The case where va is in the interior of epq is handled,
  //    while the case where vp is in the interior of eab is not.
  // 3. Intersections between regions of the same dimension are handled only if
  //    eab and epq are left and right regions, respectively.
  void edge_edge_intersection_1d(Triangle_region eab, std::size_t a, std::size_t /*b*/,
                                 Triangle_region epq, std::size_t p, std::size_t q) const {
    auto [va, vb] = edge_vertices(eab);
    auto [vp, vq] = edge_vertices(epq);

    auto ap = orientation(a, p);
    auto aq = orientation(a, q);

    if (ap * aq > 0) {
      // No intersections.
      return;
    }

    if (ap * aq < 0) {
      insert(va, epq);
      return;
    }

    if (ap == 0 && is_left_region(va)) {
      insert(va, vp);
    }
  }

  template <std::size_t N>
  static Sign sort(std::array<std::size_t, N>& ids) {
    auto parity = POSITIVE;
    for (std::size_t i = 1; i < ids.size(); ++i) {
      auto j = i;
      while (j > 0 && ids.at(j - 1) > ids.at(j)) {
        std::swap(ids.at(j), ids.at(j - 1));
        parity = -parity;
        --j;
      }
    }
    return parity;
  }

  Orientation orientation(std::size_t a, std::size_t b) const {
    const auto& pa = points_.at(a);
    const auto& pb = points_.at(b);
    return compare_lexicographically(pa, pb);
  }

  Orientation orientation(std::size_t a, std::size_t b, std::size_t c) const {
    const auto& pa = points_.at(a);
    const auto& pb = points_.at(b);
    const auto& pc = points_.at(c);
    return coplanar_orientation(pa, pb, pc);
  }

  Orientation orientation(std::size_t a, std::size_t b, std::size_t c, std::size_t d) const {
    Orientation_3_key key{a, b, c, d};
    auto parity = sort(key);
    auto [it, inserted] = orientation_3_cache_.emplace(key, ZERO);

    if (inserted) {
      const auto& pa = points_.at(key[0]);
      const auto& pb = points_.at(key[1]);
      const auto& pc = points_.at(key[2]);
      const auto& pd = points_.at(key[3]);

      auto o = kigumi::orientation(pa, pb, pc, pd);
      it->second = o;
    }

    return parity * it->second;
  }

  void insert(Triangle_region first, Triangle_region second) const {
    if (!is_left_region(first)) {
      std::swap(first, second);
    }

    intersections_.emplace_back(first, second);
  }

  const Point_list& points_;
  mutable std::vector<std::pair<Triangle_region, Triangle_region>> intersections_;
  mutable Orientation_3_map orientation_3_cache_;
};

}  // namespace kigumi
