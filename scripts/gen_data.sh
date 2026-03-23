#!/bin/bash
# Generate training positions using parallel workers.
# Supports: minichess, minishogi, gomoku, kohaku_shogi, kohaku_chess
#
# Usage: bash scripts/gen_data.sh [options]
#   -g GAME         Game type: minichess, minishogi, gomoku (default: minichess)
#   -n NUM_GAMES    Target games (default: 30000)
#   -w NUM_WORKERS  Parallel processes (default: 64)
#   -d DEPTH        Search depth (default: 6)
#   -e EPSILON      Jitter probability (default: 0.15)
#   -m MODEL        NNUE model file (optional, enables NNUE eval)
#   -o OUTPUT_DIR   Output directory (default: data)

set -e

# Defaults
GAME="minichess"
TOTAL_GAMES=30000
NUM_WORKERS=64
DEPTH=6
RANDOM_MOVES=8
RANDOM_MAXPLY=24
OUTPUT_DIR="data"
NNUE_MODEL=""

# Parse args
while getopts "g:n:w:d:r:p:o:m:h" opt; do
  case $opt in
    g) GAME=$OPTARG ;;
    n) TOTAL_GAMES=$OPTARG ;;
    w) NUM_WORKERS=$OPTARG ;;
    d) DEPTH=$OPTARG ;;
    r) RANDOM_MOVES=$OPTARG ;;
    p) RANDOM_MAXPLY=$OPTARG ;;
    o) OUTPUT_DIR=$OPTARG ;;
    m) NNUE_MODEL=$OPTARG ;;
    h) echo "Usage: $0 [-g game] [-n games] [-w workers] [-d depth] [-r random_moves] [-p random_maxply] [-m model] [-o output_dir]"
       echo "  Games: minichess, minishogi, gomoku, kohakushogi, kohakuchess"
       exit 0 ;;
    *) exit 1 ;;
  esac
done

# Normalize game name: accept kohaku_shogi, KohakuShogi, kohakushogi etc.
GAME=$(echo "$GAME" | tr '[:upper:]' '[:lower:]' | tr -d '_')

# Map normalized name to build binary name (Makefile uses underscores)
case "$GAME" in
  kohakushogi) BIN_GAME="kohaku_shogi" ;;
  kohakuchess) BIN_GAME="kohaku_chess" ;;
  *) BIN_GAME="$GAME" ;;
esac

# Per-game record size (header=12 bytes for v3, record = board + metadata)
# v3 record: board(2*H*W) + player(1) + score(2) + result(1) + ply(2) + best_move(2) = 2*H*W + 8
case "$GAME" in
  minichess)
    BOARD_CELLS=$((2 * 6 * 5))   # 60
    POS_PER_GAME=30
    ;;
  minishogi)
    BOARD_CELLS=$((2 * 5 * 5))   # 50
    HAND_CELLS=$((2 * 5))        # 10 (5 hand types per player)
    POS_PER_GAME=40
    ;;
  gomoku)
    BOARD_CELLS=$((2 * 15 * 15))  # 450
    POS_PER_GAME=40
    ;;
  kohakushogi)
    BOARD_CELLS=$((2 * 7 * 6))   # 84
    HAND_CELLS=$((2 * 7))        # 14 (7 hand types per player)
    POS_PER_GAME=70
    ;;
  kohakuchess)
    BOARD_CELLS=$((2 * 7 * 6))   # 84
    POS_PER_GAME=50
    ;;
  *)
    echo "Error: unknown game '$GAME'. Use: minichess, minishogi, gomoku, kohakushogi, kohakuchess"
    exit 1
    ;;
esac

# v5 record: board(BOARD_CELLS) + hand(HAND_CELLS) + player(1) + score(2) + result(1) + ply(2) + best_move(2)
HAND_CELLS=${HAND_CELLS:-2}  # default 2 (min 1 per player in C struct for games without hand)
RECORD_SIZE=$((BOARD_CELLS + HAND_CELLS + 8))
HEADER_SIZE=36  # v5 header size

GAMES_PER_WORKER=$(( (TOTAL_GAMES + NUM_WORKERS - 1) / NUM_WORKERS ))

BIN=./build/${BIN_GAME}-datagen

# Fall back to legacy name if game-specific binary doesn't exist
if [ ! -f "$BIN" ] && [ ! -f "${BIN}.exe" ]; then
  BIN=./build/datagen
fi

echo "=== ${GAME} Data Generation ==="
echo "  Game:       ${GAME}"
echo "  Target:     ${TOTAL_GAMES} games"
echo "  Games:      ${TOTAL_GAMES} total (${GAMES_PER_WORKER} per worker)"
echo "  Workers:    ${NUM_WORKERS}"
echo "  Depth:      ${DEPTH}"
echo "  Random:     ${RANDOM_MOVES} moves in first ${RANDOM_MAXPLY} plies"
if [ -n "$NNUE_MODEL" ]; then
echo "  NNUE:       ${NNUE_MODEL}"
fi
echo "  Record:     ${RECORD_SIZE} bytes"
echo "  Output dir: ${OUTPUT_DIR}"
echo ""

