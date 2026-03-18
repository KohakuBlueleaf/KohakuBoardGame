CXX = g++
CXXFLAGS = --std=c++2a -Wall -Wextra -Wpedantic -g -O3 -march=native

SOURCES_DIR = src
UNITTEST_DIR = unittest

BUILD_DIR = build
STATE_SOURCE = $(SOURCES_DIR)/state/state.cpp
NNUE_SOURCE = $(SOURCES_DIR)/nnue/nnue.cpp
POLICY_DIR = $(SOURCES_DIR)/policy
UNITTESTS = $(wildcard $(UNITTEST_DIR)/*.cpp)
TARGET_UNITTEST = $(UNITTESTS:$(UNITTEST_DIR)/%_test.cpp=%)
TARGET_OTHER = selfplay benchmark datagen nnue_bench


.PHONY: all clean uci
all: |$(BUILD_DIR) uci $(TARGET_OTHER)

$(BUILD_DIR):
	mkdir "$(BUILD_DIR)"
	mkdir "$(UNITTEST_DIR)/build"

ifeq ($(OS), Windows_NT)
uci:
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/minichess-uci.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp src/uci/uci.cpp
$(TARGET_OTHER): %: $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/$@.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) -o $(UNITTEST_DIR)/build/$@_test.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
else
uci:
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/minichess-uci $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp src/uci/uci.cpp
$(TARGET_OTHER): %: $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/$@ $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) -o $(UNITTEST_DIR)/build/$@_test $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
endif
