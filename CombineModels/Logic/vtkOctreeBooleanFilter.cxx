#include "vtkOctreeBooleanFilter.h"

#include "vtkBoundingBox.h"
#include "vtkCellArray.h"
#include "vtkDoubleArray.h"
#include "vtkFlyingEdges3D.h"
#include "vtkHyperTree.h"
#include "vtkHyperTreeGrid.h"
#include "vtkIdList.h"
#include "vtkImageData.h"
#include "vtkImageStencilData.h"
#include "vtkInformation.h"
#include "vtkInformationVector.h"
#include "vtkNew.h"
#include "vtkObjectFactory.h"
#include "vtkPoints.h"
#include "vtkPolyData.h"
#include "vtkPolyDataToImageStencil.h"
#include "vtkSMPThreadLocal.h"
#include "vtkSMPTools.h"
#include "vtkSmartPointer.h"
#include "vtkTriangleFilter.h"

#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdint>
#include <new>
#include <vector>

// The octrees are built and combined as in the "HyperTree boolean" effect of the
// SegmentEditorExtraEffects extension. The helpers are in an anonymous namespace, so that they
// cannot clash with those of that extension when both are loaded.
namespace {

// Octree cells have 2 children along each axis.
constexpr unsigned int NumberOfChildren = 8;

// Pre-order description of a tree, one byte per cell. Leaf children that all have the same value
// are merged into their parent when the parent is closed, because a vtkHyperTree cell cannot be
// merged once it is subdivided.
class RecordStream {
 public:
  enum : uint8_t { Leaf = 1, Inside = 2 };

  void Clear() { this->Records.clear(); }
  size_t Size() const { return this->Records.size(); }
  const uint8_t* Data() const { return this->Records.data(); }

  void AddLeaf(bool inside) { this->Records.push_back(inside ? Leaf | Inside : Leaf); }

  // Starts a subdivided cell and returns its position, to pass to EndCoarse().
  size_t BeginCoarse() {
    this->Records.push_back(0);
    return this->Records.size() - 1;
  }

  // Ends a subdivided cell after all of its children were added.
  void EndCoarse(size_t position) {
    // Each child is a single record only if all children are leaves
    if (this->Records.size() != position + 1 + NumberOfChildren) {
      return;
    }
    const uint8_t first = this->Records[position + 1];
    for (unsigned int child = 1; child < NumberOfChildren; ++child) {
      if (this->Records[position + 1 + child] != first) {
        return;
      }
    }
    this->Records[position] = first;
    this->Records.resize(position + 1);
  }

 private:
  std::vector<uint8_t> Records;
};

// Subdivides an empty tree as described by the records, and stores the inside flag of each cell
// at its local index.
void Replay(vtkHyperTree* tree, const uint8_t* records, size_t& position, vtkIdType index,
            unsigned int level, uint8_t* inside) {
  const uint8_t record = records[position++];
  inside[index] = (record & RecordStream::Inside) ? 1 : 0;
  if (record & RecordStream::Leaf) {
    return;
  }
  tree->SubdivideLeaf(index, level);
  const vtkIdType elder = tree->GetElderChildIndex(static_cast<unsigned int>(index));
  for (unsigned int child = 0; child < NumberOfChildren; ++child) {
    Replay(tree, records, position, elder + child, level + 1, inside);
  }
}

// Builds all trees of a grid whose level-0 grid is already set, and returns the inside flag of
// each cell by global index. buildTree(treeIndex, records) describes one tree; it is called
// concurrently for different trees.
template <typename BuildTreeFunctor>
std::vector<uint8_t> BuildTrees(vtkHyperTreeGrid* grid, BuildTreeFunctor& buildTree) {
  const vtkIdType numberOfTrees = grid->GetMaxNumberOfTrees();

  // Creating trees modifies the grid, so it is done before going parallel
  std::vector<vtkHyperTree*> trees(numberOfTrees);
  for (vtkIdType treeIndex = 0; treeIndex < numberOfTrees; ++treeIndex) {
    trees[treeIndex] = grid->GetTree(treeIndex, true);
  }

  std::vector<std::vector<uint8_t>> treeInside(numberOfTrees);
  vtkSMPThreadLocal<RecordStream> localRecords;
  vtkSMPTools::For(0, numberOfTrees, [&](vtkIdType begin, vtkIdType end) {
    RecordStream& records = localRecords.Local();
    for (vtkIdType treeIndex = begin; treeIndex < end; ++treeIndex) {
      records.Clear();
      buildTree(treeIndex, records);
      treeInside[treeIndex].resize(records.Size());
      size_t position = 0;
      Replay(trees[treeIndex], records.Data(), position, 0, 0, treeInside[treeIndex].data());
    }
  });

  std::vector<vtkIdType> offsets(numberOfTrees + 1, 0);
  for (vtkIdType treeIndex = 0; treeIndex < numberOfTrees; ++treeIndex) {
    trees[treeIndex]->SetGlobalIndexStart(offsets[treeIndex]);
    offsets[treeIndex + 1] = offsets[treeIndex] + static_cast<vtkIdType>(treeInside[treeIndex].size());
  }

  std::vector<uint8_t> inside(offsets[numberOfTrees]);
  vtkSMPTools::For(0, numberOfTrees, [&](vtkIdType begin, vtkIdType end) {
    for (vtkIdType treeIndex = begin; treeIndex < end; ++treeIndex) {
      std::copy(treeInside[treeIndex].begin(), treeInside[treeIndex].end(),
                inside.begin() + offsets[treeIndex]);
    }
  });
  return inside;
}

// Octrees of a grid with the inside flag of each cell by global index.
struct Octrees {
  vtkSmartPointer<vtkHyperTreeGrid> Grid;
  std::vector<uint8_t> Inside;
};

// Read-only access to one tree, safe to use from several threads.
struct TreeView {
  vtkHyperTree* Tree = nullptr;
  const uint8_t* Inside = nullptr;

