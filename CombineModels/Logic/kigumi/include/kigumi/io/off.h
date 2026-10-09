#pragma once

#include <kigumi/Mesh_indices.h>
#include <kigumi/Triangle_soup.h>
#include <kigumi/io/ascii.h>

#include <cstdint>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace kigumi::io {

struct Off_signature {
  bool binary{};
};

inline std::istream& operator>>(std::istream& in, Off_signature& sig) {
  using namespace kigumi::io::ascii;

  std::string s;
  if (!(in >> s)) {
    return in;
  }

  std::string_view sv{s};
  if (sv.starts_with("ST")) {
    sv = sv.substr(2);
  }
  if (sv.starts_with('C')) {
    sv = sv.substr(1);
  }
  if (sv.starts_with('N')) {
    sv = sv.substr(1);
  }
  if (sv != "OFF") {
    in.setstate(std::ios::failbit);
    return in;
  }

  if (in >> opt_hash_comment_eof) {
    return in;
  }
  in.clear();

  if (in >> "BINARY"_c) {
    sig.binary = true;
  }

  return in >> opt_hash_comment_eof;
}

enum class Off_reading_state : std::uint8_t {
  READING_SIGNATURE,
  READING_NUMBERS,
  READING_VERTICES,
  READING_FACES,
  END,
};

template <class K, class FaceData>
bool read_off(std::istream& is, Triangle_soup<K, FaceData>& soup) {
  using namespace kigumi::io::ascii;
  using Triangle_soup = kigumi::Triangle_soup<K, FaceData>;

  if (!is) {
    return false;
  }

  Triangle_soup new_soup;

  std::size_t num_vertices{};
  std::size_t num_faces{};
  std::string line;
  std::string s;
  std::vector<Vertex_index> face;

  Off_reading_state state = Off_reading_state::READING_SIGNATURE;

  while (std::getline(is, line)) {
    std::istringstream iss{line};

    if (iss >> opt_hash_comment_eof) {
      continue;
    }
    iss.clear();

    switch (state) {
      case Off_reading_state::READING_SIGNATURE: {
        Off_signature sig;
        if (!(iss >> sig)) {
          std::cerr << "invalid header line: " << line << std::endl;
          return false;
        }
        if (sig.binary) {
          std::cerr << "binary OFF is not supported" << std::endl;
          return false;
        }
        state = Off_reading_state::READING_NUMBERS;
        break;
      }
      case Off_reading_state::READING_NUMBERS: {
        if (!(iss >> num_vertices >> num_faces)) {
          std::cerr << "invalid header line: " << line << std::endl;
          return false;
        }
        state = Off_reading_state::READING_VERTICES;
        if (num_vertices == 0) {
          state = Off_reading_state::READING_FACES;
          if (num_faces == 0) {
            state = Off_reading_state::END;
          }
        }
        break;
      }
      case Off_reading_state::READING_VERTICES: {
        Double x;
        Double y;
        Double z;
        if (!(iss >> x >> y >> z)) {
          std::cerr << "invalid vertex line: " << line << std::endl;
          return false;
        }
        new_soup.add_vertex({x.value, y.value, z.value});
        --num_vertices;
        if (num_vertices == 0) {
          state = Off_reading_state::READING_FACES;
          if (num_faces == 0) {
            state = Off_reading_state::END;
          }
        }
        break;
      }
      case Off_reading_state::READING_FACES: {
        face.clear();
        std::size_t count{};
        iss >> count;
        for (std::size_t i = 0; i < count; ++i) {
          std::size_t v{};
          iss >> v;
          face.push_back(Vertex_index{v});
        }
        if (!iss) {
          std::cout << "invalid face line: " << line << std::endl;
          return false;
        }
        if (face.size() >= 3) {
          for (std::size_t i = 0; i < face.size() - 2; ++i) {
            new_soup.add_face({face.at(0), face.at(i + 1), face.at(i + 2)});
          }
        }
        --num_faces;
        if (num_faces == 0) {
          state = Off_reading_state::END;
        }
        break;
      }
      case Off_reading_state::END:
        std::cout << "unexpected line: " << line << std::endl;
        return false;
    }
  }

  if (state != Off_reading_state::END) {
    std::cerr << "unexpected end of file" << std::endl;
    return false;
  }

  soup = std::move(new_soup);
  return true;
}

template <class K, class FaceData>
bool read_off(const std::string& filename, Triangle_soup<K, FaceData>& soup) {
  std::ifstream ifs{filename};
  if (!ifs) {
    std::cerr << "failed to open file: " << filename << std::endl;
    return false;
  }
  return read_off<K, FaceData>(ifs, soup);
}

template <class K, class FaceData>
bool write_off(std::ostream& os, const Triangle_soup<K, FaceData>& soup) {
  using namespace kigumi::io::ascii;

  if (!os) {
    return false;
  }

  os << "OFF\n"  //
     << soup.num_vertices() << ' ' << soup.num_faces() << " 0\n";

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
bool write_off(const std::string& filename, const Triangle_soup<K, FaceData>& soup) {
  std::ofstream ofs{filename};
  if (!ofs) {
    std::cerr << "failed to open file: " << filename << std::endl;
    return false;
  }
  return write_off<K, FaceData>(ofs, soup);
}

}  // namespace kigumi::io