# Build if needed
if [ ! -f "$BIN" ] && [ ! -f "${BIN}.exe" ]; then
  echo "Building datagen for ${GAME}..."
  make ${BIN_GAME}-datagen
fi

mkdir -p "$OUTPUT_DIR"

# Launch workers
echo "Launching ${NUM_WORKERS} workers..."
PIDS=()
for i in $(seq 0 $((NUM_WORKERS - 1))); do
  NNUE_FLAG=""
  if [ -n "$NNUE_MODEL" ]; then
    NNUE_FLAG="-m $NNUE_MODEL"
  fi
  $BIN -n $GAMES_PER_WORKER -d $DEPTH -r $RANDOM_MOVES -p $RANDOM_MAXPLY \
       $NNUE_FLAG -s $i -o "${OUTPUT_DIR}/train_${i}.bin" 2>/dev/null &
  PIDS+=($!)
done

# Wait with progress polling
START_TIME=$(date +%s)
echo ""
while true; do
  sleep 5

  # Count finished workers
  DONE=0
  for pid in "${PIDS[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      DONE=$((DONE + 1))
    fi
  done

  # Estimate completed games from file sizes
  TOTAL_BYTES=0
  FILE_COUNT=0
  for f in "${OUTPUT_DIR}"/train_*.bin; do
    [ -f "$f" ] || continue
    FILE_COUNT=$((FILE_COUNT + 1))
    TOTAL_BYTES=$((TOTAL_BYTES + $(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)))
  done
  HEADER_TOTAL=$((FILE_COUNT * HEADER_SIZE))
  if [ $RECORD_SIZE -gt 0 ]; then
    POS_EST=$(( (TOTAL_BYTES - HEADER_TOTAL) / RECORD_SIZE ))
  else
    POS_EST=0
  fi
  GAMES_EST=$(( POS_EST / (POS_PER_GAME > 0 ? POS_PER_GAME : 1) ))
  PCT=$(( GAMES_EST * 100 / (TOTAL_GAMES > 0 ? TOTAL_GAMES : 1) ))

  # Calc games/sec and ETA
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TIME))
  if [ $ELAPSED -gt 0 ] && [ $GAMES_EST -gt 0 ]; then
    # Use awk for float division
    GAMES_SEC_STR=$(awk "BEGIN{printf \"%.1f\", $GAMES_EST / $ELAPSED}")
    POS_SEC_STR=$(awk "BEGIN{printf \"%.0f\", $POS_EST / $ELAPSED}")
    GAMES_SEC_RAW=$(awk "BEGIN{printf \"%.6f\", $GAMES_EST / $ELAPSED}")
    REMAINING=$(awk "BEGIN{r=($TOTAL_GAMES - $GAMES_EST) / ($GAMES_SEC_RAW > 0 ? $GAMES_SEC_RAW : 0.001); printf \"%d\", r}")
    ETA_MIN=$((REMAINING / 60))
    ETA_SEC=$((REMAINING % 60))
    printf "\r  [%d/%d workers done] ~%d/%d games (%d%%) %d pos | %s g/s %s pos/s | ETA %dm%02ds   " \
      $DONE $NUM_WORKERS $GAMES_EST $TOTAL_GAMES $PCT $POS_EST "$GAMES_SEC_STR" "$POS_SEC_STR" $ETA_MIN $ETA_SEC
  else
    printf "\r  [%d/%d workers done] ~%d/%d games (%d%%) | starting...   " \
      $DONE $NUM_WORKERS $GAMES_EST $TOTAL_GAMES $PCT
  fi

  # Exit when all workers done
  [ $DONE -ge $NUM_WORKERS ] && break
done

echo ""
echo ""

# Final stats
TOTAL_RECORDS=0
TOTAL_SIZE=0
for f in "${OUTPUT_DIR}"/train_*.bin; do
  [ -f "$f" ] || continue
  SZ=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null)
  RECORDS=$(( (SZ - HEADER_SIZE) / RECORD_SIZE ))
  TOTAL_RECORDS=$((TOTAL_RECORDS + RECORDS))
  TOTAL_SIZE=$((TOTAL_SIZE + SZ))
done

END_TIME=$(date +%s)
WALL_TIME=$((END_TIME - START_TIME))

TOTAL_GAMES_EST=$(( TOTAL_RECORDS / (POS_PER_GAME > 0 ? POS_PER_GAME : 1) ))

echo "=== Done ==="
echo "  Game:       ${GAME}"
echo "  Files:      ${NUM_WORKERS} x .bin"
echo "  Games:      ~${TOTAL_GAMES_EST}"
echo "  Positions:  ${TOTAL_RECORDS}"
echo "  Total size: $(( TOTAL_SIZE / 1024 / 1024 )) MB"
echo "  Wall time:  $((WALL_TIME / 60))m$((WALL_TIME % 60))s"
echo "  Throughput: $(awk "BEGIN{printf \"%.1f\", $TOTAL_GAMES_EST / ($WALL_TIME > 0 ? $WALL_TIME : 1)}") games/s"
echo ""
echo "To inspect: python3 scripts/read_data.py --game ${GAME} ${OUTPUT_DIR}/train_*.bin"