  bool IsLeaf(vtkIdType index) const { return this->Tree->IsLeaf(index); }
  bool IsInside(vtkIdType index) const {
    return this->Inside[this->Tree->GetGlobalIndexFromLocal(index)] != 0;
  }
  vtkIdType GetChild(vtkIdType index, unsigned int child) const {
    return this->Tree->GetElderChildIndex(static_cast<unsigned int>(index)) + child;
  }
};

bool HasFinitePoints(vtkPolyData* polyData) {
  vtkPoints* points = polyData->GetPoints();
  for (vtkIdType pointId = 0; pointId < points->GetNumberOfPoints(); ++pointId) {
    double point[3];
    points->GetPoint(pointId, point);
    if (!std::isfinite(point[0]) || !std::isfinite(point[1]) || !std::isfinite(point[2])) {
      return false;
    }
  }
  return true;
}

std::vector<TreeView> GetTreeViews(const Octrees& octrees) {
  std::vector<TreeView> views(octrees.Grid->GetMaxNumberOfTrees());
  for (vtkIdType treeIndex = 0; treeIndex < static_cast<vtkIdType>(views.size()); ++treeIndex) {
    views[treeIndex] = {octrees.Grid->GetTree(treeIndex), octrees.Inside.data()};
  }
  return views;
}

// Inside runs of each row of a fine voxel grid, sorted along x.
class RowRuns {
 public:
  // Scan-converts a surface on the voxels of extent, with the given origin and spacing. The
  // voxels are inside where a line along x crosses the surface an odd number of times.
  RowRuns(vtkPolyData* surface, const double origin[3], double spacing, const int extent[6])
      : Extent{extent[0], extent[1], extent[2], extent[3], extent[4], extent[5]} {
    // vtkPolyDataToImageStencil cuts every cell at each slice, so the slices are split in slabs
    // that are scan-converted in parallel, each with the cells that can cross its slices
    const int numberOfSlices = extent[5] - extent[4] + 1;
    const int numberOfSlabs = (numberOfSlices + SlicesPerSlab - 1) / SlicesPerSlab;
    std::vector<std::vector<vtkIdType>> slabCells(numberOfSlabs);
    vtkPoints* points = surface->GetPoints();
    vtkCellArray* polys = surface->GetPolys();
    vtkNew<vtkIdList> pointIds;
    for (vtkIdType cellId = 0; cellId < polys->GetNumberOfCells(); ++cellId) {
      vtkIdType numberOfPoints;
      const vtkIdType* cellPointIds;
      polys->GetCellAtId(cellId, numberOfPoints, cellPointIds, pointIds);
      double zMin = VTK_DOUBLE_MAX;
      double zMax = VTK_DOUBLE_MIN;
      for (vtkIdType i = 0; i < numberOfPoints; ++i) {
        double point[3];
        points->GetPoint(cellPointIds[i], point);
        zMin = std::min(zMin, point[2]);
        zMax = std::max(zMax, point[2]);
      }
      // Slices within the z range of the cell, with a margin of one slice for rounding
      const double firstSlice = std::max(std::floor((zMin - origin[2]) / spacing) - 1.0, double(extent[4]));
      const double lastSlice = std::min(std::ceil((zMax - origin[2]) / spacing) + 1.0, double(extent[5]));
      if (!(firstSlice <= lastSlice)) {
        continue;
      }
      const int lastSlab = (static_cast<int>(lastSlice) - extent[4]) / SlicesPerSlab;
      for (int slab = (static_cast<int>(firstSlice) - extent[4]) / SlicesPerSlab; slab <= lastSlab; ++slab) {
        slabCells[slab].push_back(cellId);
      }
    }

    const vtkIdType rowsPerSlice = extent[3] - extent[2] + 1;
    std::vector<std::vector<int>> slabRunsPerRow(numberOfSlabs);
    std::vector<std::vector<int>> slabRuns(numberOfSlabs);
    vtkSMPTools::For(0, numberOfSlabs, [&](vtkIdType begin, vtkIdType end) {
      vtkNew<vtkIdList> localPointIds;
      for (vtkIdType slab = begin; slab < end; ++slab) {
        int slabExtent[6] = {extent[0], extent[1], extent[2], extent[3],
                             extent[4] + static_cast<int>(slab) * SlicesPerSlab, 0};
        slabExtent[5] = std::min(slabExtent[4] + SlicesPerSlab - 1, extent[5]);
        slabRunsPerRow[slab].assign(rowsPerSlice * (slabExtent[5] - slabExtent[4] + 1), 0);
        if (slabCells[slab].empty()) {
          continue;
        }
        vtkNew<vtkCellArray> cells;
        for (vtkIdType cellId : slabCells[slab]) {
          vtkIdType numberOfPoints;
          const vtkIdType* cellPointIds;
          polys->GetCellAtId(cellId, numberOfPoints, cellPointIds, localPointIds);
          cells->InsertNextCell(numberOfPoints, cellPointIds);
        }
        vtkNew<vtkPolyData> slabSurface;
        slabSurface->SetPoints(points);
        slabSurface->SetPolys(cells);
        vtkNew<vtkPolyDataToImageStencil> stencilSource;
        stencilSource->SetEnableSMP(false);
        stencilSource->SetInputData(slabSurface);
        stencilSource->SetOutputOrigin(origin[0], origin[1], origin[2]);
        stencilSource->SetOutputSpacing(spacing, spacing, spacing);
        stencilSource->SetOutputWholeExtent(slabExtent);
        stencilSource->Update();
        vtkImageStencilData* stencil = stencilSource->GetOutput();
        int* runsPerRow = slabRunsPerRow[slab].data();
        for (int z = slabExtent[4]; z <= slabExtent[5]; ++z) {
          for (int y = extent[2]; y <= extent[3]; ++y, ++runsPerRow) {
            int iter = 0;
            int r1, r2;
            while (stencil->GetNextExtent(r1, r2, extent[0], extent[1], y, z, iter)) {
              slabRuns[slab].push_back(r1);
              slabRuns[slab].push_back(r2);
              ++*runsPerRow;
            }
          }
        }
      }
    });

    this->Offsets.reserve(rowsPerSlice * numberOfSlices + 1);
    this->Offsets.push_back(0);
    for (int slab = 0; slab < numberOfSlabs; ++slab) {
      for (int numberOfRuns : slabRunsPerRow[slab]) {
        this->Offsets.push_back(this->Offsets.back() + numberOfRuns);
      }
      this->Runs.insert(this->Runs.end(), slabRuns[slab].begin(), slabRuns[slab].end());
      std::vector<int>().swap(slabRuns[slab]);
    }
  }

