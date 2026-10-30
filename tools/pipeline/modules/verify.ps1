# Regression gate independent of copyrighted game data.
if ($Stages -contains 'verify') {
    Step 'verify runtime and code generation'
    Use-Clang
    Native $python @('-I', (Join-Path $root 'tools/test/pipeline_tests.py')) 'pipeline regression tests'
    Native $python @('-I', (Join-Path $root 'tools/test/worker-ab-tests.py')) 'worker comparison methodology tests'
    Native (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe') @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        (Join-Path $root 'tools/test/pipeline-tests.ps1')) 'pipeline configure and process tests'
    $testBuild = "$BuildRoot-verify-clang"
    if (Test-ForeignCache $testBuild) { throw "Regression build belongs to another checkout: $testBuild. Choose another -BuildRoot." }
    $testArgs = @('-S', $rec, '-B', $testBuild, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
        '-DPS2X_BUILD_RUNTIME=ON', '-DPS2X_BUILD_RECOMP=ON', '-DPS2X_BUILD_STUDIO=OFF',
        '-DPS2X_BUILD_ANALYZER=OFF', '-DPS2X_BUILD_TEST=OFF', '-DPS2X_RELEASE_LTCG=OFF',
        '-DPS2X_ENABLE_SCCACHE=OFF', '-DCMAKE_CXX_FLAGS=-fno-strict-aliasing -fwrapv',
        '-DCMAKE_EXE_LINKER_FLAGS=-static', '-DFETCHCONTENT_UPDATES_DISCONNECTED=ON',
        "-DPython3_EXECUTABLE=$(Barra $python)",
        "-DCMAKE_PROJECT_PS2RetroX_INCLUDE=$(Barra (Join-Path $root 'tools/test/guest-calls.cmake'))") + (Clang-CMakeArgs)
    Native $cmakeExe $testArgs 'regression configure'
    Native $cmakeExe @('--build', $testBuild, '--target', 'gow_guest_calls', 'gow_codegen_tests', 'gow_memory_tests', 'gow_frame_metrics', 'gow_vu1_x64_fuzz_test', 'gow_dma_worker_tests', 'gow_vu1_tasks', 'ps2_recomp', '--parallel', "$jobs") 'regression build'
    Write-CompilerCacheStats 'verify'
    Native $python @('-I', (Join-Path $root 'tools/test/recompile-smoke.py'), $testBuild) 'synthetic ELF generation regression'
    Native $python @('-I', (Join-Path $root 'tools/test/guest-calls.py'), (Join-Path $testBuild 'gow_guest_calls.exe'),
        (Join-Path $logs 'guest-calls')) 'guest-call regression tests'
    Native (Join-Path (Split-Path $cmakeExe) 'ctest.exe') @('--test-dir', $testBuild, '-R', '^gow_(codegen_tests|memory_tests|frame_metrics|dma_worker_tests)$', '--output-on-failure') 'codegen, memory and frame-metric regression tests'
    Native $python @('-I', (Join-Path $root 'tools/test/vu1-equivalence.py'),
        (Join-Path $testBuild 'gow_vu1_x64_fuzz_test.exe'), $rt, $python,
        (Join-Path $script:llvmBin 'clang++.exe'), (Join-Path $logs 'vu1-equivalence')) 'VU1 backend equivalence'
    Native $python @('-I', (Join-Path $root 'tools/test/vu1-task-tests.py'), (Join-Path $testBuild 'gow_vu1_tasks.exe')) 'VU1 isolated task replay'
}
