#pragma once

#include <kigumi/kernel/Bbox_3.h>
#include <kigumi/kernel/Point_3.h>
#include <kigumi/kernel/Rational.h>
#include <kigumi/kernel/Ray_3.h>
#include <kigumi/kernel/Triangle_3.h>
#include <kigumi/kernel/constructions.h>
#include <kigumi/kernel/enum.h>
#include <kigumi/kernel/predicates.h>

namespace kigumi {

// A kernel with exact predicates and exact constructions.
//
// Predicates are first evaluated with floating-point filters, and only uncertain cases are
// evaluated exactly. Constructed points have exact rational coordinates.
struct Exact_kernel {
  using FT = Rational;
  using Point_3 = kigumi::Point_3;
  using Ray_3 = kigumi::Ray_3;
  using Triangle_3 = kigumi::Triangle_3;
};

}  // namespace kigumi
