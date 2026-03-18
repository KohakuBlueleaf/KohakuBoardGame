#pragma once
#include "../state/state.hpp"


class PVS{
public:
  static int eval(State *state, int depth, int alpha, int beta, int ply = 0, bool can_null = true);
  static Move get_move(State *state, int depth);
};