  enum Coverage { Empty, Full, Partial };

  // Coverage of the voxels [x0, x1] of a row.
  Coverage GetCoverage(vtkIdType x0, vtkIdType x1, vtkIdType y, vtkIdType z) const {
    if (y < this->Extent[2] || y > this->Extent[3] || z < this->Extent[4] || z > this->Extent[5]) {
      return Empty;
    }
    const vtkIdType row =
        (y - this->Extent[2]) + (this->Extent[3] - this->Extent[2] + 1) * (z - this->Extent[4]);
    const int* first = this->Runs.data() + 2 * this->Offsets[row];
    const int* last = this->Runs.data() + 2 * this->Offsets[row + 1];
    // First run that ends at or after x0
    const vtkIdType numberOfRuns = (last - first) / 2;
    vtkIdType low = 0, high = numberOfRuns;
    while (low < high) {
      const vtkIdType middle = (low + high) / 2;
      if (first[2 * middle + 1] < x0) {
        low = middle + 1;
      } else {
        high = middle;
      }
    }
    if (low == numberOfRuns || first[2 * low] > x1) {
      return Empty;
    }
    return (first[2 * low] <= x0 && first[2 * low + 1] >= x1) ? Full : Partial;
  }

 private:
  static constexpr int SlicesPerSlab = 8;

