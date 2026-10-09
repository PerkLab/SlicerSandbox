#pragma once

namespace kigumi {

template <class Options>
class Context {
 public:
  explicit Context(Options options) { current_ = options; }

  ~Context() { current_ = bak_; }

  Context(const Context&) = delete;
  Context(Context&&) = delete;
  Context& operator=(const Context&) = delete;
  Context& operator=(Context&&) = delete;

  static const Options& current() { return current_; }

 private:
  static thread_local inline Options current_{Options{}};
  Options bak_{current_};
};

}  // namespace kigumi
