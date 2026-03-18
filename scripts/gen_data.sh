#!/bin/bash
# Generate training positions using parallel workers.
# Assumes ~30 positions per game.
#
# Usage: bash scripts/gen_data.sh [options]
#   -p NUM_POS      Target positions (default: 1000000)
#   -w NUM_WORKERS  Parallel processes (default: 64)
#   -d DEPTH        Search depth (default: 6)
#   -e EPSILON      Jitter probability (default: 0.15)
#   -o OUTPUT_DIR   Output directory (default: data)

set -e

# Defaults
TOTAL_POS=1000000
NUM_WORKERS=64
DEPTH=6
EPSILON=0.15
OUTPUT_DIR="data"

# Parse args
while getopts "p:w:d:e:o:h" opt; do
  case $opt in
    p) TOTAL_POS=$OPTARG ;;
    w) NUM_WORKERS=$OPTARG ;;
    d) DEPTH=$OPTARG ;;
    e) EPSILON=$OPTARG ;;
    o) OUTPUT_DIR=$OPTARG ;;
    h) echo "Usage: $0 [-p positions] [-w workers] [-d depth] [-e epsilon] [-o output_dir]"; exit 0 ;;
    *) exit 1 ;;
  esac
done

POS_PER_GAME=30
TOTAL_GAMES=$(( (TOTAL_POS + POS_PER_GAME - 1) / POS_PER_GAME ))
GAMES_PER_WORKER=$(( (TOTAL_GAMES + NUM_WORKERS - 1) / NUM_WORKERS ))

BIN=./build/datagen

echo "=== MiniChess Data Generation ==="
echo "  Target:     ~${TOTAL_POS} positions"
echo "  Games:      ${TOTAL_GAMES} total (${GAMES_PER_WORKER} per worker)"
echo "  Workers:    ${NUM_WORKERS}"
echo "  Depth:      ${DEPTH}"
echo "  Epsilon:    ${EPSILON}"
echo "  Output dir: ${OUTPUT_DIR}"
echo ""

# Build if needed
if [ ! -f "$BIN" ]; then
  echo "Building datagen..."
  make datagen
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
  HEADER_TOTAL=$((FILE_COUNT * 12))
  POS_EST=$(( (TOTAL_BYTES - HEADER_TOTAL) / 66 ))
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
  RECORDS=$(( (SZ - 12) / 66 ))
  TOTAL_RECORDS=$((TOTAL_RECORDS + RECORDS))
  TOTAL_SIZE=$((TOTAL_SIZE + SZ))
done

END_TIME=$(date +%s)
WALL_TIME=$((END_TIME - START_TIME))

echo "=== Done ==="
echo "  Files:      ${NUM_WORKERS} x .bin"
echo "  Positions:  ${TOTAL_RECORDS}"
echo "  Total size: $(( TOTAL_SIZE / 1024 / 1024 )) MB"
echo "  Wall time:  $((WALL_TIME / 60))m$((WALL_TIME % 60))s"
echo "  Throughput: $(( TOTAL_RECORDS / (WALL_TIME > 0 ? WALL_TIME : 1) )) pos/s"
echo ""
echo "To inspect: python3 scripts/read_data.py ${OUTPUT_DIR}/train_*.bin"