  const int Extent[6];
  std::vector<vtkIdType> Offsets;
  std::vector<int> Runs;
};

class StencilSubdivider {
 public:
  explicit StencilSubdivider(const RowRuns& runs) : Runs(runs) {}

  // Describes the cell covering the fine voxels [x0, x0 + size) along each axis.
  void Subdivide(vtkIdType x0, vtkIdType y0, vtkIdType z0, vtkIdType size,
                 RecordStream& records) const {
    bool inside = false;
    if (size == 1 || this->IsUniform(x0, y0, z0, size, inside)) {
      records.AddLeaf(size == 1 ? this->Runs.GetCoverage(x0, x0, y0, z0) == RowRuns::Full : inside);
      return;
    }
    const size_t position = records.BeginCoarse();
    const vtkIdType half = size / 2;
    for (unsigned int child = 0; child < NumberOfChildren; ++child) {
      this->Subdivide(x0 + (child & 1) * half, y0 + ((child >> 1) & 1) * half,
                      z0 + ((child >> 2) & 1) * half, half, records);
    }
    records.EndCoarse(position);
  }

 private:
  bool IsUniform(vtkIdType x0, vtkIdType y0, vtkIdType z0, vtkIdType size, bool& inside) const {
    const RowRuns::Coverage first = this->Runs.GetCoverage(x0, x0 + size - 1, y0, z0);
    if (first == RowRuns::Partial) {
      return false;
    }
    for (vtkIdType z = z0; z < z0 + size; ++z) {
      for (vtkIdType y = y0; y < y0 + size; ++y) {
        if (this->Runs.GetCoverage(x0, x0 + size - 1, y, z) != first) {
          return false;
        }
      }
    }
    inside = first == RowRuns::Full;
    return true;
  }

  const RowRuns& Runs;
};

class TreeCombiner {
 public:
  explicit TreeCombiner(int operation) : Operation(operation) {}

  bool Apply(bool a, bool b) const {
    switch (this->Operation) {
      case vtkOctreeBooleanFilter::OPER_INTERSECTION:
        return a && b;
      case vtkOctreeBooleanFilter::OPER_DIFFERENCE:
        return a && !b;
      case vtkOctreeBooleanFilter::OPER_DIFFERENCE2:
        return !a && b;
      case vtkOctreeBooleanFilter::OPER_SYMMETRIC_DIFFERENCE:
        return a != b;
      default:
        return a || b;
    }
  }

  void Combine(const TreeView& a, vtkIdType indexA, const TreeView& b, vtkIdType indexB,
               RecordStream& records) const {
    const bool leafA = a.IsLeaf(indexA);
    const bool leafB = b.IsLeaf(indexB);
    if (leafA && leafB) {
      records.AddLeaf(this->Apply(a.IsInside(indexA), b.IsInside(indexB)));
      return;
    }
    if (leafA || leafB) {
      // With one side fixed, the result is a constant, the other subtree, or its complement
      const bool fixedValue = leafA ? a.IsInside(indexA) : b.IsInside(indexB);
      const bool resultIfOutside = leafA ? this->Apply(fixedValue, false) : this->Apply(false, fixedValue);
      const bool resultIfInside = leafA ? this->Apply(fixedValue, true) : this->Apply(true, fixedValue);
      if (resultIfOutside == resultIfInside) {
        records.AddLeaf(resultIfInside);
      } else {
        this->Copy(leafA ? b : a, leafA ? indexB : indexA, !resultIfInside, records);
      }
      return;
    }
    const size_t position = records.BeginCoarse();
    for (unsigned int child = 0; child < NumberOfChildren; ++child) {
      this->Combine(a, a.GetChild(indexA, child), b, b.GetChild(indexB, child), records);
    }
    records.EndCoarse(position);
  }

 private:
  void Copy(const TreeView& tree, vtkIdType index, bool complement, RecordStream& records) const {
    if (tree.IsLeaf(index)) {
      records.AddLeaf(tree.IsInside(index) != complement);
      return;
    }
    const size_t position = records.BeginCoarse();
    for (unsigned int child = 0; child < NumberOfChildren; ++child) {
      this->Copy(tree, tree.GetChild(index, child), complement, records);
    }
    records.EndCoarse(position);
  }

