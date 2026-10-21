#include "vtkKigumiBooleanFilter.h"

#include <kigumi/Boolean_operator.h>
#include <kigumi/Boolean_region_builder.h>
#include <kigumi/threading.h>
#include <kigumi/vtk_polydata.h>

#include "vtkCellData.h"
#include "vtkIdTypeArray.h"
#include "vtkInformation.h"
#include "vtkInformationVector.h"
#include "vtkKigumiBooleanInternals.h"
#include "vtkObjectFactory.h"
#include "vtkPolyData.h"

#include <exception>
#include <utility>

namespace {

using vtkKigumiBooleanInternals::Face_source;
using vtkKigumiBooleanInternals::K;
using vtkKigumiBooleanInternals::Triangle_soup;
using vtkKigumiBooleanInternals::to_region;

Triangle_soup concatenate(const Triangle_soup& first, const Triangle_soup& second) {
  Triangle_soup soup;
  for (const auto* part : {&first, &second}) {
    auto offset = soup.num_vertices();
    for (auto vi : part->vertices()) {
      soup.add_vertex(part->point(vi));
    }
    for (auto fi : part->faces()) {
      auto f = part->face(fi);
      for (auto& vi : f) {
        vi = kigumi::Vertex_index{vi.idx() + offset};
      }
      auto new_fi = soup.add_face(f);
      soup.data(new_fi) = part->data(fi);
    }
  }
  return soup;
}

}  // namespace

vtkStandardNewMacro(vtkKigumiBooleanFilter);

vtkKigumiBooleanFilter::vtkKigumiBooleanFilter() { this->SetNumberOfInputPorts(2); }

vtkKigumiBooleanFilter::~vtkKigumiBooleanFilter() = default;

void vtkKigumiBooleanFilter::PrintSelf(ostream& os, vtkIndent indent) {
  this->Superclass::PrintSelf(os, indent);
  os << indent << "OperMode: " << this->OperMode << "\n";
  os << indent << "PreferFirst: " << (this->PreferFirst ? "On" : "Off") << "\n";
  os << indent << "NumberOfThreads: " << this->NumberOfThreads << "\n";
}

int vtkKigumiBooleanFilter::FillInputPortInformation(int /*port*/, vtkInformation* info) {
  info->Set(vtkAlgorithm::INPUT_REQUIRED_DATA_TYPE(), "vtkPolyData");
  return 1;
}

int vtkKigumiBooleanFilter::RequestData(vtkInformation* /*request*/,
                                        vtkInformationVector** inputVector,
                                        vtkInformationVector* outputVector) {
  auto* input_a = vtkPolyData::GetData(inputVector[0]);
  auto* input_b = vtkPolyData::GetData(inputVector[1]);
  auto* output = vtkPolyData::GetData(outputVector);

  if (input_a == nullptr || input_b == nullptr || output == nullptr) {
    vtkErrorMacro(<< "Missing input or output.");
    return 0;
  }

  try {
    kigumi::Threading_options threading_options;
    if (this->NumberOfThreads > 0) {
      threading_options.set_num_threads(static_cast<std::size_t>(this->NumberOfThreads));
    }
    kigumi::Threading_context threading_context{threading_options};

    auto a = to_region(input_a, 0);
    auto b = to_region(input_b, 1);

    kigumi::Boolean_region_builder<K, Face_source> builder{a, b};

    for (const auto* message : vtkKigumiBooleanInternals::warning_messages(builder.warnings())) {
      vtkWarningMacro(<< message);
    }

    Triangle_soup soup;
    auto is_full = false;
    if (this->OperMode == OPER_NONE) {
      // The boundaries of A and B, split along their intersection.
      auto boundary_a = builder(kigumi::Boolean_operator::I, true);
      auto boundary_b = builder(kigumi::Boolean_operator::H, false);
      soup = concatenate(boundary_a.boundary(), boundary_b.boundary());
    } else {
      auto op = vtkKigumiBooleanInternals::to_boolean_operator(this->OperMode);
      if (!op) {
        vtkErrorMacro(<< "Invalid operation mode: " << this->OperMode);
        return 0;
      }
      auto result = builder(*op, this->PreferFirst);
      is_full = result.is_full();
      soup = std::move(result.boundary_unsafe());
    }

    if (is_full) {
      vtkWarningMacro(<< "The result is the entire space, which cannot be represented.");
    }

    auto polydata = kigumi::to_polydata(soup);

    auto orig_cell_ids_a = vtkSmartPointer<vtkIdTypeArray>::New();
    orig_cell_ids_a->SetName("OrigCellIdsA");
    orig_cell_ids_a->SetNumberOfValues(static_cast<vtkIdType>(soup.num_faces()));
    auto orig_cell_ids_b = vtkSmartPointer<vtkIdTypeArray>::New();
    orig_cell_ids_b->SetName("OrigCellIdsB");
    orig_cell_ids_b->SetNumberOfValues(static_cast<vtkIdType>(soup.num_faces()));
    for (auto fi : soup.faces()) {
      const auto& source = soup.data(fi);
      auto id = static_cast<vtkIdType>(fi.idx());
      orig_cell_ids_a->SetValue(id, source.input == 0 ? source.cell_id : -1);
      orig_cell_ids_b->SetValue(id, source.input == 1 ? source.cell_id : -1);
    }
    polydata->GetCellData()->AddArray(orig_cell_ids_a);
    polydata->GetCellData()->AddArray(orig_cell_ids_b);

    output->ShallowCopy(polydata);
  } catch (const std::exception& e) {
    vtkErrorMacro(<< "Boolean operation failed: " << e.what());
    return 0;
  }

  return 1;
}
