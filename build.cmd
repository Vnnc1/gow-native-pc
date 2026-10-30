@echo off
rem God of War Native PC: the build pipeline from a terminal (the launcher's Install tab runs the same script).
rem   build.cmd -Discs "D:\God of War (USA).iso"                 everything: runtime, discs, recompile, build
rem   build.cmd -Discs "D:\usa.iso|D:\ptbr.iso"                  several ISOs: one language each
rem   build.cmd -Stages sync,build                               only the changed C++ (after editing the runtime)
rem   build.cmd -Stages optimize                                 record + compile VU1/IOP native code
rem   build.cmd -Stages native                                   compile the VU1 code recorded while playing
rem   build.cmd -Stages configure,recomp,sync,build               build with the pinned Clang toolchain
rem   build.cmd -Stages pgo                                      clang: profile-guided rebuild (the game plays itself)
rem   build.cmd -Stages launcher                                 build matching Qt once, then the launcher + root shortcut
rem   build.cmd -Stages installer                                the release setup: data\_package\gow-native-pc-setup.exe
rem Full list: tools\pipeline\build.ps1
setlocal
rem Avoid inheriting PowerShell 7 modules into Windows PowerShell 5.1.
set "PSModulePath=%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules;%ProgramFiles%\WindowsPowerShell\Modules"
set "STAGES=fetch,discs,configure,recomp,sync,build"
echo %* | findstr /i /c:"-Stages" >nul && set "STAGES="
if defined STAGES (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\pipeline\build.ps1" -Stages %STAGES% %*
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\pipeline\build.ps1" %*
)
set "GOW_BUILD_RC=%ERRORLEVEL%"
if not "%GOW_BUILD_RC%"=="0" (echo. & echo BUILD FAILED) else (echo. & echo BUILD OK)
endlocal & exit /b %GOW_BUILD_RC%
