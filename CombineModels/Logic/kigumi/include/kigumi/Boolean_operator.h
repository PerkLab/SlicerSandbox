#pragma once

#include <cstdint>

namespace kigumi {

// Face output table
//
//     |                  tag
//     |
//  op |   Ext.  |   Int.  |   Cop.  |   Opp.
// ----+---------+---------+---------+---------
//   V |         |         |         |
//   A |  A &  B |         |  A |  B |
//   B |      ~B |  A      |         |  A | ~B
//   C | ~A      |       B |         | ~A |  B
//   D |         | ~A & ~B | ~A | ~B |
//   E | ~A & ~B |  A &  B |         |
//   F | ~A      | ~A      | ~A | ~B | ~A |  B
//   G |      ~B |      ~B | ~A | ~B |  A | ~B
//   H |       B |       B |  A |  B | ~A |  B
//   I |  A      |  A      |  A |  B |  A | ~B
//   J |  A &  B | ~A & ~B |         |
//   K |         |  A &  B |  A |  B |
//   L |  A      |      ~B |         |  A | ~B
//   M |       B | ~A      |         | ~A |  B
//   X | ~A & ~B |         | ~A | ~B |
//   O |         |         |         |
//
// A & B: Output both A and B.
// A | B: Output either A or B.

enum class Boolean_operator : std::uint8_t {
  // Bochenski notation
  V = 0,   // The universe
  A = 1,   // A \cup B
  B = 2,   // (B \setminus A)^c
  C = 3,   // (A \setminus B)^c
  D = 4,   // (A \cap B)^c
  E = 5,   // (A \triangle B)^c
  F = 6,   // A^c
  G = 7,   // B^c
  H = 8,   // B
  I = 9,   // A
  J = 10,  // A \triangle B
  K = 11,  // A \cap B
  L = 12,  // A \setminus B
  M = 13,  // B \setminus A
  X = 14,  // (A \cup B)^c
  O = 15,  // The empty set

  // Aliases
  UNION = A,
  SYMMETRIC_DIFFERENCE = J,
  INTERSECTION = K,
  DIFFERENCE = L,
};

enum class Mask : std::uint8_t {
  NONE = 0,
  A = 1,
  B = 2,
  A_INV = 4,
  B_INV = 8,
};

inline Mask operator|(Mask a, Mask b) {
  return static_cast<Mask>(static_cast<std::uint8_t>(a) | static_cast<std::uint8_t>(b));
}

inline Mask operator&(Mask a, Mask b) {
  return static_cast<Mask>(static_cast<std::uint8_t>(a) & static_cast<std::uint8_t>(b));
}

inline Mask exterior_mask(Boolean_operator op) {
  switch (op) {
    case Boolean_operator::I:
    case Boolean_operator::L:
      return Mask::A;
    case Boolean_operator::H:
    case Boolean_operator::M:
      return Mask::B;
    case Boolean_operator::A:
    case Boolean_operator::J:
      return Mask::A | Mask::B;
    case Boolean_operator::C:
    case Boolean_operator::F:
      return Mask::A_INV;
    case Boolean_operator::B:
    case Boolean_operator::G:
      return Mask::B_INV;
    case Boolean_operator::E:
    case Boolean_operator::X:
      return Mask::A_INV | Mask::B_INV;
    default:
      return Mask::NONE;
  }
}

inline Mask interior_mask(Boolean_operator op) {
  switch (op) {
    case Boolean_operator::B:
    case Boolean_operator::I:
      return Mask::A;
    case Boolean_operator::C:
    case Boolean_operator::H:
      return Mask::B;
    case Boolean_operator::E:
    case Boolean_operator::K:
      return Mask::A | Mask::B;
    case Boolean_operator::F:
    case Boolean_operator::M:
      return Mask::A_INV;
    case Boolean_operator::G:
    case Boolean_operator::L:
      return Mask::B_INV;
    case Boolean_operator::D:
    case Boolean_operator::J:
      return Mask::A_INV | Mask::B_INV;
    default:
      return Mask::NONE;
  }
}

inline Mask coplanar_mask(Boolean_operator op, bool prefer_a) {
  switch (op) {
    case Boolean_operator::A:
    case Boolean_operator::H:
    case Boolean_operator::I:
    case Boolean_operator::K:
      return prefer_a ? Mask::A : Mask::B;
    case Boolean_operator::D:
    case Boolean_operator::F:
    case Boolean_operator::G:
    case Boolean_operator::X:
      return prefer_a ? Mask::A_INV : Mask::B_INV;
    default:
      return Mask::NONE;
  }
}

inline Mask opposite_mask(Boolean_operator op, bool prefer_a) {
  switch (op) {
    case Boolean_operator::B:
    case Boolean_operator::G:
    case Boolean_operator::I:
    case Boolean_operator::L:
      return prefer_a ? Mask::A : Mask::B_INV;
    case Boolean_operator::C:
    case Boolean_operator::F:
    case Boolean_operator::H:
    case Boolean_operator::M:
      return prefer_a ? Mask::A_INV : Mask::B;
    default:
      return Mask::NONE;
  }
}

}  // namespace kigumi
