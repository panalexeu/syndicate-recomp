# syndicate - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(syndicate LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Use the pinned, patched SDK checkout unless REXSDK_DIR is given (see tools/apply_patches.sh).
set(REXSDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/rexglue-sdk" CACHE PATH "Path to rexglue-sdk source tree")

include(generated/rexglue.cmake)

# Sources
set(SYNDICATE_SOURCES
    src/main.cpp
)

if(WIN32)
    add_executable(syndicate WIN32 ${SYNDICATE_SOURCES})
else()
    add_executable(syndicate ${SYNDICATE_SOURCES})
endif()

rexglue_setup_target(syndicate)

# The SDK puts its shared libraries in ${REXSDK_DIR}/out/<platform>; the executable looks
# for them next to itself ($ORIGIN). Link them into the build folder.
if(UNIX AND NOT APPLE AND REXSDK_DIR)
    foreach(lib rexruntime rexgpu-xenos TracyClient)
        add_custom_command(TARGET syndicate POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E create_symlink
                    ${REXSDK_DIR}/out/linux-amd64/lib${lib}.so
                    $<TARGET_FILE_DIR:syndicate>/lib${lib}.so)
    endforeach()
endif()

# Copy the runtime configuration next to the executable (the runtime reads <exe dir>/syndicate.toml).
add_custom_command(TARGET syndicate POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/config/syndicate.toml
            $<TARGET_FILE_DIR:syndicate>/syndicate.toml
    COMMENT "Copying config/syndicate.toml next to the executable")
