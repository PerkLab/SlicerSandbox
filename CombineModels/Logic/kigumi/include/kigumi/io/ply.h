#pragma once

#include <kigumi/Mesh_indices.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/io/ascii.h>

#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace kigumi::io {

enum class Ply_reading_state : std::uint8_t {
  READING_SIGNATURE,
  READING_VERSION,
  READING_ELEMENTS,
  READING_BODY,
};

struct Ply_property {
  std::string type;
  std::string list_count_type;
  std::string list_element_type;
  std::string name;
};

struct Ply_element {
  std::string name;
  std::size_t count{};
  std::vector<Ply_property> properties;
};

template <class K, class FaceData>
bool read_ply(std::istream& is, Triangle_soup<K, FaceData>& soup) {
  using namespace kigumi::io::ascii;
  using Triangle_soup = kigumi::Triangle_soup<K, FaceData>;

  if (!is) {
    return false;
  }

  std::string line;
  std::string s;
  std::vector<Ply_element> elements;

  Ply_reading_state state = Ply_reading_state::READING_SIGNATURE;

  // Read header.
  while (std::getline(is, line)) {
    std::istringstream iss{line};

    if (iss >> eof) {
      continue;
    }
    iss.clear();

    iss >> s;
    if (s == "comment") {
      continue;
    }

    switch (state) {
      case Ply_reading_state::READING_SIGNATURE: {
        if (s != "ply" || !(iss >> eof)) {
          std::cerr << "invalid header line: " << line << std::endl;
          return false;
        }
        state = Ply_reading_state::READING_VERSION;
        break;
      }
      case Ply_reading_state::READING_VERSION: {
        if (s != "format") {
          std::cerr << "invalid header line: " << line << std::endl;
          return false;
        }
        if (!(iss >> "ascii"_c >> "1.0"_c >> eof)) {
          std::cerr << "unsupported PLY version" << std::endl;
          return false;
        }
        state = Ply_reading_state::READING_ELEMENTS;
        break;
      }
      case Ply_reading_state::READING_ELEMENTS: {
        if (s == "element") {
          Ply_element element;
          if (!(iss >> element.name >> element.count >> eof)) {
            std::cerr << "invalid header line: " << line << std::endl;
            return false;
          }
          elements.push_back(std::move(element));
        } else if (s == "property") {
          if (elements.empty()) {
            std::cerr << "invalid header line: " << line << std::endl;
            return false;
          }
          Ply_property property;
          if (!(iss >> property.type)) {
            std::cerr << "invalid header line: " << line << std::endl;
            return false;
          }
          if (property.type == "list") {
            if (!(iss >> property.list_count_type >> property.list_element_type >> property.name >>
                  eof)) {
              std::cerr << "invalid header line: " << line << std::endl;
              return false;
            }
          } else {
            if (!(iss >> property.name >> eof)) {
              std::cerr << "invalid header line: " << line << std::endl;
              return false;
            }
          }
          elements.back().properties.push_back(std::move(property));
        } else if (s == "end_header") {
          state = Ply_reading_state::READING_BODY;
        } else {
          std::cerr << "invalid header line: " << line << std::endl;
          return false;
        }
        break;
      }
      default:
        break;
    }

    if (state == Ply_reading_state::READING_BODY) {
      break;
    }
  }

  if (state != Ply_reading_state::READING_BODY) {
    std::cerr << "unexpected end of file" << std::endl;
    return false;
  }

  auto find_element = [&](const std::string& name) {
    auto it = std::find_if(elements.begin(), elements.end(),
                           [&](const auto& e) { return e.name == name; });
    if (it == elements.end()) {
      std::cerr << "element " << name << " not found" << std::endl;
    }
    return it;
  };

  auto find_property = [](const Ply_element& element, const std::vector<std::string>& names,
                          bool list) {
    auto& properties = element.properties;
    auto it = std::find_if(properties.begin(), properties.end(), [&](const auto& p) {
      return std::find(names.begin(), names.end(), p.name) != names.end() &&
             (p.type == "list") == list;
    });
    if (it == properties.end()) {
      std::cerr << "property " << names.front() << " not found in element " << element.name
                << std::endl;
    }
    return it;
  };

  auto vertex_element_it = find_element("vertex");
  if (vertex_element_it == elements.end()) {
    return false;
  }
  auto x_property_it = find_property(*vertex_element_it, {"x"}, false);
  if (x_property_it == vertex_element_it->properties.end()) {
    return false;
  }
  auto y_property_it = find_property(*vertex_element_it, {"y"}, false);
  if (y_property_it == vertex_element_it->properties.end()) {
    return false;
  }
  auto z_property_it = find_property(*vertex_element_it, {"z"}, false);
  if (z_property_it == vertex_element_it->properties.end()) {
    return false;
  }

  auto face_element_it = find_element("face");
  if (face_element_it == elements.end()) {
    return false;
  }
  auto vertex_index_property_it =
      find_property(*face_element_it, {"vertex_index", "vertex_indices"}, true);
  if (vertex_index_property_it == face_element_it->properties.end()) {
    return false;
  }

  Triangle_soup new_soup;
  std::vector<Vertex_index> face;

  // Read body.
  auto element_it = elements.begin();
  while (element_it != elements.end() && element_it->count == 0) {
    ++element_it;
  }
  while (std::getline(is, line)) {
    if (element_it == elements.end()) {
      std::cerr << "unexpected line: " << line << std::endl;
      return false;
    }

    std::istringstream iss{line};

    auto& properties = element_it->properties;
    if (element_it == vertex_element_it) {
      Double x;
      Double y;
      Double z;
      for (auto it = properties.begin(); it != properties.end(); ++it) {
        if (it == x_property_it) {
          iss >> x;
        } else if (it == y_property_it) {
          iss >> y;
        } else if (it == z_property_it) {
          iss >> z;
        } else if (it->type == "list") {
          std::size_t count{};
          iss >> count;
          for (std::size_t i = 0; i < count; ++i) {
            iss >> s;
          }
        } else {
          iss >> s;
        }
      }
      if (!iss) {
        std::cerr << "invalid vertex line: " << line << std::endl;
        return false;
      }
      new_soup.add_vertex({x.value, y.value, z.value});
    } else if (element_it == face_element_it) {
      face.clear();
      for (auto it = properties.begin(); it != properties.end(); ++it) {
        if (it == vertex_index_property_it) {
          std::size_t count{};
          iss >> count;
          for (std::size_t i = 0; i < count; ++i) {
            std::size_t v{};
            iss >> v;
            face.push_back(Vertex_index{v});
          }
        } else if (it->type == "list") {
          std::size_t count{};
          iss >> count;
          for (std::size_t i = 0; i < count; ++i) {
            iss >> s;
          }
        } else {
          iss >> s;
        }
      }
      if (!iss) {
        std::cerr << "invalid face line: " << line << std::endl;
        return false;
      }
      if (face.size() >= 3) {
        for (std::size_t i = 0; i < face.size() - 2; ++i) {
          new_soup.add_face({face.at(0), face.at(i + 1), face.at(i + 2)});
        }
      }
    }

    --element_it->count;
    while (element_it != elements.end() && element_it->count == 0) {
      ++element_it;
    }
  }

  if (element_it != elements.end()) {
    std::cerr << "unexpected end of file" << std::endl;
    return false;
  }

  soup = std::move(new_soup);
  return true;
}

