# Pass as CMAKE_PROJECT_PS2RetroX_INCLUDE when configuring the runtime.
# Defer until the runtime and recompiler targets have been declared.
if(NOT TARGET ps2_runtime)
    if(GOW_GUEST_CALLS_DEFERRED)
        message(FATAL_ERROR "Guest-call tests require PS2X_BUILD_RUNTIME=ON")
    endif()
    set(GOW_GUEST_CALLS_DEFERRED TRUE)
    cmake_language(EVAL CODE "cmake_language(DEFER CALL include [[${CMAKE_CURRENT_LIST_FILE}]])")
    return()
endif()
if(NOT TARGET ps2_recomp_lib)
    message(FATAL_ERROR "Guest-call tests require PS2X_BUILD_RECOMP=ON")
endif()
add_executable(gow_guest_calls "${CMAKE_CURRENT_LIST_DIR}/guest_calls.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xTest/src/test_function_table.cpp")
target_compile_features(gow_guest_calls PRIVATE cxx_std_20)
target_include_directories(gow_guest_calls PRIVATE
    "${CMAKE_SOURCE_DIR}/ps2xRuntime/include"
    "${CMAKE_SOURCE_DIR}/ps2xRecomp/include")
target_link_libraries(gow_guest_calls PRIVATE ps2_runtime ps2_recomp_lib)
add_executable(gow_codegen_tests "${CMAKE_CURRENT_LIST_DIR}/guest_codegen_tests.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xTest/src/code_generator_tests.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xTest/src/test_function_table.cpp")
target_compile_features(gow_codegen_tests PRIVATE cxx_std_20)
target_include_directories(gow_codegen_tests PRIVATE
    "${CMAKE_SOURCE_DIR}/ps2xTest/include"
    "${CMAKE_SOURCE_DIR}/ps2xRuntime/include"
    "${CMAKE_SOURCE_DIR}/ps2xRecomp/include")
target_link_libraries(gow_codegen_tests PRIVATE ps2_runtime ps2_recomp_lib)
# Isolate memory/DMA tests from unrelated stale upstream test modules.
add_executable(gow_memory_tests "${CMAKE_CURRENT_LIST_DIR}/guest_memory_tests.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xTest/src/ps2_memory_tests.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xTest/src/test_function_table.cpp")
target_compile_features(gow_memory_tests PRIVATE cxx_std_20)
target_include_directories(gow_memory_tests PRIVATE
    "${CMAKE_SOURCE_DIR}/ps2xTest/include" "${CMAKE_SOURCE_DIR}/ps2xRuntime/include"
    "${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib")
target_link_libraries(gow_memory_tests PRIVATE ps2_runtime)
if(MSVC)
    target_link_options(gow_memory_tests PRIVATE /STACK:8388608)
elseif(MINGW)
    target_link_options(gow_memory_tests PRIVATE -Wl,--stack,8388608)
endif()
enable_testing()
add_test(NAME gow_memory_tests COMMAND gow_memory_tests)
add_executable(gow_texture_budget_tests "${CMAKE_CURRENT_LIST_DIR}/gs-texture-budget.cpp")
target_compile_features(gow_texture_budget_tests PRIVATE cxx_std_20)
target_include_directories(gow_texture_budget_tests PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/include")
add_test(NAME gow_texture_budget_tests COMMAND gow_texture_budget_tests)
add_executable(gow_texture_upload_test EXCLUDE_FROM_ALL "${CMAKE_CURRENT_LIST_DIR}/gs-texture-upload.cpp")
target_link_libraries(gow_texture_upload_test PRIVATE ps2_runtime)
set_tests_properties(gow_memory_tests PROPERTIES TIMEOUT 120)
add_executable(gow_frame_metrics "${CMAKE_CURRENT_LIST_DIR}/frame_metrics.cpp")
target_compile_features(gow_frame_metrics PRIVATE cxx_std_20)
target_include_directories(gow_frame_metrics PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/include")
add_test(NAME gow_frame_metrics COMMAND gow_frame_metrics)
add_test(NAME gow_codegen_tests COMMAND gow_codegen_tests)
# The codegen suite reads instructions.h relative to its working directory.
set_tests_properties(gow_codegen_tests PROPERTIES WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
if(MSVC)
    target_link_options(gow_guest_calls PRIVATE /STACK:8388608)
    target_link_options(gow_codegen_tests PRIVATE /STACK:8388608)
elseif(MINGW)
    target_link_options(gow_guest_calls PRIVATE -Wl,--stack,8388608)
    target_link_options(gow_codegen_tests PRIVATE -Wl,--stack,8388608)
endif()

# Exercise the same native VU1 runtime with procedural microcode (no disc required).
add_executable(gow_vu1_x64_fuzz_test "${CMAKE_SOURCE_DIR}/../tests/vu1_x64_fuzz_test.cpp")
target_compile_features(gow_vu1_x64_fuzz_test PRIVATE cxx_std_20)
target_link_libraries(gow_vu1_x64_fuzz_test PRIVATE ps2_runtime)
add_executable(gow_dma_worker_tests "${CMAKE_CURRENT_LIST_DIR}/dma_worker_tests.cpp")
target_compile_features(gow_dma_worker_tests PRIVATE cxx_std_20)
target_link_libraries(gow_dma_worker_tests PRIVATE ps2_runtime)
add_test(NAME gow_dma_worker_tests COMMAND gow_dma_worker_tests)
set_tests_properties(gow_dma_worker_tests PROPERTIES TIMEOUT 30)
add_executable(gow_vu1_tasks "${CMAKE_CURRENT_LIST_DIR}/vu1_tasks.cpp")
target_compile_features(gow_vu1_tasks PRIVATE cxx_std_20)
target_link_libraries(gow_vu1_tasks PRIVATE ps2_runtime)
# The IOP mixer alone (no game data): saturation of a full mix and envelopes that reach silence.
add_executable(gow_sound_regression "${CMAKE_CURRENT_LIST_DIR}/sound_regression.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xIOP/src/emulator/core/sound_engine.cpp")
target_compile_features(gow_sound_regression PRIVATE cxx_std_20)
target_include_directories(gow_sound_regression PRIVATE "${CMAKE_SOURCE_DIR}/ps2xIOP/src/emulator/core")
add_test(NAME gow_sound_regression COMMAND gow_sound_regression)
set_tests_properties(gow_sound_regression PROPERTIES TIMEOUT 60)
# Hold instead of mashing (patch 53) alone: short presses untouched, held buttons become presses at 60 and 30 fps polls.
add_executable(gow_qte_hold_test "${CMAKE_CURRENT_LIST_DIR}/qte_hold_test.cpp")
target_compile_features(gow_qte_hold_test PRIVATE cxx_std_20)
target_include_directories(gow_qte_hold_test PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/include")
add_test(NAME gow_qte_hold_test COMMAND gow_qte_hold_test)
set_tests_properties(gow_qte_hold_test PROPERTIES TIMEOUT 60)
add_executable(gow_qte_input_test "${CMAKE_CURRENT_LIST_DIR}/qte_input_test.cpp"
    "${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib/ps2_pad.cpp")
target_compile_features(gow_qte_input_test PRIVATE cxx_std_20)
target_include_directories(gow_qte_input_test PRIVATE "${CMAKE_SOURCE_DIR}/ps2xRuntime/include"
    "$<TARGET_PROPERTY:raylib,INTERFACE_INCLUDE_DIRECTORIES>")
foreach(mode IN ITEMS off shake rotate smoke)
    add_test(NAME gow_qte_input_${mode} COMMAND gow_qte_input_test ${mode})
endforeach()
