/**
 * @class vtkKigumiMeshDefectsFilter
 * @brief Finds the defects of a polygonal mesh that make it unsuitable for Boolean operations.
 *
 * Checks the mesh on input port 0 with kigumi::Find_defects, in the same way as the
 * `kigumi check` command. Polygons and triangle strips are used; polygons with more than three
 * vertices are interpreted as triangle fans, as vtkKigumiBooleanFilter does. Points with the same
 * coordinates are merged before the check. All tests are exact:
 *
 * - Boundary edges: edges that belong to only one triangle (the mesh is not closed).
 * - Inconsistent edges: edges whose two triangles traverse them in the same direction (the
 *   orientation of the triangles is not consistent).
 * - Non-manifold edges: edges that belong to more than two triangles.
 * - Non-manifold vertices: vertices whose surrounding triangles do not form a single fan.
 * - Degenerate faces: triangles with repeated or collinear vertices.
 * - Self-intersecting faces: triangles that intersect another triangle of the mesh other than at
 *   their shared vertices and edges.
 * - Isolated vertices: points that are not used by any triangle. These are harmless and are only
 *   counted.
 *
 * The output contains the defects: non-manifold vertices as vertex cells, boundary, inconsistent
 * and non-manifold edges as lines, and degenerate and self-intersecting faces as triangles. The
 * cell data array "DefectType" holds the DefectTypes value of each cell, and "OrigCellId" holds
 * the id of the input cell each triangle originates from (-1 for vertices and lines). The output
 * is empty if the mesh has no defects.
 */

#ifndef vtkKigumiMeshDefectsFilter_h
#define vtkKigumiMeshDefectsFilter_h

#include "vtkSlicerCombineModelsModuleLogicExport.h"
#include "vtkPolyDataAlgorithm.h"

class VTK_SLICER_COMBINEMODELS_MODULE_LOGIC_EXPORT vtkKigumiMeshDefectsFilter : public vtkPolyDataAlgorithm {
 public:
  static vtkKigumiMeshDefectsFilter* New();
  vtkTypeMacro(vtkKigumiMeshDefectsFilter, vtkPolyDataAlgorithm);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  enum DefectTypes {
    NON_MANIFOLD_VERTEX = 1,
    BOUNDARY_EDGE,
    INCONSISTENT_EDGE,
    NON_MANIFOLD_EDGE,
    DEGENERATE_FACE,
    SELF_INTERSECTING_FACE,
  };

  ///@{
  /**
   * The numbers of triangles and defects found by the last update.
   */
  vtkGetMacro(NumberOfFaces, vtkIdType);
  vtkGetMacro(NumberOfIsolatedVertices, vtkIdType);
  vtkGetMacro(NumberOfNonManifoldVertices, vtkIdType);
  vtkGetMacro(NumberOfBoundaryEdges, vtkIdType);
  vtkGetMacro(NumberOfInconsistentEdges, vtkIdType);
  vtkGetMacro(NumberOfNonManifoldEdges, vtkIdType);
  vtkGetMacro(NumberOfDegenerateFaces, vtkIdType);
  vtkGetMacro(NumberOfSelfIntersectingFaces, vtkIdType);
  ///@}

  ///@{
  /**
   * The maximum number of threads to use. 0 (the default) uses all hardware threads.
   */
  vtkSetClampMacro(NumberOfThreads, int, 0, VTK_INT_MAX);
  vtkGetMacro(NumberOfThreads, int);
  ///@}

 protected:
  vtkKigumiMeshDefectsFilter();
  ~vtkKigumiMeshDefectsFilter() override;

  int FillInputPortInformation(int port, vtkInformation* info) override;
  int RequestData(vtkInformation* request, vtkInformationVector** inputVector,
                  vtkInformationVector* outputVector) override;

 private:
  vtkKigumiMeshDefectsFilter(const vtkKigumiMeshDefectsFilter&) = delete;
  void operator=(const vtkKigumiMeshDefectsFilter&) = delete;

  void ResetCounts();

  vtkIdType NumberOfFaces = 0;
  vtkIdType NumberOfIsolatedVertices = 0;
  vtkIdType NumberOfNonManifoldVertices = 0;
  vtkIdType NumberOfBoundaryEdges = 0;
  vtkIdType NumberOfInconsistentEdges = 0;
  vtkIdType NumberOfNonManifoldEdges = 0;
  vtkIdType NumberOfDegenerateFaces = 0;
  vtkIdType NumberOfSelfIntersectingFaces = 0;
  int NumberOfThreads = 0;
};

#endif
