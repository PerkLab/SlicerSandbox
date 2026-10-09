#pragma once

#include <kigumi/io.h>

#include <boost/container_hash/hash.hpp>
#include <cstdint>
#include <functional>
#include <limits>

namespace kigumi {

template <class Tag>
class Index {
 public:
  Index() = default;

  explicit Index(std::size_t i) : i_{i} {}

  std::size_t idx() const { return i_; }

  bool is_valid() const { return i_ != std::numeric_limits<std::size_t>::max(); }

  bool operator==(Index other) const { return i_ == other.i_; }
  bool operator!=(Index other) const { return i_ != other.i_; }
  bool operator<(Index other) const { return i_ < other.i_; }
  bool operator<=(Index other) const { return i_ <= other.i_; }
  bool operator>(Index other) const { return i_ > other.i_; }
  bool operator>=(Index other) const { return i_ >= other.i_; }

  Index& operator++() {
    ++i_;
    return *this;
  }

  Index operator++(int) {
    Index tmp{*this};
    operator++();
    return tmp;
  }

  Index& operator--() {
    --i_;
    return *this;
  }

  Index operator--(int) {
    Index tmp{*this};
    operator--();
    return tmp;
  }

  Index& operator+=(std::size_t n) {
    i_ += n;
    return *this;
  }

 private:
  friend Read<Index>;
  friend Write<Index>;

  friend std::size_t hash_value(const Index& index) { return index.i_; }

  std::size_t i_{std::numeric_limits<std::size_t>::max()};
};

struct Face_index_tag {};
struct Vertex_index_tag {};

using Face_index = Index<Face_index_tag>;
using Vertex_index = Index<Vertex_index_tag>;

template <>
struct Write<Vertex_index> {
  void operator()(std::ostream& out, const Vertex_index& t) const {
    kigumi_write<std::int32_t>(out, t.i_);
  }
};

template <>
struct Read<Vertex_index> {
  void operator()(std::istream& in, Vertex_index& t) const { kigumi_read<std::int32_t>(in, t.i_); }
};

}  // namespace kigumi

template <>
struct std::hash<kigumi::Face_index> {
  std::size_t operator()(kigumi::Face_index fi) const noexcept { return fi.idx(); }
};

template <>
struct std::hash<kigumi::Vertex_index> {
  std::size_t operator()(kigumi::Vertex_index vi) const noexcept { return vi.idx(); }
};
