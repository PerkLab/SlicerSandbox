#pragma once

// Conversion between kigumi::Triangle_soup and vtkPolyData. Requires VTK (CommonCore and
// CommonDataModel).

#include <kigumi/Mesh_entities.h>
#include <kigumi/Mesh_indices.h>
#include <kigumi/Null_data.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/kernel/predicates.h>
#include <vtkCellArray.h>
#include <vtkCellArrayIterator.h>
#include <vtkIdTypeArray.h>
#include <vtkPoints.h>
#include <vtkPolyData.h>
#include <vtkSmartPointer.h>

#include <utility>

namespace kigumi {

// Converts the polygons and triangle strips of polydata into a triangle soup. Vertices and lines
// are ignored. Polygons with more than three vertices are interpreted as triangle fans.
// Degenerate triangles (with repeated or collinear vertices) are skipped unless
// skip_degenerate_triangles is false. face_data(cell_id) returns the data attached to the
// triangles that originate from the cell.
template <class K, class FaceData, class FaceDataFunction>
Triangle_soup<K, FaceData> to_triangle_soup(vtkPolyData* polydata, FaceDataFunction face_data,
                                            bool skip_degenerate_triangles = true) {
  Triangle_soup<K, FaceData> soup;
  if (polydata == nullptr) {
    return soup;
  }

  auto* points = polydata->GetPoints();
  auto num_points = points == nullptr ? vtkIdType{0} : points->GetNumberOfPoints();
  for (vtkIdType i = 0; i < num_points; ++i) {
    double p[3];
    points->GetPoint(i, p);
    soup.add_vertex({p[0], p[1], p[2]});
  }

  auto add_triangle = [&](vtkIdType a, vtkIdType b, vtkIdType c, vtkIdType cell_id) {
    if (skip_degenerate_triangles && (a == b || b == c || c == a)) {
      return;
    }
    Face f{Vertex_index{static_cast<std::size_t>(a)}, Vertex_index{static_cast<std::size_t>(b)},
           Vertex_index{static_cast<std::size_t>(c)}};
    if (skip_degenerate_triangles &&
        collinear(soup.point(f[0]), soup.point(f[1]), soup.point(f[2]))) {
      return;
    }
    auto fi = soup.add_face(f);
    soup.data(fi) = face_data(cell_id);
  };

  // Cell ids are ordered as vertices, lines, polygons, and strips.
  auto cell_id = polydata->GetNumberOfVerts() + polydata->GetNumberOfLines();

  vtkIdType n{};
  const vtkIdType* ids{};

  auto polys = vtk::TakeSmartPointer(polydata->GetPolys()->NewIterator());
  for (polys->GoToFirstCell(); !polys->IsDoneWithTraversal(); polys->GoToNextCell(), ++cell_id) {
    polys->GetCurrentCell(n, ids);
    for (vtkIdType i = 1; i + 1 < n; ++i) {
      add_triangle(ids[0], ids[i], ids[i + 1], cell_id);
    }
  }

  auto strips = vtk::TakeSmartPointer(polydata->GetStrips()->NewIterator());
  for (strips->GoToFirstCell(); !strips->IsDoneWithTraversal();
       strips->GoToNextCell(), ++cell_id) {
    strips->GetCurrentCell(n, ids);
    for (vtkIdType i = 0; i + 2 < n; ++i) {
      if (i % 2 == 0) {
        add_triangle(ids[i], ids[i + 1], ids[i + 2], cell_id);
      } else {
        add_triangle(ids[i + 1], ids[i], ids[i + 2], cell_id);
      }
    }
  }

  return soup;
}

template <class K>
Triangle_soup<K> to_triangle_soup(vtkPolyData* polydata) {
  return to_triangle_soup<K, Null_data>(polydata,
                                        [](vtkIdType /*cell_id*/) { return Null_data{}; });
}

// Converts a triangle soup into polydata with double-precision points. Coordinates that are not
// representable as doubles are rounded to the nearest. Cell i corresponds to face i.
template <class K, class FaceData>
vtkSmartPointer<vtkPolyData> to_polydata(const Triangle_soup<K, FaceData>& soup) {
  auto points = vtkSmartPointer<vtkPoints>::New();
  points->SetDataTypeToDouble();
  points->SetNumberOfPoints(static_cast<vtkIdType>(soup.num_vertices()));
  for (auto vi : soup.vertices()) {
    auto [x, y, z] = soup.point(vi).to_double();
    points->SetPoint(static_cast<vtkIdType>(vi.idx()), x, y, z);
  }

  auto offsets = vtkSmartPointer<vtkIdTypeArray>::New();
  auto connectivity = vtkSmartPointer<vtkIdTypeArray>::New();
  offsets->SetNumberOfValues(static_cast<vtkIdType>(soup.num_faces() + 1));
  connectivity->SetNumberOfValues(static_cast<vtkIdType>(3 * soup.num_faces()));
  vtkIdType j{};
  for (auto fi : soup.faces()) {
    offsets->SetValue(static_cast<vtkIdType>(fi.idx()), j);
    for (auto vi : soup.face(fi)) {
      connectivity->SetValue(j++, static_cast<vtkIdType>(vi.idx()));
    }
  }
  offsets->SetValue(static_cast<vtkIdType>(soup.num_faces()), j);

  auto polys = vtkSmartPointer<vtkCellArray>::New();
  polys->SetData(offsets, connectivity);

  auto polydata = vtkSmartPointer<vtkPolyData>::New();
  polydata->SetPoints(points);
  polydata->SetPolys(polys);
  return polydata;
}

}  // namespace kigumi
