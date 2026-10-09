#pragma once

#include <kigumi/Mesh_indices.h>

#include <array>
#include <boost/container_hash/hash.hpp>
#include <boost/unordered/unordered_flat_set.hpp>
#include <utility>

namespace kigumi {

using Halfedge = std::array<Vertex_index, 2>;
using Edge = std::array<Vertex_index, 2>;
using Face = std::array<Vertex_index, 3>;

inline Edge make_edge(Vertex_index first, Vertex_index second) {
  if (first > second) {
    std::swap(first, second);
  }

  return {first, second};
}

struct Halfedge_hash {
  std::size_t operator()(const Halfedge& he) const noexcept {
    std::size_t seed{};
    boost::hash_combine(seed, he[0].idx());
    boost::hash_combine(seed, he[1].idx());
    return seed;
  }
};

struct Edge_hash {
  std::size_t operator()(const kigumi::Edge& edge) const noexcept {
    std::size_t seed{};
    boost::hash_combine(seed, edge[0].idx());
    boost::hash_combine(seed, edge[1].idx());
    return seed;
  }
};

using Edge_set = boost::unordered_flat_set<Edge, Edge_hash>;

}  // namespace kigumi
