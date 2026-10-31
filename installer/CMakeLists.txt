# gow-native-pc installer (setup.cpp): plain Win32 + GDI+, no Qt, so the packed setup is one self-contained .exe.
# Built and packed by tools/pipeline/build.ps1 -Stages installer (which runs the package stage first).
cmake_minimum_required(VERSION 3.21)
project(GowNativePcSetup VERSION 3.0.1 LANGUAGES CXX RC)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# The pinned llvm-mingw toolchain produces a self-contained installer.
add_executable(gow-setup WIN32 setup.cpp setup.rc)
target_compile_definitions(gow-setup PRIVATE UNICODE _UNICODE _WIN32_WINNT=0x0A00 WINVER=0x0A00 GOW_VERSION="${PROJECT_VERSION}")
target_compile_options(gow-setup PRIVATE -Wall -Wextra)
target_link_options(gow-setup PRIVATE -static -municode)
target_link_libraries(gow-setup PRIVATE user32 gdi32 gdiplus shell32 ole32 cabinet advapi32)
