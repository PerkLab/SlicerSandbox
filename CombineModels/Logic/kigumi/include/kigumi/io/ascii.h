#pragma once

#include <fast_float/fast_float.h>

#include <array>
#include <charconv>
#include <iostream>
#include <limits>
#include <string>
#include <system_error>

namespace kigumi::io::ascii {

struct Double {
  double value{};
};

inline std::istream& operator>>(std::istream& in, Double& d) {
  thread_local std::string s;

  if (!(in >> s)) {
    return in;
  }
  const auto* first = s.front() == '+' ? s.data() + 1 : s.data();
  const auto* last = s.data() + s.size();
  auto [ptr, ec] = fast_float::from_chars(first, last, d.value);
  if (ptr != last || ec != std::errc{}) {
    in.setstate(std::ios::failbit);
  }

  return in;
}

inline std::ostream& operator<<(std::ostream& out, const Double& d) {
  std::array<char, 32> buffer;
  auto [ptr, ec] = std::to_chars(buffer.data(), buffer.data() + buffer.size(), d.value);
  out.write(buffer.data(), ptr - buffer.data());
  return out;
}

struct End_of_file {};

inline const End_of_file eof{};

inline std::istream& operator>>(std::istream& in, const End_of_file& /*eof*/) {
  if (in.eof()) {
    return in;
  }
  in >> std::ws;
  if (in.eof()) {
    return in;
  }
  in.setstate(std::ios::failbit);
  return in;
}

struct Opt_hash_comment_end_of_file {};

inline const Opt_hash_comment_end_of_file opt_hash_comment_eof;

inline std::istream& operator>>(std::istream& in,
                                const Opt_hash_comment_end_of_file& /*opt_hash_comment_eof*/) {
  if (!in || in >> eof) {
    return in;
  }
  in.clear();

  if (in.peek() != '#') {
    in.setstate(std::ios::failbit);
    return in;
  }

  in.ignore(std::numeric_limits<std::streamsize>::max());
  return in;
}

struct String_constant {
  std::string value;
};

inline String_constant operator""_c(const char* str, std::size_t len) {
  return {std::string{str, len}};
}

inline std::istream& operator>>(std::istream& in, const String_constant& str) {
  thread_local std::string s;

  if (!(in >> s) || s != str.value) {
    in.setstate(std::ios::failbit);
  }

  return in;
}

}  // namespace kigumi::io::ascii