  const int Operation;
};

// Writes the fraction of each voxel that the inside cells cover, from 0 to 255.
class TreeRasterizer {
 public:
  TreeRasterizer(uint8_t* voxels, const int dimensions[3], int voxelLevel)
      : Voxels(voxels), Dimensions{dimensions[0], dimensions[1], dimensions[2]}, VoxelLevel(voxelLevel) {}

  // Writes the voxels covered by a cell whose first voxel is (x0, y0, z0).
  void Rasterize(const TreeView& tree, vtkIdType index, int level, vtkIdType x0, vtkIdType y0,
                 vtkIdType z0) const {
    if (tree.IsLeaf(index)) {
      if (tree.IsInside(index)) {
        this->Fill(x0, y0, z0, vtkIdType(1) << (this->VoxelLevel - level));
      }
      return;
    }
    if (level == this->VoxelLevel) {
      if (x0 < this->Dimensions[0] && y0 < this->Dimensions[1] && z0 < this->Dimensions[2]) {
        this->Voxels[this->GetVoxelIndex(x0, y0, z0)] =
            static_cast<uint8_t>(std::lround(255.0 * this->GetFraction(tree, index)));
      }
      return;
    }
    const vtkIdType half = vtkIdType(1) << (this->VoxelLevel - level - 1);
    for (unsigned int child = 0; child < NumberOfChildren; ++child) {
      this->Rasterize(tree, tree.GetChild(index, child), level + 1, x0 + (child & 1) * half,
                      y0 + ((child >> 1) & 1) * half, z0 + ((child >> 2) & 1) * half);
    }
  }

 private:
  double GetFraction(const TreeView& tree, vtkIdType index) const {
    if (tree.IsLeaf(index)) {
      return tree.IsInside(index) ? 1.0 : 0.0;
    }
    double sum = 0.0;
    for (unsigned int child = 0; child < NumberOfChildren; ++child) {
      sum += this->GetFraction(tree, tree.GetChild(index, child));
    }
    return sum / NumberOfChildren;
  }

  vtkIdType GetVoxelIndex(vtkIdType x, vtkIdType y, vtkIdType z) const {
    return x + this->Dimensions[0] * (y + this->Dimensions[1] * z);
  }

  // Fills a cube of voxels, clipped to the grid, which the trees overhang.
  void Fill(vtkIdType x0, vtkIdType y0, vtkIdType z0, vtkIdType size) const {
    const vtkIdType xMax = std::min<vtkIdType>(x0 + size, this->Dimensions[0]);
    if (x0 >= xMax) {
      return;
    }
    for (vtkIdType z = z0; z < std::min<vtkIdType>(z0 + size, this->Dimensions[2]); ++z) {
      for (vtkIdType y = y0; y < std::min<vtkIdType>(y0 + size, this->Dimensions[1]); ++y) {
        uint8_t* row = this->Voxels + this->GetVoxelIndex(x0, y, z);
        std::fill(row, row + (xMax - x0), uint8_t(255));
      }
    }
  }

  uint8_t* Voxels;
  const vtkIdType Dimensions[3];
  const int VoxelLevel;
};

// Voxels covered by octrees of 2^VoxelLevel voxels along each axis. The octrees are in voxel
// index space, where voxel (i, j, k) is centered at (i, j, k).
class OctreeGrid {
 public:
  OctreeGrid(const double origin[3], double voxelSize, const int dimensions[3], int voxelLevel,
             int extraLevels)
      : Origin{origin[0], origin[1], origin[2]},
        VoxelSize(voxelSize),
        Dimensions{dimensions[0], dimensions[1], dimensions[2]},
        VoxelLevel(voxelLevel),
        ExtraLevels(extraLevels) {}

  // Octrees in which every cell is outside.
  Octrees BuildEmpty() const {
    Octrees octrees = this->NewOctrees();
    auto buildTree = [](vtkIdType, RecordStream& records) { records.AddLeaf(false); };
    octrees.Inside = BuildTrees(octrees.Grid, buildTree);
    return octrees;
  }

