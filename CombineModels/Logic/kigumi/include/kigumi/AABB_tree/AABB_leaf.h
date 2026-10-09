#pragma once

#include <kigumi/kernel/Bbox_3.h>

namespace kigumi {

class AABB_leaf {
  using Bbox = Bbox_3;

 public:
  explicit AABB_leaf(const Bbox& bbox) : bbox_{bbox} {}

  const Bbox& bbox() const { return bbox_; }

 private:
  Bbox bbox_;
};

}  // namespace kigumi
