#include "vtkKigumiMeshDefectsFilter.h"

#include <kigumi/Exact_kernel.h>
#include <kigumi/Find_defects.h>
#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/threading.h>
#include <kigumi/vtk_polydata.h>

#include "vtkCellArray.h"
#include "vtkCellData.h"
#include "vtkIdTypeArray.h"
#include "vtkInformation.h"
#include "vtkInformationVector.h"
#include "vtkIntArray.h"
#include "vtkNew.h"
#include "vtkObjectFactory.h"
#include "vtkPoints.h"
#include "vtkPolyData.h"
#include "vtkSmartPointer.h"

#include <algorithm>
#include <exception>
#include <iterator>
#include <vector>

namespace {

using K = kigumi::Exact_kernel;

// The input cell that a face originates from.
struct Face_source {
  vtkIdType cell_id{-1};
};

using Triangle_soup = kigumi::Triangle_soup<K, Face_source>;

// Collects defects as the cells of a polydata that contains only the points they use.
class Defects_builder {
 public:
  explicit Defects_builder(const Triangle_soup& soup)
      : soup_{soup}, point_ids_(soup.num_vertices(), -1) {
    points_->SetDataTypeToDouble();
  }

  void add_vertex(kigumi::Vertex_index vi, int type) {
    verts_->InsertNextCell(1);
    verts_->InsertCellPoint(point_id(vi));
    vert_types_.push_back(type);
  }

  void add_edge(const kigumi::Edge& edge, int type) {
    lines_->InsertNextCell(2);
    lines_->InsertCellPoint(point_id(edge[0]));
    lines_->InsertCellPoint(point_id(edge[1]));
    line_types_.push_back(type);
  }

  void add_face(kigumi::Face_index fi, vtkIdType cell_id, int type) {
    polys_->InsertNextCell(3);
    for (auto vi : soup_.face(fi)) {
      polys_->InsertCellPoint(point_id(vi));
    }
    poly_types_.push_back(type);
    poly_cell_ids_.push_back(cell_id);
  }

  vtkSmartPointer<vtkPolyData> polydata() const {
    auto types = vtkSmartPointer<vtkIntArray>::New();
    types->SetName("DefectType");
    auto cell_ids = vtkSmartPointer<vtkIdTypeArray>::New();
    cell_ids->SetName("OrigCellId");
    // Cell ids are ordered as vertices, lines, and polygons.
    for (const auto* part_types : {&vert_types_, &line_types_}) {
      for (auto type : *part_types) {
        types->InsertNextValue(type);
        cell_ids->InsertNextValue(-1);
      }
    }
    for (std::size_t i = 0; i < poly_types_.size(); ++i) {
      types->InsertNextValue(poly_types_[i]);
      cell_ids->InsertNextValue(poly_cell_ids_[i]);
    }

    auto polydata = vtkSmartPointer<vtkPolyData>::New();
    polydata->SetPoints(points_);
    polydata->SetVerts(verts_);
    polydata->SetLines(lines_);
    polydata->SetPolys(polys_);
    polydata->GetCellData()->AddArray(types);
    polydata->GetCellData()->AddArray(cell_ids);
    return polydata;
  }

 private:
  vtkIdType point_id(kigumi::Vertex_index vi) {
    auto& id = point_ids_.at(vi.idx());
    if (id < 0) {
      auto [x, y, z] = soup_.point(vi).to_double();
      id = points_->InsertNextPoint(x, y, z);
    }
    return id;
  }

  const Triangle_soup& soup_;
  std::vector<vtkIdType> point_ids_;
  vtkNew<vtkPoints> points_;
  vtkNew<vtkCellArray> verts_;
  vtkNew<vtkCellArray> lines_;
  vtkNew<vtkCellArray> polys_;
  std::vector<int> vert_types_;
  std::vector<int> line_types_;
  std::vector<int> poly_types_;
  std::vector<vtkIdType> poly_cell_ids_;
};

template <class Range>
auto sorted(const Range& range) {
  std::vector<typename Range::value_type> values(range.begin(), range.end());
  std::sort(values.begin(), values.end());
  return values;
}

}  // namespace

vtkStandardNewMacro(vtkKigumiMeshDefectsFilter);

vtkKigumiMeshDefectsFilter::vtkKigumiMeshDefectsFilter() { this->SetNumberOfInputPorts(1); }

vtkKigumiMeshDefectsFilter::~vtkKigumiMeshDefectsFilter() = default;

