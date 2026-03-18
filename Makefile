CXX = g++
CXX_MERGE = cpp-merge
CXXFLAGS = --std=c++2a -Wall -Wextra -Wpedantic -g -O3

SOURCES_DIR = src
UNITTEST_DIR = unittest

BUILD_DIR = build
SOURCES = $(wildcard $(SOURCES_DIR)/*.cpp)

MAIN = $(SOURCES_DIR)/main.cpp
PLAYERS = $(wildcard $(SOURCES_DIR)/player/*.cpp)
BASELINES = $(wildcard $(SOURCES_DIR)/baselines/*.cpp)
UNITTESTS = $(wildcard $(UNITTEST_DIR)/*.cpp)
STATE_SOURCE = $(SOURCES_DIR)/state/state.cpp
NNUE_SOURCE = $(SOURCES_DIR)/nnue/nnue.cpp
POLICY_DIR = $(SOURCES_DIR)/policy

TARGET_PLAYER = $(PLAYERS:$(SOURCES_DIR)/player/%.cpp=%)
TARGET_BASELINES = $(BASELINES:$(SOURCES_DIR)/baselines/%.cpp=%)
TARGET_MAIN = main
TARGET_OTHER = selfplay benchmark datagen nnue_bench
TARGET_UNITTEST = $(UNITTESTS:$(UNITTEST_DIR)/%_test.cpp=%)
OTHER = action state gamelog.txt


.PHONY: all clean
all: |$(BUILD_DIR) $(TARGET_MAIN) $(TARGET_PLAYER) $(TARGET_BASELINES)
player: |$(BUILD_DIR) $(TARGET_PLAYER)
baselines: |$(BUILD_DIR) $(TARGET_BASELINES)
merge: |$(MERGE_DIR) $(TARGET_MERGE_PLAYER) $(TARGET_MERGE_MAIN)

# make build dir if it doesn't exist
$(BUILD_DIR):
	mkdir "$(BUILD_DIR)"
	mkdir "$(BUILD_DIR)/baselines"
	mkdir "$(UNITTEST_DIR)/build"
$(MERGE_DIR):
	mkdir "$(MERGE_DIR)"

# build target
ifeq ($(OS), Windows_NT)
$(TARGET_PLAYER): % : $(SOURCES_DIR)/player/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/player_$@.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/$@.cpp $<
$(TARGET_BASELINES): % : $(SOURCES_DIR)/baselines/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/baselines/$@.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
$(TARGET_MAIN): % : $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/$@.exe $<
$(TARGET_OTHER): %: $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/$@.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) -o $(UNITTEST_DIR)/build/$@_test.exe $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
else
$(TARGET_PLAYER): % : $(SOURCES_DIR)/player/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/player_$@ $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/$@.cpp $<
$(TARGET_BASELINES): % : $(SOURCES_DIR)/baselines/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/baselines/$@ $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
$(TARGET_MAIN): % : $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/$@ $<
$(TARGET_OTHER): %: $(SOURCES_DIR)/%.cpp
	$(CXX) $(CXXFLAGS) -o $(BUILD_DIR)/$@ $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
$(TARGET_UNITTEST): %: $(UNITTEST_DIR)/%_test.cpp
	$(CXX) $(CXXFLAGS) -o $(UNITTEST_DIR)/build/$@_test $(STATE_SOURCE) $(NNUE_SOURCE) $(POLICY_DIR)/*.cpp $<
endif