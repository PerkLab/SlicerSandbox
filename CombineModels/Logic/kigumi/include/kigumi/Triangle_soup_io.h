#pragma once

#include <kigumi/io/obj.h>
#include <kigumi/io/off.h>
#include <kigumi/io/ply.h>

#include <iostream>
#include <string>

namespace kigumi {

template <class K, class FaceData>
bool read_triangle_soup(const std::string& filename, Triangle_soup<K, FaceData>& soup) {
  if (filename.ends_with(".obj")) {
    return io::read_obj(filename, soup);
  }
  if (filename.ends_with(".off")) {
    return io::read_off(filename, soup);
  }
  if (filename.ends_with(".ply")) {
    return io::read_ply(filename, soup);
  }
  std::cerr << "unsupported file format" << std::endl;
  return false;
}

template <class K, class FaceData>
bool write_triangle_soup(const std::string& filename, const Triangle_soup<K, FaceData>& soup) {
  if (filename.ends_with(".obj")) {
    return io::write_obj(filename, soup);
  }
  if (filename.ends_with(".off")) {
    return io::write_off(filename, soup);
  }
  if (filename.ends_with(".ply")) {
    return io::write_ply(filename, soup);
  }
  std::cerr << "unsupported file format" << std::endl;
  return false;
}

}  // namespace kigumi
