CXX = g++
CXXFLAGS = --std=c++2a -Wall -Wextra -Wpedantic -g -O3 -march=native

SOURCES_DIR = src
UNITTEST_DIR = unittest

BUILD_DIR = build
STATE_SOURCE_MC = $(SOURCES_DIR)/games/minichess/state.cpp
STATE_SOURCE_MS = $(SOURCES_DIR)/games/minishogi/state.cpp
STATE_SOURCE_GK = $(SOURCES_DIR)/games/connect6/state.cpp
STATE_SOURCE_KS = $(SOURCES_DIR)/games/kohakushogi/state.cpp
STATE_SOURCE_KC = $(SOURCES_DIR)/games/kohakuchess/state.cpp
STATE_SOURCE_CH = $(SOURCES_DIR)/games/chess/state.cpp
NNUE_SOURCE = $(SOURCES_DIR)/nnue/nnue.cpp
POLICY_SRC = $(wildcard $(SOURCES_DIR)/policy/*.cpp)
UNITTESTS = $(wildcard $(UNITTEST_DIR)/*.cpp)
TARGET_UNITTEST = $(UNITTESTS:$(UNITTEST_DIR)/%_test.cpp=%)

# Include paths
MINICHESS_INC = -Isrc/games/minichess -Isrc/state -Isrc
CONNECT6_INC = -Isrc/games/connect6 -Isrc/state -Isrc
MINISHOGI_INC = -Isrc/games/minishogi -Isrc/state -Isrc
KOHAKU_SHOGI_INC = -Isrc/games/kohakushogi -Isrc/state -Isrc
KOHAKU_CHESS_INC = -Isrc/games/kohakuchess -Isrc/state -Isrc
CHESS_INC = -Isrc/games/chess -Isrc/state -Isrc


.PHONY: all clean minichess connect6 minishogi kohakushogi kohakuchess chess
.PHONY: datagen selfplay benchmark nnue_bench
.PHONY: minichess-datagen minishogi-datagen connect6-datagen kohakushogi-datagen kohakuchess-datagen
.PHONY: minichess-selfplay minishogi-selfplay connect6-selfplay kohakushogi-selfplay kohakuchess-selfplay
.PHONY: minichess-benchmark minishogi-benchmark connect6-benchmark kohakushogi-benchmark kohakuchess-benchmark
all: |$(BUILD_DIR) minichess minishogi connect6 kohakushogi kohakuchess minichess-datagen minishogi-datagen connect6-datagen kohakushogi-datagen kohakuchess-datagen minichess-selfplay minishogi-selfplay connect6-selfplay kohakushogi-selfplay kohakuchess-selfplay minichess-benchmark minishogi-benchmark connect6-benchmark kohakushogi-benchmark kohakuchess-benchmark selfplay benchmark nnue_bench

$(BUILD_DIR):
	mkdir "$(BUILD_DIR)"
	mkdir "$(UNITTEST_DIR)/build"

ifeq ($(OS), Windows_NT)
# === Engine targets (Windows) ===
minichess:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-ubgi.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
connect6:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-ubgi.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
minishogi:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-ubgi.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohakushogi:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-ubgi.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohakuchess:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-ubgi.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
chess:
	$(CXX) $(CXXFLAGS) $(CHESS_INC) -o $(BUILD_DIR)/chess-ubgi.exe $(STATE_SOURCE_CH) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp

# === Per-game datagen (Windows) ===
minichess-datagen:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-datagen.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
minishogi-datagen:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-datagen.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
connect6-datagen:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-datagen.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohakushogi-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-datagen.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohakuchess-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-datagen.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Per-game selfplay (Windows) ===
minichess-selfplay:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-selfplay.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
minishogi-selfplay:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-selfplay.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
connect6-selfplay:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-selfplay.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohakushogi-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-selfplay.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohakuchess-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-selfplay.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Per-game benchmark (Windows) ===
minichess-benchmark:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-benchmark.exe $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
minishogi-benchmark:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-benchmark.exe $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
connect6-benchmark:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-benchmark.exe $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohakushogi-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-benchmark.exe $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohakuchess-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-benchmark.exe $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp

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
connect6:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-ubgi $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
minishogi:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-ubgi $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohakushogi:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-ubgi $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
kohakuchess:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-ubgi $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp

# === Per-game datagen (Unix) ===
minichess-datagen:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-datagen $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
minishogi-datagen:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-datagen $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
connect6-datagen:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-datagen $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohakushogi-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-datagen $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp
kohakuchess-datagen:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-datagen $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/datagen.cpp

# === Per-game selfplay (Unix) ===
minichess-selfplay:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-selfplay $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
minishogi-selfplay:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-selfplay $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
connect6-selfplay:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-selfplay $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohakushogi-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-selfplay $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp
kohakuchess-selfplay:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-selfplay $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/selfplay.cpp

# === Per-game benchmark (Unix) ===
minichess-benchmark:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-benchmark $(STATE_SOURCE_MC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
minishogi-benchmark:
	$(CXX) $(CXXFLAGS) $(MINISHOGI_INC) -o $(BUILD_DIR)/minishogi-benchmark $(STATE_SOURCE_MS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
connect6-benchmark:
	$(CXX) $(CXXFLAGS) $(CONNECT6_INC) -DNO_NNUE -o $(BUILD_DIR)/connect6-benchmark $(STATE_SOURCE_GK) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohakushogi-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_SHOGI_INC) -o $(BUILD_DIR)/kohakushogi-benchmark $(STATE_SOURCE_KS) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp
kohakuchess-benchmark:
	$(CXX) $(CXXFLAGS) $(KOHAKU_CHESS_INC) -o $(BUILD_DIR)/kohakuchess-benchmark $(STATE_SOURCE_KC) $(NNUE_SOURCE) $(POLICY_SRC) src/benchmark.cpp

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
	rm -f $(BUILD_DIR)/minichess-ubgi* $(BUILD_DIR)/connect6-ubgi* $(BUILD_DIR)/minishogi-ubgi* $(BUILD_DIR)/kohakushogi-ubgi* $(BUILD_DIR)/kohakuchess-ubgi* $(BUILD_DIR)/minichess-selfplay* $(BUILD_DIR)/minishogi-selfplay* $(BUILD_DIR)/connect6-selfplay* $(BUILD_DIR)/kohakushogi-selfplay* $(BUILD_DIR)/kohakuchess-selfplay* $(BUILD_DIR)/minichess-benchmark* $(BUILD_DIR)/minishogi-benchmark* $(BUILD_DIR)/connect6-benchmark* $(BUILD_DIR)/kohakushogi-benchmark* $(BUILD_DIR)/kohakuchess-benchmark* $(BUILD_DIR)/minichess-datagen* $(BUILD_DIR)/minishogi-datagen* $(BUILD_DIR)/connect6-datagen* $(BUILD_DIR)/kohakushogi-datagen* $(BUILD_DIR)/kohakuchess-datagen* $(BUILD_DIR)/nnue_bench*