void vtkKigumiMeshDefectsFilter::PrintSelf(ostream& os, vtkIndent indent) {
  this->Superclass::PrintSelf(os, indent);
  os << indent << "NumberOfFaces: " << this->NumberOfFaces << "\n";
  os << indent << "NumberOfIsolatedVertices: " << this->NumberOfIsolatedVertices << "\n";
  os << indent << "NumberOfNonManifoldVertices: " << this->NumberOfNonManifoldVertices << "\n";
  os << indent << "NumberOfBoundaryEdges: " << this->NumberOfBoundaryEdges << "\n";
  os << indent << "NumberOfInconsistentEdges: " << this->NumberOfInconsistentEdges << "\n";
  os << indent << "NumberOfNonManifoldEdges: " << this->NumberOfNonManifoldEdges << "\n";
  os << indent << "NumberOfDegenerateFaces: " << this->NumberOfDegenerateFaces << "\n";
  os << indent << "NumberOfSelfIntersectingFaces: " << this->NumberOfSelfIntersectingFaces
     << "\n";
  os << indent << "NumberOfThreads: " << this->NumberOfThreads << "\n";
}

int vtkKigumiMeshDefectsFilter::FillInputPortInformation(int /*port*/, vtkInformation* info) {
  info->Set(vtkAlgorithm::INPUT_REQUIRED_DATA_TYPE(), "vtkPolyData");
  return 1;
}

void vtkKigumiMeshDefectsFilter::ResetCounts() {
  this->NumberOfFaces = 0;
  this->NumberOfIsolatedVertices = 0;
  this->NumberOfNonManifoldVertices = 0;
  this->NumberOfBoundaryEdges = 0;
  this->NumberOfInconsistentEdges = 0;
  this->NumberOfNonManifoldEdges = 0;
  this->NumberOfDegenerateFaces = 0;
  this->NumberOfSelfIntersectingFaces = 0;
}

int vtkKigumiMeshDefectsFilter::RequestData(vtkInformation* /*request*/,
                                            vtkInformationVector** inputVector,
                                            vtkInformationVector* outputVector) {
  auto* input = vtkPolyData::GetData(inputVector[0]);
  auto* output = vtkPolyData::GetData(outputVector);

  this->ResetCounts();

  if (input == nullptr || output == nullptr) {
    vtkErrorMacro(<< "Missing input or output.");
    return 0;
  }

  try {
    kigumi::Threading_options threading_options;
    if (this->NumberOfThreads > 0) {
      threading_options.set_num_threads(static_cast<std::size_t>(this->NumberOfThreads));
    }
    kigumi::Threading_context threading_context{threading_options};

    // Keep degenerate triangles, so that they are reported.
    auto soup = kigumi::to_triangle_soup<K, Face_source>(
        input, [](vtkIdType cell_id) { return Face_source{cell_id}; }, false);
    this->NumberOfFaces = static_cast<vtkIdType>(soup.num_faces());
    if (soup.num_faces() == 0) {
      output->Initialize();
      return 1;
    }

    kigumi::Find_defects defects{soup};

    this->NumberOfIsolatedVertices = static_cast<vtkIdType>(defects.isolated_vertices().size());
    this->NumberOfNonManifoldVertices =
        static_cast<vtkIdType>(defects.non_manifold_vertices().size());
    this->NumberOfBoundaryEdges = static_cast<vtkIdType>(defects.boundary_edges().size());
    this->NumberOfInconsistentEdges = static_cast<vtkIdType>(defects.inconsistent_edges().size());
    this->NumberOfNonManifoldEdges = static_cast<vtkIdType>(defects.non_manifold_edges().size());
    this->NumberOfDegenerateFaces =
        static_cast<vtkIdType>(defects.trivial_degenerate_faces().size() +
                               defects.non_trivial_degenerate_faces().size());
    this->NumberOfSelfIntersectingFaces =
        static_cast<vtkIdType>(defects.overlapping_faces().size());

    // Faces of the merged soup are in the same order as those of the input soup.
    Defects_builder builder{defects.triangle_soup()};
    for (auto vi : sorted(defects.non_manifold_vertices())) {
      builder.add_vertex(vi, NON_MANIFOLD_VERTEX);
    }
    for (const auto& edge : sorted(defects.boundary_edges())) {
      builder.add_edge(edge, BOUNDARY_EDGE);
    }
    for (const auto& edge : sorted(defects.inconsistent_edges())) {
      builder.add_edge(edge, INCONSISTENT_EDGE);
    }
    for (const auto& edge : sorted(defects.non_manifold_edges())) {
      builder.add_edge(edge, NON_MANIFOLD_EDGE);
    }
    for (const auto* faces :
         {&defects.trivial_degenerate_faces(), &defects.non_trivial_degenerate_faces()}) {
      for (auto fi : sorted(*faces)) {
        builder.add_face(fi, soup.data(fi).cell_id, DEGENERATE_FACE);
      }
    }
    std::vector<kigumi::Face_index> overlapping_faces;
    for (const auto& [fi, other_fis] : defects.overlapping_faces()) {
      overlapping_faces.push_back(fi);
    }
    for (auto fi : sorted(overlapping_faces)) {
      builder.add_face(fi, soup.data(fi).cell_id, SELF_INTERSECTING_FACE);
    }

    output->ShallowCopy(builder.polydata());
  } catch (const std::exception& e) {
    vtkErrorMacro(<< "Finding defects failed: " << e.what());
    return 0;
  }

  return 1;
}