  // Octrees of the inside of a closed surface whose points are within bounds.
  Octrees BuildFromSurface(vtkPolyData* surface, const vtkBoundingBox& bounds) const {
    // Fine voxel f = i * factor + m of voxel i is centered at (f + 0.5) / factor - 0.5
    const int factor = 1 << this->ExtraLevels;
    const double fineSpacing = this->VoxelSize / factor;
    double fineOrigin[3];
    int fineExtent[6];
    for (int axis = 0; axis < 3; ++axis) {
      fineOrigin[axis] = this->Origin[axis] + this->VoxelSize * (0.5 / factor - 0.5);
      // Only the fine voxels within the bounds of the surface can be inside
      const double first = std::floor((bounds.GetMinPoint()[axis] - fineOrigin[axis]) / fineSpacing);
      const double last = std::ceil((bounds.GetMaxPoint()[axis] - fineOrigin[axis]) / fineSpacing);
      const double lastFineVoxel = static_cast<double>(this->Dimensions[axis]) * factor - 1;
      if (last < 0.0 || first > lastFineVoxel) {
        return this->BuildEmpty();
      }
      fineExtent[2 * axis] = static_cast<int>(std::max(first, 0.0));
      fineExtent[2 * axis + 1] = static_cast<int>(std::min(last, lastFineVoxel));
    }

    const RowRuns runs = [&] {
      if (surface->GetNumberOfStrips() == 0) {
        return RowRuns(surface, fineOrigin, fineSpacing, fineExtent);
      }
      vtkNew<vtkTriangleFilter> triangulator;
      triangulator->PassVertsOff();
      triangulator->PassLinesOff();
      triangulator->SetInputData(surface);
      triangulator->Update();
      return RowRuns(triangulator->GetOutput(), fineOrigin, fineSpacing, fineExtent);
    }();

    Octrees octrees = this->NewOctrees();
    const StencilSubdivider subdivider(runs);
    const vtkIdType treeSize = (vtkIdType(1) << this->VoxelLevel) * factor;
    vtkHyperTreeGrid* grid = octrees.Grid;
    auto buildTree = [&](vtkIdType treeIndex, RecordStream& records) {
      unsigned int ijk[3];
      grid->GetLevelZeroCoordinatesFromIndex(treeIndex, ijk[0], ijk[1], ijk[2]);
      vtkIdType firstFineVoxel[3];
      for (int axis = 0; axis < 3; ++axis) {
        firstFineVoxel[axis] = ijk[axis] * treeSize;
        if (firstFineVoxel[axis] > fineExtent[2 * axis + 1] ||
            firstFineVoxel[axis] + treeSize - 1 < fineExtent[2 * axis]) {
          records.AddLeaf(false);
          return;
        }
      }
      subdivider.Subdivide(firstFineVoxel[0], firstFineVoxel[1], firstFineVoxel[2], treeSize, records);
    };
    octrees.Inside = BuildTrees(grid, buildTree);
    return octrees;
  }

  Octrees Combine(const Octrees& a, const Octrees& b, int operation) const {
    Octrees result = this->NewOctrees();
    const std::vector<TreeView> treesA = GetTreeViews(a);
    const std::vector<TreeView> treesB = GetTreeViews(b);
    const TreeCombiner combiner(operation);
    auto buildTree = [&](vtkIdType treeIndex, RecordStream& records) {
      combiner.Combine(treesA[treeIndex], 0, treesB[treeIndex], 0, records);
    };
    result.Inside = BuildTrees(result.Grid, buildTree);
    return result;
  }

  // Writes the fraction of each voxel that is inside, from 0 to 255, to voxels, which must be
  // zero-initialized.
  void Rasterize(const Octrees& octrees, uint8_t* voxels) const {
    const std::vector<TreeView> trees = GetTreeViews(octrees);
    const TreeRasterizer rasterizer(voxels, this->Dimensions, this->VoxelLevel);
    const vtkIdType blockSize = vtkIdType(1) << this->VoxelLevel;
    vtkHyperTreeGrid* grid = octrees.Grid;
    // Trees cover disjoint blocks of voxels
    vtkSMPTools::For(0, static_cast<vtkIdType>(trees.size()), [&](vtkIdType begin, vtkIdType end) {
      for (vtkIdType treeIndex = begin; treeIndex < end; ++treeIndex) {
        unsigned int ijk[3];
        grid->GetLevelZeroCoordinatesFromIndex(treeIndex, ijk[0], ijk[1], ijk[2]);
        rasterizer.Rasterize(trees[treeIndex], 0, 0, ijk[0] * blockSize, ijk[1] * blockSize,
                             ijk[2] * blockSize);
      }
    });
  }

