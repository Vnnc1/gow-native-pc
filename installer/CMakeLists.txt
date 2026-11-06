# Windows release installer for gow-native-pc.
#
# The installer is a single Win32 executable with no third-party dependency:
# it compresses the staged package with the system cabinet.dll and appends it
# to a copy of itself (see the format description at the top of setup.cpp).
#
# The build directory is used directly by tools/pipeline/modules/distribution.ps1:
#
#   cmake -S installer -B <build> -G Ninja -DCMAKE_BUILD_TYPE=Release
#   ninja -C <build>
#   <build>/gow-setup.exe --pack <stage dir> <output exe>
#
# The produced payload is verifiable without installing anything with
# tools/test/verify_setup.py.

cmake_minimum_required(VERSION 3.20)

project(gow-setup LANGUAGES CXX)

if(NOT WIN32)
  message(FATAL_ERROR "gow-setup is a Windows-only program; the installer cannot be built here.")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# The image is copied into itself when packing, so the payload must start at a
# known offset: no section may grow past the end of the file.
add_executable(gow-setup WIN32 setup.cpp)

target_compile_definitions(gow-setup PRIVATE UNICODE _UNICODE)

target_link_libraries(gow-setup PRIVATE user32 shell32 ole32 advapi32)

if(MSVC)
  target_compile_options(gow-setup PRIVATE /utf-8 /W4)
  target_link_options(gow-setup PRIVATE /ALIGN:4096)
else()
  # The sources are UTF-8 (the installer's messages are translated), and the
  # entry point is wmain(), which needs the mingw Unicode start-up code.
  target_compile_options(gow-setup PRIVATE -Wall -Wextra)
  # -static: the installer ships as a single file with no runtime beside it.
  target_link_options(gow-setup PRIVATE -municode -static -Wl,--no-insert-timestamp)
endif()

set_target_properties(gow-setup PROPERTIES
  OUTPUT_NAME "gow-setup"
  RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}"
)
