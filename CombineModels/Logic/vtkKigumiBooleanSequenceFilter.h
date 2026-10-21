/**
 * @class vtkKigumiBooleanSequenceFilter
 * @brief Exact multi-step Boolean operations on polygonal meshes using kigumi.
 *
 * Combines the regions bounded by the meshes on the repeatable input port 0 from left to right:
 * the result is (((I0 op1 I1) op2 I2) ... opN-1 IN-1), where Ii is input i and opi is the
 * operation set for it with SetOperation(). Intermediate results are kept exact, and only the
 * final result is rounded to doubles. Chaining vtkKigumiBooleanFilter instead rounds after every
 * step, which can make the meshes self-intersect and the following steps fail.
 *
 * Inputs must meet the requirements of vtkKigumiBooleanFilter. An input without polygons
 * represents the empty set. Without inputs, the output is empty.
 *
 * The output is a triangle mesh with the cell data arrays "OrigInputIds" and "OrigCellIds", which
 * hold the index of the input and the id of the input cell each output triangle originates from
 * (-1 if none).
 */

#ifndef vtkKigumiBooleanSequenceFilter_h
#define vtkKigumiBooleanSequenceFilter_h

#include "vtkSlicerCombineModelsModuleLogicExport.h"
#include "vtkPolyDataAlgorithm.h"

#include <vector>  // For std::vector

class VTK_SLICER_COMBINEMODELS_MODULE_LOGIC_EXPORT vtkKigumiBooleanSequenceFilter : public vtkPolyDataAlgorithm {
 public:
  static vtkKigumiBooleanSequenceFilter* New();
  vtkTypeMacro(vtkKigumiBooleanSequenceFilter, vtkPolyDataAlgorithm);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  ///@{
  /**
   * The operation that combines the result of the previous steps (the first operand) with input
   * inputIndex (the second operand): a vtkKigumiBooleanFilter::OperModes value other than
   * OPER_NONE. OPER_DIFFERENCE subtracts the input from the result, and OPER_DIFFERENCE2 subtracts
   * the result from the input. Input 0 has no operation. Inputs whose operation is not set are
   * united with the result.
   */
  void SetOperation(int inputIndex, int operMode);
  int GetOperation(int inputIndex) const;
  void RemoveAllOperations();
  ///@}

  ///@{
  /**
   * Where the boundaries of the result and the next input overlap with the same orientation, keep
   * the faces of the result if on (the default), or those of the input otherwise. This only
   * affects the cell data.
   */
  vtkSetMacro(PreferFirst, bool);
  vtkGetMacro(PreferFirst, bool);
  vtkBooleanMacro(PreferFirst, bool);
  ///@}

  ///@{
  /**
   * The maximum number of threads to use. 0 (the default) uses all hardware threads.
   */
  vtkSetClampMacro(NumberOfThreads, int, 0, VTK_INT_MAX);
  vtkGetMacro(NumberOfThreads, int);
  ///@}

 protected:
  vtkKigumiBooleanSequenceFilter();
  ~vtkKigumiBooleanSequenceFilter() override;

  int FillInputPortInformation(int port, vtkInformation* info) override;
  int RequestData(vtkInformation* request, vtkInformationVector** inputVector,
                  vtkInformationVector* outputVector) override;

 private:
  vtkKigumiBooleanSequenceFilter(const vtkKigumiBooleanSequenceFilter&) = delete;
  void operator=(const vtkKigumiBooleanSequenceFilter&) = delete;

  // Operations[i] is the operation of input i.
  std::vector<int> Operations;
  bool PreferFirst = true;
  int NumberOfThreads = 0;
};

#endif
