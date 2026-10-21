#include "vtkKigumiBooleanSequenceFilter.h"

#include <kigumi/Boolean_region_builder.h>
#include <kigumi/threading.h>
#include <kigumi/vtk_polydata.h>

#include "vtkCellData.h"
#include "vtkIdTypeArray.h"
#include "vtkInformation.h"
#include "vtkInformationVector.h"
#include "vtkKigumiBooleanFilter.h"
#include "vtkKigumiBooleanInternals.h"
#include "vtkObjectFactory.h"
#include "vtkPolyData.h"

#include <cstdint>
#include <exception>
#include <utility>

using vtkKigumiBooleanInternals::Face_source;
using vtkKigumiBooleanInternals::K;
using vtkKigumiBooleanInternals::Region;
using vtkKigumiBooleanInternals::to_region;

vtkStandardNewMacro(vtkKigumiBooleanSequenceFilter);

vtkKigumiBooleanSequenceFilter::vtkKigumiBooleanSequenceFilter() = default;

vtkKigumiBooleanSequenceFilter::~vtkKigumiBooleanSequenceFilter() = default;

void vtkKigumiBooleanSequenceFilter::PrintSelf(ostream& os, vtkIndent indent) {
  this->Superclass::PrintSelf(os, indent);
  os << indent << "Operations:";
  for (std::size_t i = 1; i < this->Operations.size(); ++i) {
    os << " " << this->Operations[i];
  }
  os << "\n";
  os << indent << "PreferFirst: " << (this->PreferFirst ? "On" : "Off") << "\n";
  os << indent << "NumberOfThreads: " << this->NumberOfThreads << "\n";
}

void vtkKigumiBooleanSequenceFilter::SetOperation(int inputIndex, int operMode) {
  if (inputIndex < 1) {
    vtkErrorMacro(<< "Input " << inputIndex << " has no operation.");
    return;
  }
  if (!vtkKigumiBooleanInternals::to_boolean_operator(operMode)) {
    vtkErrorMacro(<< "Invalid operation mode: " << operMode);
    return;
  }
  auto index = static_cast<std::size_t>(inputIndex);
  if (index >= this->Operations.size()) {
    this->Operations.resize(index + 1, vtkKigumiBooleanFilter::OPER_UNION);
  } else if (this->Operations[index] == operMode) {
    return;
  }
  this->Operations[index] = operMode;
  this->Modified();
}

int vtkKigumiBooleanSequenceFilter::GetOperation(int inputIndex) const {
  if (inputIndex < 1 || static_cast<std::size_t>(inputIndex) >= this->Operations.size()) {
    return vtkKigumiBooleanFilter::OPER_UNION;
  }
  return this->Operations[static_cast<std::size_t>(inputIndex)];
}

void vtkKigumiBooleanSequenceFilter::RemoveAllOperations() {
  if (!this->Operations.empty()) {
    this->Operations.clear();
    this->Modified();
  }
}

int vtkKigumiBooleanSequenceFilter::FillInputPortInformation(int /*port*/, vtkInformation* info) {
  info->Set(vtkAlgorithm::INPUT_REQUIRED_DATA_TYPE(), "vtkPolyData");
  info->Set(vtkAlgorithm::INPUT_IS_REPEATABLE(), 1);
  info->Set(vtkAlgorithm::INPUT_IS_OPTIONAL(), 1);
  return 1;
}

int vtkKigumiBooleanSequenceFilter::RequestData(vtkInformation* /*request*/,
                                                vtkInformationVector** inputVector,
                                                vtkInformationVector* outputVector) {
  auto* output = vtkPolyData::GetData(outputVector);
  if (output == nullptr) {
    vtkErrorMacro(<< "Missing output.");
    return 0;
  }

  auto num_inputs = inputVector[0]->GetNumberOfInformationObjects();
  // The input that is being combined with the result, for error messages.
  int step = 0;

  try {
    kigumi::Threading_options threading_options;
    if (this->NumberOfThreads > 0) {
      threading_options.set_num_threads(static_cast<std::size_t>(this->NumberOfThreads));
    }
    kigumi::Threading_context threading_context{threading_options};

    auto result = num_inputs == 0 ? Region::empty()
                                  : to_region(vtkPolyData::GetData(inputVector[0], 0), 0);

    for (step = 1; step < num_inputs; ++step) {
      auto op = vtkKigumiBooleanInternals::to_boolean_operator(this->GetOperation(step));
      auto next = to_region(vtkPolyData::GetData(inputVector[0], step),
                            static_cast<std::int32_t>(step));

      // The builder holds the corefined meshes, so free it before the next step.
      kigumi::Boolean_region_builder<K, Face_source> builder{result, next};
      for (const auto* message :
           vtkKigumiBooleanInternals::warning_messages(builder.warnings())) {
        vtkWarningMacro(<< "Step " << step << " (the result of the previous steps and input "
                        << step << "): " << message);
      }
      result = builder(*op, this->PreferFirst);

      this->UpdateProgress(static_cast<double>(step) / (num_inputs - 1));
    }

    if (result.is_full()) {
      vtkWarningMacro(<< "The result is the entire space, which cannot be represented.");
    }

    const auto& soup = result.boundary();
    auto polydata = kigumi::to_polydata(soup);

    auto orig_input_ids = vtkSmartPointer<vtkIdTypeArray>::New();
    orig_input_ids->SetName("OrigInputIds");
    orig_input_ids->SetNumberOfValues(static_cast<vtkIdType>(soup.num_faces()));
    auto orig_cell_ids = vtkSmartPointer<vtkIdTypeArray>::New();
    orig_cell_ids->SetName("OrigCellIds");
    orig_cell_ids->SetNumberOfValues(static_cast<vtkIdType>(soup.num_faces()));
    for (auto fi : soup.faces()) {
      const auto& source = soup.data(fi);
      auto id = static_cast<vtkIdType>(fi.idx());
      orig_input_ids->SetValue(id, source.input);
      orig_cell_ids->SetValue(id, source.cell_id);
    }
    polydata->GetCellData()->AddArray(orig_input_ids);
    polydata->GetCellData()->AddArray(orig_cell_ids);

    output->ShallowCopy(polydata);
  } catch (const std::exception& e) {
    vtkErrorMacro(<< "Boolean operation failed at step " << step << " (combining input " << step
                  << "): " << e.what());
    return 0;
  }

  return 1;
}