template <class K, class FaceData>
bool read_ply(const std::string& filename, Triangle_soup<K, FaceData>& soup) {
  std::ifstream ifs{filename};
  if (!ifs) {
    std::cerr << "failed to open file: " << filename << std::endl;
    return false;
  }
  return read_ply<K, FaceData>(ifs, soup);
}

template <class K, class FaceData>
bool write_ply(std::ostream& os, const Triangle_soup<K, FaceData>& soup) {
  using namespace kigumi::io::ascii;

  if (!os) {
    return false;
  }

  os << "ply\n"                                           //
     << "format ascii 1.0\n"                              //
     << "element vertex " << soup.num_vertices() << '\n'  //
     << "property float x\n"                              //
     << "property float y\n"                              //
     << "property float z\n"                              //
     << "element face " << soup.num_faces() << '\n'       //
     << "property list uchar int vertex_index\n";

  os << "end_header\n";

  for (auto vi : soup.vertices()) {
    const auto& p = soup.point(vi);
    auto [px, py, pz] = p.to_double();
    Double x{px};
    Double y{py};
    Double z{pz};
    os << x << ' ' << y << ' ' << z << '\n';
  }

  for (auto fi : soup.faces()) {
    const auto& f = soup.face(fi);
    os << "3 " << f[0].idx() << ' ' << f[1].idx() << ' ' << f[2].idx() << '\n';
  }

  return os.good();
}

template <class K, class FaceData>
bool write_ply(const std::string& filename, const Triangle_soup<K, FaceData>& soup) {
  std::ofstream ofs{filename};
  if (!ofs) {
    std::cerr << "failed to open file: " << filename << std::endl;
    return false;
  }
  return write_ply<K, FaceData>(ofs, soup);
}

}  // namespace kigumi::io