 private:
  Octrees NewOctrees() const {
    Octrees octrees;
    octrees.Grid = vtkSmartPointer<vtkHyperTreeGrid>::New();
    vtkHyperTreeGrid* grid = octrees.Grid;
    const int blockSize = 1 << this->VoxelLevel;
    int numberOfTrees[3];
    for (int axis = 0; axis < 3; ++axis) {
      numberOfTrees[axis] = (this->Dimensions[axis] + blockSize - 1) / blockSize;
    }
    grid->Initialize();
    grid->SetDimensions(numberOfTrees[0] + 1, numberOfTrees[1] + 1, numberOfTrees[2] + 1);
    grid->SetBranchFactor(2);
    vtkNew<vtkDoubleArray> coordinates[3];
    for (int axis = 0; axis < 3; ++axis) {
      for (int i = 0; i <= numberOfTrees[axis]; ++i) {
        coordinates[axis]->InsertNextValue(i * blockSize - 0.5);
      }
    }
    grid->SetXCoordinates(coordinates[0]);
    grid->SetYCoordinates(coordinates[1]);
    grid->SetZCoordinates(coordinates[2]);
    return octrees;
  }

  const double Origin[3];
  const double VoxelSize;
  const int Dimensions[3];
  const int VoxelLevel;
  const int ExtraLevels;
};

}  // namespace

vtkStandardNewMacro(vtkOctreeBooleanFilter);

vtkOctreeBooleanFilter::vtkOctreeBooleanFilter() = default;

vtkOctreeBooleanFilter::~vtkOctreeBooleanFilter() = default;

void vtkOctreeBooleanFilter::PrintSelf(ostream& os, vtkIndent indent) {
  this->Superclass::PrintSelf(os, indent);
  os << indent << "Operations:";
  for (std::size_t i = 1; i < this->Operations.size(); ++i) {
    os << " " << this->Operations[i];
  }
  os << "\n";
  os << indent << "VoxelSize: " << this->VoxelSize << "\n";
  os << indent << "ExtraLevels: " << this->ExtraLevels << "\n";
  os << indent << "MaximumNumberOfVoxels: " << this->MaximumNumberOfVoxels << "\n";
  os << indent << "EffectiveVoxelSize: " << this->EffectiveVoxelSize << "\n";
}

void vtkOctreeBooleanFilter::SetOperation(int inputIndex, int operMode) {
  if (inputIndex < 1) {
    vtkErrorMacro(<< "Input " << inputIndex << " has no operation.");
    return;
  }
  if (operMode < OPER_UNION || operMode > OPER_SYMMETRIC_DIFFERENCE) {
    vtkErrorMacro(<< "Invalid operation mode: " << operMode);
    return;
  }
  auto index = static_cast<std::size_t>(inputIndex);
  if (index >= this->Operations.size()) {
    this->Operations.resize(index + 1, OPER_UNION);
  } else if (this->Operations[index] == operMode) {
    return;
  }
  this->Operations[index] = operMode;
  this->Modified();
}

int vtkOctreeBooleanFilter::GetOperation(int inputIndex) const {
  if (inputIndex < 1 || static_cast<std::size_t>(inputIndex) >= this->Operations.size()) {
    return OPER_UNION;
  }
  return this->Operations[static_cast<std::size_t>(inputIndex)];
}

void vtkOctreeBooleanFilter::RemoveAllOperations() {
  if (!this->Operations.empty()) {
    this->Operations.clear();
    this->Modified();
  }
}

int vtkOctreeBooleanFilter::FillInputPortInformation(int /*port*/, vtkInformation* info) {
  info->Set(vtkAlgorithm::INPUT_REQUIRED_DATA_TYPE(), "vtkPolyData");
  info->Set(vtkAlgorithm::INPUT_IS_REPEATABLE(), 1);
  info->Set(vtkAlgorithm::INPUT_IS_OPTIONAL(), 1);
  return 1;
}

