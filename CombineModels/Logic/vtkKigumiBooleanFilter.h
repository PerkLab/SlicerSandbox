/**
 * @class vtkKigumiBooleanFilter
 * @brief Exact Boolean operations on polygonal meshes using kigumi.
 *
 * Computes a Boolean operation between the regions bounded by the meshes on input ports 0 (A)
 * and 1 (B). Polygons and triangle strips are used; polygons with more than three vertices are
 * interpreted as triangle fans. Meshes may be open or closed, manifold or non-manifold, but must
 * not self-intersect (see the kigumi documentation for details). An input without polygons
 * represents the empty set.
 *
 * Computations are exact. Coordinates of intersection points are rounded to the nearest doubles
 * in the output.
 *
 * The output is a triangle mesh with the cell data arrays "OrigCellIdsA" and "OrigCellIdsB",
 * which hold the ids of the input cells each output triangle originates from (-1 if none).
 *
 * The API of the operation mode follows that of vtkPolyDataBooleanFilter from vtkbool.
 */

#ifndef vtkKigumiBooleanFilter_h
#define vtkKigumiBooleanFilter_h

#include "vtkSlicerCombineModelsModuleLogicExport.h"
#include "vtkPolyDataAlgorithm.h"

class VTK_SLICER_COMBINEMODELS_MODULE_LOGIC_EXPORT vtkKigumiBooleanFilter : public vtkPolyDataAlgorithm {
 public:
  static vtkKigumiBooleanFilter* New();
  vtkTypeMacro(vtkKigumiBooleanFilter, vtkPolyDataAlgorithm);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  enum OperModes {
    OPER_NONE = 0,
    OPER_UNION,
    OPER_INTERSECTION,
    OPER_DIFFERENCE,             // A - B
    OPER_DIFFERENCE2,            // B - A
    OPER_SYMMETRIC_DIFFERENCE,  // (A - B) + (B - A)
  };

  ///@{
  /**
   * The Boolean operation. OPER_NONE outputs the boundaries of both inputs, split along their
   * intersection, with their original orientation.
   * The default is OPER_UNION.
   */
  vtkSetClampMacro(OperMode, int, OPER_NONE, OPER_SYMMETRIC_DIFFERENCE);
  vtkGetMacro(OperMode, int);
  void SetOperModeToNone() { this->SetOperMode(OPER_NONE); }
  void SetOperModeToUnion() { this->SetOperMode(OPER_UNION); }
  void SetOperModeToIntersection() { this->SetOperMode(OPER_INTERSECTION); }
  void SetOperModeToDifference() { this->SetOperMode(OPER_DIFFERENCE); }
  void SetOperModeToDifference2() { this->SetOperMode(OPER_DIFFERENCE2); }
  void SetOperModeToSymmetricDifference() { this->SetOperMode(OPER_SYMMETRIC_DIFFERENCE); }
  ///@}

  ///@{
  /**
   * Where the boundaries of A and B overlap with the same orientation, keep the faces of A if on
   * (the default), or those of B otherwise. This only affects the cell data.
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
  vtkKigumiBooleanFilter();
  ~vtkKigumiBooleanFilter() override;

  int FillInputPortInformation(int port, vtkInformation* info) override;
  int RequestData(vtkInformation* request, vtkInformationVector** inputVector,
                  vtkInformationVector* outputVector) override;

 private:
  vtkKigumiBooleanFilter(const vtkKigumiBooleanFilter&) = delete;
  void operator=(const vtkKigumiBooleanFilter&) = delete;

  int OperMode = OPER_UNION;
  bool PreferFirst = true;
  int NumberOfThreads = 0;
};

#endif
