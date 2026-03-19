CXX = g++
CXXFLAGS = --std=c++2a -Wall -Wextra -Wpedantic -g -O3 -march=native

SOURCES_DIR = src
UNITTEST_DIR = unittest

BUILD_DIR = build
STATE_SOURCE = $(SOURCES_DIR)/games/minichess/state.cpp
NNUE_SOURCE = $(SOURCES_DIR)/nnue/nnue.cpp
POLICY_SRC = $(wildcard $(SOURCES_DIR)/policy/*.cpp)
UNITTESTS = $(wildcard $(UNITTEST_DIR)/*.cpp)
TARGET_UNITTEST = $(UNITTESTS:$(UNITTEST_DIR)/%_test.cpp=%)
TARGET_OTHER = selfplay benchmark datagen nnue_bench

# Include paths
MINICHESS_INC = -Isrc/games/minichess -Isrc/state -Isrc
GOMOKU_INC = -Isrc/games/gomoku -Isrc/state -Isrc


.PHONY: all clean minichess gomoku
all: |$(BUILD_DIR) minichess $(TARGET_OTHER)

$(BUILD_DIR):
	mkdir "$(BUILD_DIR)"
	mkdir "$(UNITTEST_DIR)/build"

ifeq ($(OS), Windows_NT)
minichess:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-ubgi.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
gomoku:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-ubgi.exe src/games/gomoku/state.cpp $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
$(TARGET_OTHER): %: $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/$@.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_SRC) $<
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(UNITTEST_DIR)/build/$@_test.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_SRC) $<
else
minichess:
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/minichess-ubgi $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
gomoku:
	$(CXX) $(CXXFLAGS) $(GOMOKU_INC) -DNO_NNUE -o $(BUILD_DIR)/gomoku-ubgi src/games/gomoku/state.cpp $(NNUE_SOURCE) $(POLICY_SRC) src/ubgi/ubgi.cpp
$(TARGET_OTHER): %: $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(BUILD_DIR)/$@ $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_SRC) $<
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) $(MINICHESS_INC) -o $(UNITTEST_DIR)/build/$@_test $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_SRC) $<
endif

clean:
	rm -f $(BUILD_DIR)/minichess-ubgi* $(BUILD_DIR)/gomoku-ubgi* $(BUILD_DIR)/selfplay* $(BUILD_DIR)/benchmark* $(BUILD_DIR)/datagen* $(BUILD_DIR)/nnue_bench*
