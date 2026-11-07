# Regression gate independent of copyrighted game data.
if ($Stages -contains 'verify') {
    Step 'verify runtime and code generation'
    Use-Clang
    Native $python @('-I', (Join-Path $root 'tools/test/pipeline_tests.py')) 'pipeline regression tests'
    Native $python @('-I', (Join-Path $root 'tools/test/pr26-integration-tests.py')) 'mod identity, dependencies and frame-equivalence regressions'
    Native (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'tools/test/pgo-eligibility-tests.ps1')) 'PGO eligibility regressions'
    Native $python @('-I', (Join-Path $root 'tools/disc/import_test.py')) 'disc import regression tests'
    Native $python @('-I', (Join-Path $root 'tools/test/worker-ab-tests.py')) 'worker comparison methodology tests'
    Native $python @('-I', (Join-Path $root 'tools/test/gs-run-ab-tests.py')) 'GS comparison methodology and save isolation tests'
    Native $python @('-I', (Join-Path $root 'tools/test/render-delivery-tests.py'), '--runtime', (Join-Path $rec 'ps2xRuntime'), '--compiler', (Join-Path $script:llvmBin 'clang++.exe'), '--output', (Join-Path $logs 'render-delivery')) 'GS run encoder and vertex-ring fences (extracted, ASan)'
    Native $python @('-I', (Join-Path $root 'tools/test/finish-countdown-tests.py'), '--runtime', (Join-Path $rec 'ps2xRuntime'), '--compiler', (Join-Path $script:llvmBin 'clang++.exe'), '--output', (Join-Path $logs 'finish-countdown')) 'EE countdown checkpoint equivalence'
    Native $python @('-I', (Join-Path $root 'tools/test/movie-tail-tests.py'), '--runtime', (Join-Path $rec 'ps2xRuntime'), '--compiler', (Join-Path $script:llvmBin 'clang++.exe'), '--output', (Join-Path $logs 'movie-tail')) 'Movie tail clock catch-up'
    Native $python @('-I', (Join-Path $root 'tools/test/logic-rate-tests.py'), '--runtime', $rt, '--compiler', (Join-Path $script:llvmBin 'clang++.exe'), '--output', (Join-Path $logs 'logic-rate')) 'experimental logic-rate timestep and pacing'
    Native (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'tools/test/pipeline-tests.ps1')) 'pipeline configure and process tests'
    Native (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'tools/test/patch-stack-tests.ps1')) 'runtime patch stack rebase tests'
    $testBuild = "$BuildRoot-verify-clang"
    if (Test-ForeignCache $testBuild) { throw "Regression build belongs to another checkout: $testBuild. Choose another -BuildRoot." }
    $testArgs = @('-S', $rec, '-B', $testBuild, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
        '-DPS2X_BUILD_RUNTIME=ON', '-DPS2X_BUILD_RECOMP=ON', '-DPS2X_BUILD_STUDIO=OFF',
        '-DPS2X_BUILD_ANALYZER=OFF', '-DPS2X_BUILD_TEST=OFF', '-DPS2X_RELEASE_LTCG=OFF',
        '-DPS2X_ENABLE_SCCACHE=OFF', '-DPS2X_ENABLE_FFMPEG=OFF', '-DCMAKE_CXX_FLAGS=-fno-strict-aliasing -fwrapv',
        '-DCMAKE_EXE_LINKER_FLAGS=-static', '-DFETCHCONTENT_UPDATES_DISCONNECTED=ON',
        "-DPython3_EXECUTABLE=$(Barra $python)",
        "-DCMAKE_PROJECT_PS2RetroX_INCLUDE=$(Barra (Join-Path $root 'tools/test/guest-calls.cmake'))") + (Clang-CMakeArgs)
    Native $cmakeExe $testArgs 'regression configure'
    Native $cmakeExe @('--build', $testBuild, '--target', 'gow_guest_calls', 'gow_codegen_tests', 'gow_memory_tests', 'gow_frame_metrics', 'gow_vu1_x64_fuzz_test', 'gow_dma_worker_tests', 'gow_sound_regression', 'gow_qte_hold_test', 'gow_qte_input_test', 'gow_vu1_tasks', 'gow_texture_budget', 'gow_shader_program', 'gow_software_reference', 'gow_test_time', 'gow_gs_run_tests', 'gow_shared_present_tests', 'gow_mod_runtime', 'ps2_recomp', '--parallel', "$jobs") 'regression build'
    Write-CompilerCacheStats 'verify'
    Native $python @('-I', (Join-Path $root 'tools/test/recompile-smoke.py'), $testBuild) 'synthetic ELF generation regression'
    Native $python @('-I', (Join-Path $root 'tools/test/launcher-languages.py')) 'launcher language files'
    Native $python @('-I', (Join-Path $root 'tools/test/launcher-env-contract.py')) 'launcher settings contract'
    Native $python @('-I', (Join-Path $root 'tools/test/guest-calls.py'), (Join-Path $testBuild 'gow_guest_calls.exe'),
        (Join-Path $logs 'guest-calls')) 'guest-call regression tests'
    Native (Join-Path (Split-Path $cmakeExe) 'ctest.exe') @('--test-dir', $testBuild, '-R', '^gow_(codegen_tests|memory_tests|frame_metrics|dma_worker_tests|sound_regression|qte_hold_test|qte_input_off|qte_input_shake|qte_input_rotate|qte_input_smoke|texture_budget|shader_program|software_reference|test_time|gs_run_tests|shared_present_tests)$', '--output-on-failure') 'codegen, memory, frame-metric, sound and hold-to-mash regression tests'
    Native $python @('-I', (Join-Path $root 'tools/test/vu1-equivalence.py'),
        (Join-Path $testBuild 'gow_vu1_x64_fuzz_test.exe'), $rt, $python,
        (Join-Path $script:llvmBin 'clang++.exe'), (Join-Path $logs 'vu1-equivalence')) 'VU1 backend equivalence'
    Native $python @('-I', (Join-Path $root 'tools/test/mod-runtime.py'), (Join-Path $testBuild 'gow_mod_runtime.exe')) 'mod VFS and data-patch consumers'
    Native $python @('-I', (Join-Path $root 'tools/test/vu1-task-tests.py'), (Join-Path $testBuild 'gow_vu1_tasks.exe')) 'VU1 isolated task replay'
}
