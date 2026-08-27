cmake_minimum_required(VERSION 3.16)
project(CenterlineExtractor LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Dependencies
find_package(DGtal REQUIRED)

# Executable target
add_executable(extractor 
    src/main.cpp
)

# Link Libraries
target_link_libraries(extractor PRIVATE 
    DGtal::DGtal
)
