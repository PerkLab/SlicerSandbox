/**
 * @class vtkOctreeBooleanFilter
 * @brief Boolean operations on closed surfaces, computed on adaptive octrees of voxels.
 *
 * Combines the regions bounded by the meshes on the repeatable input port 0 from left to right:
 * the result is (((I0 op1 I1) op2 I2) ... opN-1 IN-1), where Ii is input i and opi is the
 * operation set for it with SetOperation(), as in vtkKigumiBooleanSequenceFilter.
 *
 * Each input is scan-converted on voxels split 2^ExtraLevels times along each axis, and stored
 * as octrees (vtkHyperTreeGrid) that are only refined near the surface. The octrees are combined
 * cell by cell. The output is the iso-surface of the fraction of each voxel that the result
 * covers, at 0.5: a closed triangle mesh, accurate to a fraction of a voxel, which rounds sharp
 * edges and loses features thinner than a voxel. The voxels are axis-aligned and cover the
 * bounds of the result with a margin of 2 voxels.
 *
 * A point is inside an input if a ray from it crosses the surface an odd number of times. So the
 * orientation of the faces, self-intersections and non-manifold edges do not matter, but
 * overlapping parts of one input cancel out, and holes in the surface make the inside leak.
 * An input without polygons represents the empty set. Without inputs, the output is empty.
 */

#ifndef vtkOctreeBooleanFilter_h
#define vtkOctreeBooleanFilter_h

#include "vtkSlicerCombineModelsModuleLogicExport.h"
#include "vtkPolyDataAlgorithm.h"

#include <vector>  // For std::vector

class VTK_SLICER_COMBINEMODELS_MODULE_LOGIC_EXPORT vtkOctreeBooleanFilter : public vtkPolyDataAlgorithm {
 public:
  static vtkOctreeBooleanFilter* New();
  vtkTypeMacro(vtkOctreeBooleanFilter, vtkPolyDataAlgorithm);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  enum OperModes {
    OPER_NONE = 0,
    OPER_UNION,
    OPER_INTERSECTION,
    OPER_DIFFERENCE,  // first operand minus the second
    OPER_DIFFERENCE2,  // second operand minus the first
    OPER_SYMMETRIC_DIFFERENCE
  };

  ///@{
  /**
   * The operation that combines the result of the previous steps (the first operand) with input
   * inputIndex (the second operand): an OperModes value other than OPER_NONE. OPER_DIFFERENCE
   * subtracts the input from the result, and OPER_DIFFERENCE2 subtracts the result from the
   * input. Input 0 has no operation. Inputs whose operation is not set are united with the
   * result.
   */
  void SetOperation(int inputIndex, int operMode);
  int GetOperation(int inputIndex) const;
  void RemoveAllOperations();
  ///@}

  ///@{
  /**
   * Edge length of the voxels. 0 (the default) or less chooses the voxel size that gives 256
   * voxels along the longest side of the bounds of the result.
   */
  vtkSetMacro(VoxelSize, double);
  vtkGetMacro(VoxelSize, double);
  ///@}

  ///@{
  /**
   * Number of times the voxels are split in 2 along each axis near the surfaces, to compute the
   * fraction of each voxel that the result covers. Default is 2, which samples each voxel at 64
   * points.
   */
  vtkSetClampMacro(ExtraLevels, int, 0, 4);
  vtkGetMacro(ExtraLevels, int);
  ///@}

  ///@{
  /**
   * The computation fails if the voxels would be more than this, to bound the memory use (one
   * byte per voxel, plus the octrees). Default is 512^3.
   */
  vtkSetClampMacro(MaximumNumberOfVoxels, vtkIdType, 1, VTK_ID_MAX);
  vtkGetMacro(MaximumNumberOfVoxels, vtkIdType);
  ///@}

  /**
   * Voxel size used by the last update, 0 if no voxels were needed.
   */
  vtkGetMacro(EffectiveVoxelSize, double);

 protected:
  vtkOctreeBooleanFilter();
  ~vtkOctreeBooleanFilter() override;

  int FillInputPortInformation(int port, vtkInformation* info) override;
  int RequestData(vtkInformation* request, vtkInformationVector** inputVector,
                  vtkInformationVector* outputVector) override;

 private:
  vtkOctreeBooleanFilter(const vtkOctreeBooleanFilter&) = delete;
  void operator=(const vtkOctreeBooleanFilter&) = delete;

  // Operations[i] is the operation of input i.
  std::vector<int> Operations;
  double VoxelSize = 0.0;
  int ExtraLevels = 2;
  vtkIdType MaximumNumberOfVoxels = vtkIdType(512) * 512 * 512;
  double EffectiveVoxelSize = 0.0;
};

#endif
