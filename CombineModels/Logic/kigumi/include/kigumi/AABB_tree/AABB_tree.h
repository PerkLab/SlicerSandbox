#pragma once

#include <kigumi/AABB_tree/AABB_node.h>
#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/threading.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <iterator>
#include <thread>
#include <utility>
#include <vector>

namespace kigumi {

template <class Leaf>
class AABB_tree {
  using Bbox = Bbox_3;
  using Node = AABB_node<Leaf>;
  using Node_iterator = typename std::vector<Node>::iterator;

 public:
  explicit AABB_tree(std::vector<Leaf> leaves) : leaves_{std::move(leaves)} {
    auto num_leaves = leaves_.size();
    if (num_leaves == 0) {
      return;
    }

    if (num_leaves == 1) {
      root_ = &leaves_.front();
      return;
    }

    nodes_.resize(num_leaves - 1);

    auto* root = &nodes_.front();
    root_ = root;

    build(nodes_.begin(), leaves_.begin(), leaves_.end(), 0);
  }

  template <class OutputIterator, class Query>
  void get_intersecting_leaves(OutputIterator leaves, const Query& query) const {
    auto num_leaves = leaves_.size();

    switch (num_leaves) {
      case 0:
        break;

      case 1:
        if (do_intersect(root_leaf()->bbox(), query)) {
          *leaves++ = root_leaf();
        }
        break;

      default:
        traverse(leaves, num_leaves, query, root_node());
        break;
    }
  }

 private:
  // NOLINTNEXTLINE(misc-no-recursion)
  template <class RandomAccessIterator>
  void build(Node_iterator node_it, RandomAccessIterator first, RandomAccessIterator last,
             int node_depth) {
    node_it->set_bbox(bbox_from_leaves(first, last));

    auto num_leaves = static_cast<std::size_t>(std::distance(first, last));

    switch (num_leaves) {
      case 2:  // (leaf, leaf)
        node_it->set_left_leaf(&*first);
        node_it->set_right_leaf(&*(first + 1));
        break;

      case 3:  // (leaf, node)
      {
        auto right_node_it = node_it + 1;
        auto split_axis = bbox_longest_axis(node_it->bbox());
        std::sort(first, last, [split_axis](const auto& a, const auto& b) {
          return bbox_center(a.bbox()).at(split_axis) < bbox_center(b.bbox()).at(split_axis);
        });

        node_it->set_left_leaf(&*first);
        node_it->set_right_node(&*right_node_it);

        build(right_node_it, first + 1, last, node_depth + 1);
        break;
      }

      default:  // (node, node)
      {
        auto num_left_leaves = num_leaves / 2;
        auto middle = first + num_left_leaves;
        auto left_node_it = node_it + 1;
        // The left tree requires (num_left_leaves - 1) nodes.
        auto right_node_it = node_it + num_left_leaves;
        auto split_axis = bbox_longest_axis(node_it->bbox());
        std::nth_element(first, middle, last, [split_axis](const auto& a, const auto& b) {
          return bbox_center(a.bbox()).at(split_axis) < bbox_center(b.bbox()).at(split_axis);
        });

        node_it->set_left_node(&*left_node_it);
        node_it->set_right_node(&*right_node_it);

        if (node_depth < concurrency_depth_limit_) {
          std::thread left_thread(&AABB_tree::build<RandomAccessIterator>, this, left_node_it,
                                  first, middle, node_depth + 1);
          std::thread right_thread(&AABB_tree::build<RandomAccessIterator>, this, right_node_it,
                                   middle, last, node_depth + 1);
          left_thread.join();
          right_thread.join();
        } else {
          build(left_node_it, first, middle, node_depth + 1);
          build(right_node_it, middle, last, node_depth + 1);
        }
        break;
      }
    }
  }

  template <class OutputIterator, class Query>
  // NOLINTNEXTLINE(misc-no-recursion)
  void traverse(OutputIterator leaves, std::size_t num_leaves, const Query& query,
                const Node* node) const {
    switch (num_leaves) {
      case 2:  // (leaf, leaf)
        if (do_intersect(node->left_leaf()->bbox(), query)) {
          *leaves++ = node->left_leaf();
        }
        if (do_intersect(node->right_leaf()->bbox(), query)) {
          *leaves++ = node->right_leaf();
        }
        break;

      case 3:  // (leaf, node)
        if (do_intersect(node->left_leaf()->bbox(), query)) {
          *leaves++ = node->left_leaf();
        }
        if (do_intersect(node->right_node()->bbox(), query)) {
          traverse(leaves, 2, query, node->right_node());
        }
        break;

      default:  // (node, node)
      {
        auto num_left_leaves = num_leaves / 2;
        if (do_intersect(node->left_node()->bbox(), query)) {
          traverse(leaves, num_left_leaves, query, node->left_node());
        }
        if (do_intersect(node->right_node()->bbox(), query)) {
          traverse(leaves, num_leaves - num_left_leaves, query, node->right_node());
        }
        break;
      }
    }
  }

  const Node* root_node() const { return static_cast<const Node*>(root_); }

  const Leaf* root_leaf() const { return static_cast<const Leaf*>(root_); }

  static std::array<double, 3> bbox_center(const Bbox& bbox) {
    return {(bbox.xmax() + bbox.xmin()) / 2.0, (bbox.ymax() + bbox.ymin()) / 2.0,
            (bbox.zmax() + bbox.zmin()) / 2.0};
  }

  template <class InputIterator>
  static Bbox bbox_from_leaves(InputIterator first, InputIterator last) {
    Bbox bbox;
    for (auto it = first; it != last; ++it) {
      bbox += it->bbox();
    }
    return bbox;
  }

  static int bbox_longest_axis(const Bbox& bbox) {
    std::array<double, 3> lengths{bbox.xmax() - bbox.xmin(), bbox.ymax() - bbox.ymin(),
                                  bbox.zmax() - bbox.zmin()};
    return static_cast<int>(
        std::distance(lengths.begin(), std::max_element(lengths.begin(), lengths.end())));
  }

  int concurrency_depth_limit_{
      static_cast<int>(std::log2(Threading_context::current().num_threads()))};
  std::vector<Leaf> leaves_;
  std::vector<Node> nodes_;
  const void* root_{nullptr};
};

}  // namespace kigumi
