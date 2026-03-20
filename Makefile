CXX = g++
CXXFLAGS = --std=c++2a -Wall -Wextra -Wpedantic -g -O3 -march=native

SOURCES_DIR = src
UNITTEST_DIR = unittest

BUILD_DIR = build
STATE_SOURCE_MC = $(SOURCES_DIR)/games/minichess/state.cpp
STATE_SOURCE_MS = $(SOURCES_DIR)/games/minishogi/state.cpp
STATE_SOURCE_GK = $(SOURCES_DIR)/games/gomoku/state.cpp
NNUE_SOURCE = $(SOURCES_DIR)/nnue/nnue.cpp
POLICY_SRC = $(wildcard $(SOURCES_DIR)/policy/*.cpp)
UNITTESTS = $(wildcard $(UNITTEST_DIR)/*.cpp)
TARGET_UNITTEST = $(UNITTESTS:$(UNITTEST_DIR)/%_test.cpp=%)

# Include paths
MINICHESS_INC = -Isrc/games/minichess -Isrc/state -Isrc
GOMOKU_INC = -Isrc/games/gomoku -Isrc/state -Isrc
MINISHOGI_INC = -Isrc/games/minishogi -Isrc/state -Isrc


.PHONY: all clean minichess gomoku minishogi
.PHONY: datagen selfplay benchmark nnue_bench
.PHONY: minichess-datagen minishogi-datagen gomoku-datagen
.PHONY: minichess-selfplay minishogi-selfplay gomoku-selfplay
.PHONY: minichess-benchmark minishogi-benchmark gomoku-benchmark
all: |$(BUILD_DIR) minichess minishogi gomoku minichess-datagen minishogi-datagen gomoku-datagen minichess-selfplay minishogi-selfplay gomoku-selfplay minichess-benchmark minishogi-benchmark gomoku-benchmark selfplay benchmark nnue_bench

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

# === Per-game datagen (Windows) ===
minichess-datagen:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-datagen.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
minishogi-datagen:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-datagen.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
gomoku-datagen:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-datagen.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Per-game selfplay (Windows) ===
minichess-selfplay:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-selfplay.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
minishogi-selfplay:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-selfplay.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
gomoku-selfplay:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-selfplay.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Per-game benchmark (Windows) ===
minichess-benchmark:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-benchmark.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
minishogi-benchmark:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-benchmark.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
gomoku-benchmark:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-benchmark.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp

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

# === Per-game datagen (Unix) ===
minichess-datagen:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-datagen $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
minishogi-datagen:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-datagen $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
gomoku-datagen:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-datagen $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Per-game selfplay (Unix) ===
minichess-selfplay:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-selfplay $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
minishogi-selfplay:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-selfplay $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
gomoku-selfplay:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-selfplay $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Per-game benchmark (Unix) ===
minichess-benchmark:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-benchmark $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
minishogi-benchmark:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-benchmark $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
gomoku-benchmark:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-benchmark $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp

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
	rm -f $(BUILD_DIR)/minichess-ubgi* $(BUILD_DIR)/gomoku-ubgi* $(BUILD_DIR)/minishogi-ubgi* $(BUILD_DIR)/minichess-selfplay* $(BUILD_DIR)/minishogi-selfplay* $(BUILD_DIR)/gomoku-selfplay* $(BUILD_DIR)/minichess-benchmark* $(BUILD_DIR)/minishogi-benchmark* $(BUILD_DIR)/gomoku-benchmark* $(BUILD_DIR)/minichess-datagen* $(BUILD_DIR)/minishogi-datagen* $(BUILD_DIR)/gomoku-datagen* $(BUILD_DIR)/nnue_bench*
