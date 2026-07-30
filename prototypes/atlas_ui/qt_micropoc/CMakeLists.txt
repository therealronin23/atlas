cmake_minimum_required(VERSION 3.21)
project(qt_micropoc VERSION 1.0 LANGUAGES CXX)

set(CMAKE_AUTOMOC ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_INCLUDE_CURRENT_DIR ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Qml Quick ShaderTools WebSockets)

qt_add_executable(qt_micropoc
    main.cpp
)

qt_add_qml_module(qt_micropoc
    URI QtMicropoc
    VERSION 1.0
    QML_FILES
        Main.qml
)

qt_add_shaders(qt_micropoc "shaders"
    PREFIX "/shaders"
    FILES
        shaders/glow.frag
)

target_link_libraries(qt_micropoc PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
    Qt6::WebSockets
)