int vtkOctreeBooleanFilter::RequestData(vtkInformation* /*request*/,
                                        vtkInformationVector** inputVector,
                                        vtkInformationVector* outputVector) {
  auto* output = vtkPolyData::GetData(outputVector);
  if (output == nullptr) {
    vtkErrorMacro(<< "Missing output.");
    return 0;
  }
  output->Initialize();
  this->EffectiveVoxelSize = 0.0;

  const int numberOfInputs = inputVector[0]->GetNumberOfInformationObjects();
  std::vector<vtkPolyData*> inputs(numberOfInputs);
  // Bounds of each input, not valid for the empty set
  std::vector<vtkBoundingBox> inputBounds(numberOfInputs);
  for (int i = 0; i < numberOfInputs; ++i) {
    inputs[i] = vtkPolyData::GetData(inputVector[0], i);
    if (inputs[i] != nullptr && inputs[i]->GetNumberOfPolys() + inputs[i]->GetNumberOfStrips() > 0) {
      if (!HasFinitePoints(inputs[i])) {
        vtkErrorMacro(<< "Input " << i << " has points with infinite or NaN coordinates.");
        return 0;
      }
      inputBounds[i].SetBounds(inputs[i]->GetBounds());
    }
  }

  // The result is within these bounds, so only they need voxels
  vtkBoundingBox resultBounds = numberOfInputs > 0 ? inputBounds[0] : vtkBoundingBox();
  for (int i = 1; i < numberOfInputs; ++i) {
    switch (this->GetOperation(i)) {
      case OPER_INTERSECTION:
        if (!resultBounds.IntersectBox(inputBounds[i])) {
          resultBounds.Reset();
        }
        break;
      case OPER_DIFFERENCE:
        break;
      case OPER_DIFFERENCE2:
        resultBounds = inputBounds[i];
        break;
      default:
        resultBounds.AddBox(inputBounds[i]);
        break;
    }
  }
  if (!resultBounds.IsValid() || resultBounds.GetMaxLength() <= 0.0) {
    return 1;
  }

  // Voxels cover the bounds with a margin of at least 2 voxels, so that the surface is closed
  const double voxelSize = this->VoxelSize > 0.0 ? this->VoxelSize : resultBounds.GetMaxLength() / 256.0;
  const int factor = 1 << this->ExtraLevels;
  double origin[3];
  int dimensions[3];
  double numberOfVoxels = 1.0;
  for (int axis = 0; axis < 3; ++axis) {
    origin[axis] = std::floor(resultBounds.GetMinPoint()[axis] / voxelSize) * voxelSize - 2.0 * voxelSize;
    const double size = std::ceil((resultBounds.GetMaxPoint()[axis] - origin[axis]) / voxelSize) + 3.0;
    numberOfVoxels *= size;
    // Fine voxel indices must fit in an int
    if (size * factor > INT_MAX / 2 || numberOfVoxels > static_cast<double>(this->MaximumNumberOfVoxels)) {
      vtkErrorMacro(<< "The voxel size " << voxelSize << " needs more voxels than the maximum ("
                    << this->MaximumNumberOfVoxels << "). Increase the voxel size.");
      return 0;
    }
    dimensions[axis] = static_cast<int>(size);
  }
  this->EffectiveVoxelSize = voxelSize;

  // Octrees of up to 64 voxels along each axis, and at least 8 octrees along the longest axis
  const int maximumDimension = std::max({dimensions[0], dimensions[1], dimensions[2]});
  const int voxelLevel = std::clamp(static_cast<int>(std::ceil(std::log2(maximumDimension))) - 3, 0, 6);
  const OctreeGrid grid(origin, voxelSize, dimensions, voxelLevel, this->ExtraLevels);

  try {
    auto buildInput = [&](int i) {
      return inputBounds[i].IsValid() ? grid.BuildFromSurface(inputs[i], inputBounds[i]) : grid.BuildEmpty();
    };
    Octrees result = buildInput(0);
    this->UpdateProgress(0.8 / numberOfInputs);
    for (int i = 1; i < numberOfInputs; ++i) {
      const Octrees next = buildInput(i);
      result = grid.Combine(result, next, this->GetOperation(i));
      this->UpdateProgress(0.8 * (i + 1) / numberOfInputs);
    }

    vtkNew<vtkImageData> fractions;
    fractions->SetDimensions(dimensions);
    fractions->SetOrigin(origin);
    fractions->SetSpacing(voxelSize, voxelSize, voxelSize);
    fractions->AllocateScalars(VTK_UNSIGNED_CHAR, 1);
    auto* voxels = static_cast<uint8_t*>(fractions->GetScalarPointer());
    std::fill_n(voxels, fractions->GetNumberOfPoints(), uint8_t(0));
    grid.Rasterize(result, voxels);
    result = Octrees();
    this->UpdateProgress(0.9);

    vtkNew<vtkFlyingEdges3D> contour;
    contour->SetInputData(fractions);
    // Fractions are integers, so no sample equals the value, which avoids degenerate triangles
    contour->SetValue(0, 127.5);
    contour->ComputeNormalsOff();
    contour->ComputeGradientsOff();
    contour->ComputeScalarsOff();
    contour->InterpolateAttributesOff();
    contour->Update();
    output->ShallowCopy(contour->GetOutput());
  } catch (const std::bad_alloc&) {
    vtkErrorMacro(<< "Not enough memory for voxel size " << voxelSize << ". Increase the voxel size.");
    return 0;
  }
  this->UpdateProgress(1.0);
  return 1;
}
