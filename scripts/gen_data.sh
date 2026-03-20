#!/bin/bash
# Generate training positions using parallel workers.
# Supports: minichess, minishogi, gomoku
#
# Usage: bash scripts/gen_data.sh [options]
#   -g GAME         Game type: minichess, minishogi, gomoku (default: minichess)
#   -p NUM_POS      Target positions (default: 1000000)
#   -w NUM_WORKERS  Parallel processes (default: 64)
#   -d DEPTH        Search depth (default: 6)
#   -e EPSILON      Jitter probability (default: 0.15)
#   -o OUTPUT_DIR   Output directory (default: data)

set -e

# Defaults
GAME="minichess"
TOTAL_POS=1000000
NUM_WORKERS=64
DEPTH=6
EPSILON=0.15
OUTPUT_DIR="data"

# Parse args
while getopts "g:p:w:d:e:o:h" opt; do
  case $opt in
    g) GAME=$OPTARG ;;
    p) TOTAL_POS=$OPTARG ;;
    w) NUM_WORKERS=$OPTARG ;;
    d) DEPTH=$OPTARG ;;
    e) EPSILON=$OPTARG ;;
    o) OUTPUT_DIR=$OPTARG ;;
    h) echo "Usage: $0 [-g game] [-p positions] [-w workers] [-d depth] [-e epsilon] [-o output_dir]"
       echo "  Games: minichess (6x5), minishogi (5x5), gomoku (9x9)"
       exit 0 ;;
    *) exit 1 ;;
  esac
done

# Per-game record size (header=12 bytes for v3, record = board + metadata)
# v3 record: board(2*H*W) + player(1) + score(2) + result(1) + ply(2) + best_move(2) = 2*H*W + 8
case "$GAME" in
  minichess)
    BOARD_CELLS=$((2 * 6 * 5))   # 60
    POS_PER_GAME=30
    ;;
  minishogi)
    BOARD_CELLS=$((2 * 5 * 5))   # 50
    POS_PER_GAME=40
    ;;
  gomoku)
    BOARD_CELLS=$((2 * 9 * 9))   # 162
    POS_PER_GAME=40
    ;;
  *)
    echo "Error: unknown game '$GAME'. Use: minichess, minishogi, gomoku"
    exit 1
    ;;
esac

RECORD_SIZE=$((BOARD_CELLS + 8))
HEADER_SIZE=12

TOTAL_GAMES=$(( (TOTAL_POS + POS_PER_GAME - 1) / POS_PER_GAME ))
GAMES_PER_WORKER=$(( (TOTAL_GAMES + NUM_WORKERS - 1) / NUM_WORKERS ))

BIN=./build/datagen_${GAME}

# Fall back to generic datagen if game-specific binary doesn't exist
if [ ! -f "$BIN" ]; then
  BIN=./build/datagen
fi

echo "=== ${GAME} Data Generation ==="
echo "  Game:       ${GAME}"
echo "  Target:     ~${TOTAL_POS} positions"
echo "  Games:      ${TOTAL_GAMES} total (${GAMES_PER_WORKER} per worker)"
echo "  Workers:    ${NUM_WORKERS}"
echo "  Depth:      ${DEPTH}"
echo "  Epsilon:    ${EPSILON}"
echo "  Record:     ${RECORD_SIZE} bytes"
echo "  Output dir: ${OUTPUT_DIR}"
echo ""

# Build if needed
if [ ! -f "$BIN" ]; then
  echo "Building datagen for ${GAME}..."
  make datagen GAME=${GAME}
fi

mkdir -p "$OUTPUT_DIR"

# Launch workers
echo "Launching ${NUM_WORKERS} workers..."
PIDS=()
for i in $(seq 0 $((NUM_WORKERS - 1))); do
  $BIN -n $GAMES_PER_WORKER -d $DEPTH -e $EPSILON \
       -s $i -o "${OUTPUT_DIR}/train_${i}.bin" 2>/dev/null &
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

  # Count positions from file sizes
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
  PCT=$(( POS_EST * 100 / TOTAL_POS ))

  # Calc pos/sec and ETA
  NOW=$(date +%s)
  ELAPSED=$((NOW - START_TIME))
  if [ $ELAPSED -gt 0 ] && [ $POS_EST -gt 0 ]; then
    POS_SEC=$((POS_EST / ELAPSED))
    REMAINING=$(( (TOTAL_POS - POS_EST) / (POS_SEC > 0 ? POS_SEC : 1) ))
    ETA_MIN=$((REMAINING / 60))
    ETA_SEC=$((REMAINING % 60))
    printf "\r  [%d/%d workers done] %d/%d pos (%d%%) | %d pos/s | ETA %dm%02ds   " \
      $DONE $NUM_WORKERS $POS_EST $TOTAL_POS $PCT $POS_SEC $ETA_MIN $ETA_SEC
  else
    printf "\r  [%d/%d workers done] %d/%d pos (%d%%) | starting...   " \
      $DONE $NUM_WORKERS $POS_EST $TOTAL_POS $PCT
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

echo "=== Done ==="
echo "  Game:       ${GAME}"
echo "  Files:      ${NUM_WORKERS} x .bin"
echo "  Positions:  ${TOTAL_RECORDS}"
echo "  Total size: $(( TOTAL_SIZE / 1024 / 1024 )) MB"
echo "  Wall time:  $((WALL_TIME / 60))m$((WALL_TIME % 60))s"
echo "  Throughput: $(( TOTAL_RECORDS / (WALL_TIME > 0 ? WALL_TIME : 1) )) pos/s"
echo ""
echo "To inspect: python3 scripts/read_data.py --game ${GAME} ${OUTPUT_DIR}/train_*.bin"
