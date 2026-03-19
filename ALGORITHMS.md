# MiniChess Algorithms

## Overview

- **State Evaluation** — how good is this position?
  - Material Count
  - Piece-Square Tables (PST / KP Eval)
  - King Tropism
  - Mobility
  - NNUE (Neural Network)
- **Search** — which move leads to the best position?
  - MiniMax
  - Alpha-Beta Pruning
  - PVS (Principal Variation Search)
    - Iterative Deepening
    - Move Ordering (MVV-LVA, Killer Moves)
    - Transposition Table (Zobrist Hashing)
    - Quiescence Search
    - Null Move Pruning
    - Late Move Reduction

---

## State Evaluation

### Material Count

The simplest evaluation: count what pieces each side has left.

Every piece type has a value. Sum up your pieces, subtract the opponent's pieces. Positive means you're ahead.

```
piece_value = {pawn: 2, rook: 6, knight: 7, bishop: 8, queen: 20, king: 100}

eval(board, player):
    my_score = sum of piece_value[p] for each of my pieces
    opp_score = sum of piece_value[p] for each of opponent's pieces
    return my_score - opp_score
```

This tells you *what* you have, but not *where* it is. A knight in the center is worth more than one stuck in the corner.

---

### Piece-Square Tables (PST / KP Eval)

Assign a bonus or penalty to each piece based on which square it occupies. For example, knights love the center, pawns close to promotion are valuable, kings prefer the back rank for safety.

Build a 6x5 table for each piece type. Look up the piece's position and add the bonus to the material score.

```
pst[piece_type][row][col] = positional bonus

eval(board, player):
    score = 0
    for each of my pieces at (row, col):
        score += piece_value[piece] * 10       # material (scaled up)
        score += pst[piece][row][col]           # positional bonus
    for each of opponent's pieces at (row, col):
        score -= piece_value[piece] * 10
        score -= pst[piece][mirror(row)][col]   # mirror for opponent
    return score
```

The `mirror(row)` flips the board vertically so both sides use the same table from their own perspective.

---

### King Tropism

Pieces near the enemy king are threatening. Give a bonus to attacking pieces based on how close they are to the opponent's king.

```
tropism_weight = {rook: 3, knight: 3, bishop: 2, queen: 5}

king_tropism(piece, piece_pos, enemy_king_pos):
    dist = max(abs(row_diff), abs(col_diff))    # Chebyshev distance
    if dist <= 2:
        return tropism_weight[piece] * (3 - dist)
    return 0
```

This encourages the engine to bring pieces toward the enemy king rather than leaving them passive.

---

### Mobility

Having more legal moves means more options. Add a small bonus proportional to how many more moves you have than your opponent.

```
eval_mobility(state):
    my_moves = count of my legal moves
    opp_moves = count of opponent's legal moves
    return 2 * (my_moves - opp_moves)
```

