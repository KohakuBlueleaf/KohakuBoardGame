#pragma once
#include "../state/state.hpp"


class PVS{
public:
  static int eval(State *state, int depth, int alpha, int beta);
  static Move get_move(State *state, int depth);
};
