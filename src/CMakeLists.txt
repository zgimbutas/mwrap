set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(stringify stringify.c)

set(MWRAP_SUPPORT_HEADER ${CMAKE_CURRENT_BINARY_DIR}/mwrap-support.h)
add_custom_command(
  OUTPUT ${MWRAP_SUPPORT_HEADER}
  COMMAND ${CMAKE_COMMAND}
          -DSTRINGIFY=$<TARGET_FILE:stringify>
          -DINPUT=${CMAKE_CURRENT_SOURCE_DIR}/mwrap-support.c
          -DOUTPUT=${MWRAP_SUPPORT_HEADER}
          -DNAME=mex_header
          -P ${PROJECT_SOURCE_DIR}/cmake/run_stringify.cmake
  DEPENDS stringify ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-support.c
  COMMENT "Generating mwrap-support.h"
  VERBATIM
)
set_source_files_properties(${MWRAP_SUPPORT_HEADER} PROPERTIES GENERATED TRUE)
add_custom_target(mwrap_support_header DEPENDS ${MWRAP_SUPPORT_HEADER})

set(MWRAP_HANDWRITTEN_SOURCES
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-ast.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-typecheck.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-cgen.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-mgen.cc
)
set(MWRAP_HANDWRITTEN_HEADERS
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-ast.h
)

find_package(BISON REQUIRED)
find_package(FLEX REQUIRED)

if(BISON_VERSION VERSION_GREATER_EQUAL "3.0")
  set(ERROR_VERBOSE "%define parse.error verbose")
else()
  set(ERROR_VERBOSE "%error-verbose")
endif()

configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap.y.in
  ${CMAKE_CURRENT_BINARY_DIR}/mwrap.y
  @ONLY
)

BISON_TARGET(MwrapParser
  ${CMAKE_CURRENT_BINARY_DIR}/mwrap.y
  ${CMAKE_CURRENT_BINARY_DIR}/mwrap.cc
  DEFINES_FILE ${CMAKE_CURRENT_BINARY_DIR}/mwrap.hh
  VERBOSE ${CMAKE_CURRENT_BINARY_DIR}/mwrap.output
)

FLEX_TARGET(MwrapLexer
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap.l
  ${CMAKE_CURRENT_BINARY_DIR}/lex.yy.c
)

ADD_FLEX_BISON_DEPENDENCY(MwrapLexer MwrapParser)

set(MWRAP_GENERATED_SOURCES
  ${BISON_MwrapParser_OUTPUT_SOURCE}
  ${FLEX_MwrapLexer_OUTPUTS}
)
set(MWRAP_GENERATED_HEADERS
  ${BISON_MwrapParser_OUTPUT_HEADER}
)
set_source_files_properties(${MWRAP_GENERATED_SOURCES} ${MWRAP_GENERATED_HEADERS} PROPERTIES GENERATED TRUE)

add_executable(mwrap
  ${MWRAP_HANDWRITTEN_SOURCES}
  ${MWRAP_GENERATED_SOURCES}
  ${MWRAP_SUPPORT_HEADER}
)
add_dependencies(mwrap mwrap_support_header)

target_sources(mwrap PRIVATE ${MWRAP_HANDWRITTEN_HEADERS} ${MWRAP_GENERATED_HEADERS})

target_include_directories(mwrap PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}
  ${CMAKE_CURRENT_BINARY_DIR}
)

install(TARGETS mwrap RUNTIME DESTINATION bin)
