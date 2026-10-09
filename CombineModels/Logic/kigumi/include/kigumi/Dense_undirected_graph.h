#pragma once

#include <algorithm>
#include <stack>
#include <stdexcept>
#include <utility>
#include <vector>

namespace kigumi {

class dense_undirected_graph {
  using Value = unsigned;

 public:
  explicit dense_undirected_graph(std::size_t order) : order_{order}, m_(order * (order + 1) / 2) {}

  void add_edge(std::size_t i, std::size_t j) { at(i, j)++; }

  Value degree(std::size_t i) const {
    Value d = 0;
    for (std::size_t j = 0; j < order_; j++) {
      d += at(i, j);
    }
    return d;
  }

  bool has_edge(std::size_t i, std::size_t j) const { return at(i, j) != 0; }

  bool is_connected() const {
    std::vector<bool> visited(order_);
    std::stack<std::size_t> stack;

    stack.push(0);
    while (!stack.empty()) {
      auto i = stack.top();
      stack.pop();
      visited.at(i) = true;

      for (std::size_t j = 0; j < order_; j++) {
        if (has_edge(i, j) && !visited.at(j)) {
          stack.push(j);
        }
      }
    }

    return std::find(visited.begin(), visited.end(), false) == visited.end();
  }

  bool is_simple() const {
    for (std::size_t i = 0; i < order_; ++i) {
      if (at(i, i) != 0) {
        return false;
      }

      for (std::size_t j = i + 1; j < order_; ++j) {
        if (at(i, j) > 1) {
          return false;
        }
      }
    }

    return true;
  }

  Value max_degree() const {
    Value d = 0;
    for (std::size_t i = 0; i < order_; i++) {
      d = std::max(d, degree(i));
    }
    return d;
  }

  std::size_t order() const { return order_; }

 private:
  Value& at(std::size_t i, std::size_t j) {
    if (i >= order_) {
      throw std::out_of_range{"i"};
    }
    if (j >= order_) {
      throw std::out_of_range{"j"};
    }
    if (i > j) {
      std::swap(i, j);
    }
    return m_.at(order_ * i + j - i * (i + 1) / 2);
  }

  const Value& at(std::size_t i, std::size_t j) const {
    if (i >= order_) {
      throw std::out_of_range{"i"};
    }
    if (j >= order_) {
      throw std::out_of_range{"j"};
    }
    if (i > j) {
      std::swap(i, j);
    }
    return m_.at(order_ * i + j - i * (i + 1) / 2);
  }

  std::size_t order_;
  std::vector<Value> m_;
};

}  // namespace kigumi