This is expensive (you need to generate opponent's moves too) but captures an important positional concept.

---

### NNUE (Neural Network Evaluation)

Instead of hand-tuned rules, train a neural network to evaluate positions. The network learns from millions of self-play games what "good" and "bad" positions look like.

**Key ideas:**
- Extract features from the board (which pieces are on which squares)
- Feed through a small neural network (a few hundred neurons)
- Output: a score in centipawns

The "efficiently updatable" part means: when a piece moves, you only update the affected features instead of recomputing everything from scratch.

```
features = extract_features(board, perspective)    # sparse binary vector
accumulator = weight_matrix * features + bias      # only update changed features
hidden = screlu(accumulator)                       # squared clipped ReLU
output = linear_layers(hidden)                     # few small layers
score = output                                     # centipawns
```

Training requires a data generation pipeline (self-play) and a training loop (PyTorch), but inference is very fast — especially with SIMD or quantized integer arithmetic.

---

## Search Algorithms

### MiniMax

The foundation of all game tree search. The idea: I pick the move that maximizes my score, and my opponent picks the move that minimizes my score (or equivalently, maximizes their own).

With **negamax** formulation, we always maximize — but negate the score when switching sides. "My best is your worst."

```
minimax(state, depth):
    if depth == 0 or game_over:
        return evaluate(state)

    best = -infinity
    for each move in legal_moves:
        child = apply_move(state, move)
        score = -minimax(child, depth - 1)    # negate: opponent's best is our worst
        best = max(best, score)
    return best
```

**Problem:** explores every possible move at every depth. For a branching factor of 20 and depth 6, that's 20^6 = 64 million nodes. Way too slow for deep search.

---

### Alpha-Beta Pruning

The key insight: if you've already found a move that scores 5, and you discover the opponent has a reply that scores 7 (bad for you) in another branch, you can **stop exploring that branch**. The opponent would never let you reach the good position.

- **alpha**: the best score you can guarantee (lower bound)
- **beta**: the best score the opponent can guarantee (upper bound)
- If alpha >= beta, **prune** — this branch is irrelevant.

```
alphabeta(state, depth, alpha, beta):
    if depth == 0 or game_over:
        return evaluate(state)

    for each move in legal_moves:
        child = apply_move(state, move)
        score = -alphabeta(child, depth - 1, -beta, -alpha)
        alpha = max(alpha, score)
        if alpha >= beta:
            break           # prune: opponent won't allow this
    return alpha
```

With good move ordering (best moves first), alpha-beta prunes roughly half the tree. Effective branching factor drops from ~20 to ~√20 ≈ 4.5, enabling much deeper search.

---

### PVS (Principal Variation Search)

An optimization of alpha-beta. The idea: after searching the **first move** with a full window, assume it's probably the best (thanks to move ordering). Search remaining moves with a **zero-width window** (alpha, alpha+1) — a quick test asking "is this move better than what I already have?"

If the zero-width search says "yes, it might be better," re-search with the full window to get the exact score.

```
pvs(state, depth, alpha, beta):
    if depth == 0 or game_over:
        return evaluate(state)

    moves = order_moves(state)     # best moves first
    first = true

    for each move in moves:
        child = apply_move(state, move)

        if first:
            score = -pvs(child, depth-1, -beta, -alpha)    # full window
            first = false
        else:
            # null-window search: just test if better than alpha
            score = -pvs(child, depth-1, -(alpha+1), -alpha)
            if score > alpha and score < beta:
                # surprised — re-search with full window
                score = -pvs(child, depth-1, -beta, -alpha)

        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return alpha
```

PVS is faster than plain alpha-beta when move ordering is good (the first move is usually the best). The zero-width searches are very cheap because they prune aggressively.

---

### Iterative Deepening

Don't search directly at depth 10. Instead, search depth 1, then depth 2, then depth 3, ... up to the time limit. Each iteration is fast and seeds the transposition table for the next iteration.

```
iterative_deepening(state, time_limit):
    best_move = None
    for depth = 1, 2, 3, ...:
        result = pvs(state, depth, -infinity, +infinity)
        best_move = result.best_move
        if time_elapsed > time_limit / 2:
            break                   # not enough time for next depth
    return best_move
```

**Why not wasteful?** The last iteration dominates the cost. Depth 1 through depth N-1 combined cost less than depth N alone (exponential growth). And TT entries from shallower searches make deeper searches much faster.

---

### Move Ordering

Alpha-beta prunes most when the best move is searched first. Good ordering:

1. **TT best move** — the best move from a previous search of this position
2. **Captures by MVV-LVA** — Most Valuable Victim, Least Valuable Attacker. A pawn capturing a queen is searched before a queen capturing a pawn.
3. **Killer moves** — quiet moves that caused beta cutoffs at the same depth in sibling nodes
4. **Remaining quiet moves**

```
score_move(move):
    if move captures a piece:
        return victim_value * 100 - attacker_value   # MVV-LVA
    if move is a killer move at this ply:
        return 50                                      # below captures, above quiet
    return 0                                           # quiet move

order_moves(state):
    moves = legal_moves(state)
    sort moves by score_move descending
    if TT has a best move for this position:
        move TT best move to front
    return moves
```

---

### Transposition Table (Zobrist Hashing)

Different move orders can reach the same position. A transposition table caches search results so we never re-search a position we've already evaluated.

**Zobrist hashing**: assign a random 64-bit number to each (player, piece_type, row, col). The hash of a position is the XOR of all active piece keys. XOR is fast, incremental, and collision-resistant.

```
# initialization (once)
zobrist_key[player][piece][row][col] = random_64bit()
zobrist_side = random_64bit()

hash(board, player):
    h = 0
    for each piece on the board:
        h ^= zobrist_key[owner][piece_type][row][col]
    if player == black:
        h ^= zobrist_side
    return h
```

The TT stores: hash, depth, score, flag (exact/lower/upper), and best move.

```
tt_probe(hash, depth, alpha, beta):
    entry = tt[hash % tt_size]
    if entry.hash == hash and entry.depth >= depth:
        if entry.flag == EXACT:  return entry.score
        if entry.flag == LOWER and entry.score >= beta:  return entry.score
        if entry.flag == UPPER and entry.score <= alpha: return entry.score
    return None    # miss

tt_store(hash, depth, score, flag, best_move):
    entry = tt[hash % tt_size]
    if entry is empty or entry.depth <= depth:
        entry = {hash, depth, score, flag, best_move}
```

---

### Quiescence Search

At depth 0, the static eval can be misleading. If you just captured a queen but your queen is about to be captured back, the eval says you're winning — but you're not. This is the **horizon effect**.

Quiescence search continues searching **only capture moves** until the position is "quiet" (no more captures). The static eval is used as a lower bound ("stand pat").

```
quiescence(state, alpha, beta):
    stand_pat = evaluate(state)
    if stand_pat >= beta:
        return beta                 # position is already too good
    alpha = max(alpha, stand_pat)

    for each capture_move in legal_captures(state):
        child = apply_move(state, capture_move)
        score = -quiescence(child, -beta, -alpha)
        if score >= beta:
            return beta             # cut off
        alpha = max(alpha, score)

    return alpha
```

Called at depth 0 instead of static eval: `if depth == 0: return quiescence(state, alpha, beta)`.

---

### Null Move Pruning

If we skip our turn (do nothing) and the position is STILL so good that the opponent can't beat beta, then any real move will also beat beta. Prune early.

The assumption: in most positions, having the right to move is an advantage (zugzwang is rare in MiniChess).

```
# inside pvs, before searching moves:
if can_do_null_move and depth >= R + 1:
    null_state = state with player switched (skip turn)
    score = -pvs(null_state, depth - 1 - R, -beta, -(beta-1))
    if score >= beta:
        return beta         # prune: position is too good even without moving
```

R is the reduction depth (typically 2). The null move search is cheap because it's at reduced depth with a zero-width window.

---

### Late Move Reduction (LMR)

Moves ordered late in the move list are probably bad (thanks to move ordering). Search them at **reduced depth** first. Only if the reduced search suggests the move might be interesting, re-search at full depth.

```
# inside the pvs loop, for non-first moves:
if move_index >= FULL_DEPTH_MOVES and depth >= DEPTH_LIMIT:
    if move is not a capture and not a killer move:
        # reduced depth search
        score = -pvs(child, depth - 2, -(alpha+1), -alpha)
        if score <= alpha:
            continue        # confirmed bad, skip
        # otherwise fall through to full-depth search
```

This dramatically reduces the tree size for positions with many quiet moves, allowing deeper search on the promising lines.
