# God of War Native PC launcher (Qt 6 Quick): installs (runtime, discs, build) and plays. Based on the Tobiichi
# Launcher by YYOzcan (GPL-3.0); see CREDITS.md.
# Build with matching Qt and Clang: build.cmd -Stages launcher
cmake_minimum_required(VERSION 3.21)
# The release version (tag v<this>, CHANGELOG.md). The updater compares it with the latest release's tag, so the two
# must match. 0.x until the port is complete; releases up to 3.0.1 were renumbered 0.1.0-0.3.1.
project(GowNativePcLauncher VERSION 0.5.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2)
qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(gow-launcher WIN32
    src/main.cpp
    src/lanzador.cpp
    src/lanzador.h
    src/session_diagnostics.cpp
    src/session_diagnostics.h
    src/installer_backend.cpp
    src/installer_backend.h
    src/mando.cpp
    src/mando.h
)
if(WIN32)
    target_sources(gow-launcher PRIVATE gow-launcher.rc)
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    find_package(SDL2 REQUIRED CONFIG)
    target_link_libraries(gow-launcher PRIVATE SDL2::SDL2)
endif()

set(ARCHIVOS_QML
    qml/Main.qml
    qml/Tema.qml
    qml/Textos.js
    qml/idiomas/fr.js
    qml/idiomas/de.js
    qml/idiomas/it.js
    qml/idiomas/ru.js
    qml/idiomas/zh.js
    qml/Ascuas.qml
    qml/NavItem.qml
    qml/Fila.qml
    qml/Selector.qml
    qml/Interruptor.qml
    qml/Deslizador.qml
    qml/BotonJugar.qml
    qml/BotonSecundario.qml
    qml/CampoRuta.qml
    qml/Tecla.qml
    qml/TeclaAsignable.qml
    qml/Teclas.js
    qml/PaginaGrafico.qml
    qml/PaginaRendimiento.qml
    qml/InstallPage.qml
    qml/LoadingScreen.qml
    qml/AccessibilityPage.qml
    qml/PaginaControles.qml
    qml/PaginaPartidas.qml
    qml/PaginaTrucos.qml
    qml/PaginaOtros.qml
)
# The QML files sit at the module root (no "qml/"), so their folder's implicit import is the module itself and
# Tema (the theme) loads as a singleton.
foreach(archivo IN LISTS ARCHIVOS_QML)
    string(REGEX REPLACE "^qml/" "" nombre "${archivo}") # path under qml/: idiomas/fr.js keeps its folder
    set_source_files_properties(${archivo} PROPERTIES QT_RESOURCE_ALIAS ${nombre})
endforeach()
set_source_files_properties(qml/Tema.qml PROPERTIES QT_QML_SINGLETON_TYPE TRUE)

qt_add_qml_module(gow-launcher
    URI Tobiichi
    VERSION 1.0
    RESOURCE_PREFIX /qt/qml
    QML_FILES ${ARCHIVOS_QML}
)

target_compile_definitions(gow-launcher PRIVATE TOBIICHI_VERSION="${PROJECT_VERSION}")
target_link_libraries(gow-launcher PRIVATE Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2)

qt_add_executable(gow-session WIN32 src/session_main.cpp src/session_diagnostics.cpp src/session_diagnostics.h)
target_link_libraries(gow-session PRIVATE Qt6::Core)
target_compile_definitions(gow-session PRIVATE TOBIICHI_VERSION="${PROJECT_VERSION}")
if(WIN32)
    target_link_libraries(gow-session PRIVATE psapi)
    target_link_libraries(gow-launcher PRIVATE psapi)
endif()

install(TARGETS gow-launcher gow-session RUNTIME DESTINATION bin)

if(WIN32)
    qt_add_executable(gow-diagnostics WIN32 diagnostics/main.cpp diagnostics/diagnostic_kit.cpp
        diagnostics/diagnostic_kit.h src/session_diagnostics.cpp src/session_diagnostics.h)
    target_include_directories(gow-diagnostics PRIVATE src)
    target_compile_definitions(gow-diagnostics PRIVATE TOBIICHI_VERSION="${PROJECT_VERSION}-diagnostics")
    target_link_libraries(gow-diagnostics PRIVATE Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick Qt6::QuickControls2 psapi comdlg32)
    qt_add_resources(gow-diagnostics diagnostic_ui PREFIX "/" FILES diagnostics/Main.qml qml/Textos.js
        qml/idiomas/fr.js qml/idiomas/de.js qml/idiomas/it.js qml/idiomas/ru.js qml/idiomas/zh.js)
endif()

# Explicit regression target; never included in the player package.
add_executable(gow_region_tests EXCLUDE_FROM_ALL ../tools/test/regional_launcher_test.cpp)
target_include_directories(gow_region_tests PRIVATE src)
target_link_libraries(gow_region_tests PRIVATE Qt6::Core)
