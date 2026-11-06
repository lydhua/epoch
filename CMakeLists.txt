cmake_minimum_required(VERSION 3.20)
project(epoch VERSION 0.1.0 LANGUAGES CXX)

if(NOT UNIX)
  message(FATAL_ERROR "The simulator CLI currently requires a POSIX platform (macOS/Linux)")
endif()

option(EPOCH_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

add_library(epoch_simulator simulator/src/simulator.cpp simulator/src/atomic_output.cpp)
target_include_directories(epoch_simulator PUBLIC simulator/include)
target_compile_features(epoch_simulator PUBLIC cxx_std_20)
set_target_properties(epoch_simulator PROPERTIES CXX_EXTENSIONS OFF)

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  target_compile_options(epoch_simulator PUBLIC -Wall -Wextra -Wpedantic -Werror)
  if(EPOCH_SANITIZERS)
    target_compile_options(epoch_simulator PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(epoch_simulator PUBLIC -fsanitize=address,undefined)
  endif()
elseif(EPOCH_SANITIZERS)
  message(FATAL_ERROR "EPOCH_SANITIZERS requires Clang or GCC")
endif()

add_executable(epoch-simulate simulator/src/main.cpp)
target_link_libraries(epoch-simulate PRIVATE epoch_simulator)

include(CTest)
if(BUILD_TESTING)
  add_executable(simulator-tests simulator/tests/simulator_test.cpp)
  target_link_libraries(simulator-tests PRIVATE epoch_simulator)
  add_test(NAME simulator-unit COMMAND simulator-tests)

  add_executable(atomic-output-tests simulator/tests/atomic_output_test.cpp)
  target_link_libraries(atomic-output-tests PRIVATE epoch_simulator)
  add_test(NAME atomic-output-unit COMMAND atomic-output-tests "${CMAKE_CURRENT_BINARY_DIR}")

  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  add_test(NAME simulator-cli
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/simulator/tests/test_cli.py"
            "$<TARGET_FILE:epoch-simulate>")
  set_tests_properties(simulator-unit atomic-output-unit simulator-cli PROPERTIES TIMEOUT 60)
endif()
