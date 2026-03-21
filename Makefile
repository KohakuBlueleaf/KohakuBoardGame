CXX = g++
CXXFLAGS = --std=c++2a -Wall -Wextra -Wpedantic -g -O3 -march=native

SOURCES_DIR = src
UNITTEST_DIR = unittest

BUILD_DIR = build
STATE_SOURCE_MC = $(SOURCES_DIR)/games/minichess/state.cpp
STATE_SOURCE_MS = $(SOURCES_DIR)/games/minishogi/state.cpp
STATE_SOURCE_GK = $(SOURCES_DIR)/games/gomoku/state.cpp
STATE_SOURCE_KS = $(SOURCES_DIR)/games/kohaku_shogi/state.cpp
STATE_SOURCE_KC = $(SOURCES_DIR)/games/kohaku_chess/state.cpp
NNUE_SOURCE = $(SOURCES_DIR)/nnue/nnue.cpp
POLICY_SRC = $(wildcard $(SOURCES_DIR)/policy/*.cpp)
UNITTESTS = $(wildcard $(UNITTEST_DIR)/*.cpp)
TARGET_UNITTEST = $(UNITTESTS:$(UNITTEST_DIR)/%_test.cpp=%)

# Include paths
MINICHESS_INC = -Isrc/games/minichess -Isrc/state -Isrc
GOMOKU_INC = -Isrc/games/gomoku -Isrc/state -Isrc
MINISHOGI_INC = -Isrc/games/minishogi -Isrc/state -Isrc
KOHAKU_SHOGI_INC = -Isrc/games/kohaku_shogi -Isrc/state -Isrc
KOHAKU_CHESS_INC = -Isrc/games/kohaku_chess -Isrc/state -Isrc


.PHONY: all clean minichess gomoku minishogi kohaku_shogi kohaku_chess
.PHONY: datagen selfplay benchmark nnue_bench
.PHONY: minichess-datagen minishogi-datagen gomoku-datagen kohaku_shogi-datagen kohaku_chess-datagen
.PHONY: minichess-selfplay minishogi-selfplay gomoku-selfplay kohaku_shogi-selfplay kohaku_chess-selfplay
.PHONY: minichess-benchmark minishogi-benchmark gomoku-benchmark kohaku_shogi-benchmark kohaku_chess-benchmark
all: |$(BUILD_DIR) minichess minishogi gomoku kohaku_shogi kohaku_chess minichess-datagen minishogi-datagen gomoku-datagen kohaku_shogi-datagen kohaku_chess-datagen minichess-selfplay minishogi-selfplay gomoku-selfplay kohaku_shogi-selfplay kohaku_chess-selfplay minichess-benchmark minishogi-benchmark gomoku-benchmark kohaku_shogi-benchmark kohaku_chess-benchmark selfplay benchmark nnue_bench

$(BUILD_DIR):
	mkdir "$(BUILD_DIR)"
	mkdir "$(UNITTEST_DIR)/build"

ifeq ($(OS), Windows_NT)
# === Engine targets (Windows) ===
minichess:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-ubgi.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
gomoku:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-ubgi.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
minishogi:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-ubgi.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohaku_shogi:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-ubgi.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohaku_chess:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-ubgi.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp

# === Per-game datagen (Windows) ===
minichess-datagen:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-datagen.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
minishogi-datagen:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-datagen.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
gomoku-datagen:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-datagen.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohaku_shogi-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-datagen.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohaku_chess-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-datagen.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Per-game selfplay (Windows) ===
minichess-selfplay:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-selfplay.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
minishogi-selfplay:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-selfplay.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
gomoku-selfplay:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-selfplay.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohaku_shogi-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-selfplay.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohaku_chess-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-selfplay.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Per-game benchmark (Windows) ===
minichess-benchmark:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-benchmark.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
minishogi-benchmark:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-benchmark.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
gomoku-benchmark:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-benchmark.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohaku_shogi-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-benchmark.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohaku_chess-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-benchmark.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp

# === nnue_bench (Windows, minichess only) ===
nnue_bench:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/nnue_bench.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/nnue_bench.cpp

# === Backward-compatible aliases (Windows) ===
datagen: minichess-datagen
selfplay: minichess-selfplay
benchmark: minichess-benchmark

# === Unit tests (Windows) ===
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(UNITTEST_DIR)/build/$@_test.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) $<

else
# === Engine targets (Unix) ===
minichess:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-ubgi $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
gomoku:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-ubgi $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
minishogi:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-ubgi $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohaku_shogi:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-ubgi $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohaku_chess:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-ubgi $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp

# === Per-game datagen (Unix) ===
minichess-datagen:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-datagen $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
minishogi-datagen:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-datagen $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
gomoku-datagen:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-datagen $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohaku_shogi-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-datagen $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohaku_chess-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-datagen $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Per-game selfplay (Unix) ===
minichess-selfplay:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-selfplay $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
minishogi-selfplay:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-selfplay $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
gomoku-selfplay:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-selfplay $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohaku_shogi-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-selfplay $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohaku_chess-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-selfplay $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Per-game benchmark (Unix) ===
minichess-benchmark:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-benchmark $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
minishogi-benchmark:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-benchmark $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
gomoku-benchmark:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-benchmark $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohaku_shogi-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohaku_shogi-benchmark $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohaku_chess-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohaku_chess-benchmark $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp

# === nnue_bench (Unix, minichess only) ===
nnue_bench:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/nnue_bench $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/nnue_bench.cpp

# === Backward-compatible aliases (Unix) ===
datagen: minichess-datagen
selfplay: minichess-selfplay
benchmark: minichess-benchmark

# === Unit tests (Unix) ===
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(UNITTEST_DIR)/build/$@_test $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) $<

endif

clean:
	rm -f $(BUILD_DIR)/minichess-ubgi* $(BUILD_DIR)/gomoku-ubgi* $(BUILD_DIR)/minishogi-ubgi* $(BUILD_DIR)/kohaku_shogi-ubgi* $(BUILD_DIR)/kohaku_chess-ubgi* $(BUILD_DIR)/minichess-selfplay* $(BUILD_DIR)/minishogi-selfplay* $(BUILD_DIR)/gomoku-selfplay* $(BUILD_DIR)/kohaku_shogi-selfplay* $(BUILD_DIR)/kohaku_chess-selfplay* $(BUILD_DIR)/minichess-benchmark* $(BUILD_DIR)/minishogi-benchmark* $(BUILD_DIR)/gomoku-benchmark* $(BUILD_DIR)/kohaku_shogi-benchmark* $(BUILD_DIR)/kohaku_chess-benchmark* $(BUILD_DIR)/minichess-datagen* $(BUILD_DIR)/minishogi-datagen* $(BUILD_DIR)/gomoku-datagen* $(BUILD_DIR)/kohaku_shogi-datagen* $(BUILD_DIR)/kohaku_chess-datagen* $(BUILD_DIR)/nnue_bench*
