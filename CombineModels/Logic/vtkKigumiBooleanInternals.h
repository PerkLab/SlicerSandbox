// Helpers shared by vtkKigumiBooleanFilter and vtkKigumiBooleanSequenceFilter. Not part of the
// public API.

#ifndef vtkKigumiBooleanInternals_h
#define vtkKigumiBooleanInternals_h

#include <kigumi/Boolean_operator.h>
#include <kigumi/Exact_kernel.h>
#include <kigumi/Region.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/Warnings.h>
#include <kigumi/vtk_polydata.h>

#include "vtkKigumiBooleanFilter.h"
#include "vtkPolyData.h"
#include "vtkType.h"

#include <cstdint>
#include <optional>
#include <utility>
#include <vector>

namespace vtkKigumiBooleanInternals {

using K = kigumi::Exact_kernel;

// The input and the cell that a face originates from.
struct Face_source {
  std::int32_t input{-1};
  vtkIdType cell_id{-1};
};

using Region = kigumi::Region<K, Face_source>;
using Triangle_soup = kigumi::Triangle_soup<K, Face_source>;

// The region bounded by the polygons and triangle strips of polydata, which is the empty set if
// there are none.
inline Region to_region(vtkPolyData* polydata, std::int32_t input) {
  auto soup = kigumi::to_triangle_soup<K, Face_source>(
      polydata, [input](vtkIdType cell_id) { return Face_source{input, cell_id}; });
  if (soup.num_faces() == 0) {
    return Region::empty();
  }
  return Region{std::move(soup)};
}

// The kigumi operator for a vtkKigumiBooleanFilter::OperModes value, or std::nullopt for
// OPER_NONE and invalid values.
inline std::optional<kigumi::Boolean_operator> to_boolean_operator(int oper_mode) {
  switch (oper_mode) {
    case vtkKigumiBooleanFilter::OPER_UNION:
      return kigumi::Boolean_operator::UNION;
    case vtkKigumiBooleanFilter::OPER_INTERSECTION:
      return kigumi::Boolean_operator::INTERSECTION;
    case vtkKigumiBooleanFilter::OPER_DIFFERENCE:
      return kigumi::Boolean_operator::DIFFERENCE;
    case vtkKigumiBooleanFilter::OPER_DIFFERENCE2:
      return kigumi::Boolean_operator::M;
    case vtkKigumiBooleanFilter::OPER_SYMMETRIC_DIFFERENCE:
      return kigumi::Boolean_operator::SYMMETRIC_DIFFERENCE;
    default:
      return std::nullopt;
  }
}

// Sentences describing the warnings of a Boolean_region_builder.
inline std::vector<const char*> warning_messages(kigumi::Warnings warnings) {
  std::vector<const char*> messages;
  if ((warnings & kigumi::Warnings::FIRST_MESH_PARTIALLY_INTERSECTS_WITH_SECOND_MESH) !=
      kigumi::Warnings::NONE) {
    messages.push_back("The first mesh partially intersects with the second mesh.");
  }
  if ((warnings & kigumi::Warnings::SECOND_MESH_PARTIALLY_INTERSECTS_WITH_FIRST_MESH) !=
      kigumi::Warnings::NONE) {
    messages.push_back("The second mesh partially intersects with the first mesh.");
  }
  return messages;
}

}  // namespace vtkKigumiBooleanInternals

#endif
