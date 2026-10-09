#pragma once

#include <kigumi/Region.h>
#include <kigumi/io.h>

#include <fstream>
#include <iostream>
#include <string>

namespace kigumi {

template <class K, class FaceData>
bool read_kigumi_region(std::istream& is, Region<K, FaceData>& region) {
  if (!is) {
    return false;
  }
  kigumi_read<Region<K, FaceData>>(is, region);
  return is.good();
}

template <class K, class FaceData>
bool read_kigumi_region(const std::string& filename, Region<K, FaceData>& region) {
  std::ifstream ifs{filename, std::ios::binary};
  if (!ifs) {
    std::cerr << "failed to open file: " << filename << std::endl;
    return false;
  }
  return read_kigumi_region<K, FaceData>(ifs, region);
}

template <class K, class FaceData>
bool write_kigumi_region(std::ostream& os, const Region<K, FaceData>& region) {
  if (!os) {
    return false;
  }
  kigumi_write<Region<K, FaceData>>(os, region);
  return os.good();
}

template <class K, class FaceData>
bool write_kigumi_region(const std::string& filename, const Region<K, FaceData>& region) {
  std::ofstream ofs{filename, std::ios::binary};
  if (!ofs) {
    std::cerr << "failed to open file: " << filename << std::endl;
    return false;
  }
  return write_kigumi_region<K, FaceData>(ofs, region);
}

}  // namespace kigumi
