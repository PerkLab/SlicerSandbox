#pragma once

#include <kigumi/kernel/Rational.h>

#include <boost/endian/conversion.hpp>
#include <cstdint>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>

namespace kigumi {

template <class To, class From>
To checked_cast(From value) {
  if (!std::in_range<To>(value)) {
    throw std::runtime_error("checked_cast failed");
  }

  return static_cast<To>(value);
}

template <class T>
struct Write {
  void operator()(std::ostream& out, const T& t) const {
    static_assert(std::is_arithmetic_v<T> && !std::is_same_v<T, bool>);

    T x{t};
    boost::endian::native_to_little_inplace(x);
    out.write(reinterpret_cast<const char*>(&x), sizeof(T));
  }
};

template <class T>
struct Read {
  void operator()(std::istream& in, T& t) const {
    static_assert(std::is_arithmetic_v<T> && !std::is_same_v<T, bool>);

    in.read(reinterpret_cast<char*>(&t), sizeof(T));
    boost::endian::little_to_native_inplace(t);
  }
};

template <class U, class T, std::enable_if_t<std::is_same_v<U, T>, std::nullptr_t> = nullptr>
void kigumi_write(std::ostream& out, const T& t) {
  Write<T>{}(out, t);
}

template <class U, class T, std::enable_if_t<!std::is_same_v<U, T>, std::nullptr_t> = nullptr>
void kigumi_write(std::ostream& out, const T& t) {
  Write<U>{}(out, checked_cast<U>(t));
}

template <class U, class T, std::enable_if_t<std::is_same_v<U, T>, std::nullptr_t> = nullptr>
void kigumi_read(std::istream& in, T& t) {
  Read<T>{}(in, t);
}

template <class U, class T, std::enable_if_t<!std::is_same_v<U, T>, std::nullptr_t> = nullptr>
void kigumi_read(std::istream& in, T& t) {
  U x{};
  Read<U>{}(in, x);
  t = checked_cast<T>(x);
}

template <>
struct Write<bool> {
  void operator()(std::ostream& out, const bool& t) const {
    kigumi_write<std::uint8_t>(out, static_cast<std::uint8_t>(t ? 1 : 0));
  }
};

template <>
struct Read<bool> {
  void operator()(std::istream& in, bool& t) const {
    std::uint8_t x{};
    kigumi_read<std::uint8_t>(in, x);
    t = x != 0;
  }
};

template <>
struct Write<Rational> {
  void operator()(std::ostream& out, const Rational& t) const {
    thread_local std::vector<std::uint8_t> buf;

    kigumi_write<bool>(out, t < 0);

    buf.clear();
    export_bits(numerator(t), std::back_inserter(buf), 8);
    kigumi_write<std::int32_t>(out, buf.size());
    out.write(reinterpret_cast<const char*>(buf.data()), static_cast<std::streamsize>(buf.size()));

    buf.clear();
    export_bits(denominator(t), std::back_inserter(buf), 8);
    kigumi_write<std::int32_t>(out, buf.size());
    out.write(reinterpret_cast<const char*>(buf.data()), static_cast<std::streamsize>(buf.size()));
  }
};

template <>
struct Read<Rational> {
  void operator()(std::istream& in, Rational& t) const {
    thread_local std::vector<std::uint8_t> buf;

    bool neg{};
    kigumi_read<bool>(in, neg);

    Integer num;
    Integer den;
    std::size_t count{};

    kigumi_read<std::int32_t>(in, count);
    buf.resize(count);
    in.read(reinterpret_cast<char*>(buf.data()), static_cast<std::streamsize>(count));
    import_bits(num, buf.begin(), buf.end());

    kigumi_read<std::int32_t>(in, count);
    buf.resize(count);
    in.read(reinterpret_cast<char*>(buf.data()), static_cast<std::streamsize>(count));
    import_bits(den, buf.begin(), buf.end());

    t = Rational{num, den};
    if (neg) {
      t = -std::move(t);
    }
  }
};

}  // namespace kigumi
