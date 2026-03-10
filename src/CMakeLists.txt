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

set(MWRAP_OCT_SUPPORT_HEADER ${CMAKE_CURRENT_BINARY_DIR}/mwrap-oct-support.h)
add_custom_command(
  OUTPUT ${MWRAP_OCT_SUPPORT_HEADER}
  COMMAND ${CMAKE_COMMAND}
          -DSTRINGIFY=$<TARGET_FILE:stringify>
          -DINPUT=${CMAKE_CURRENT_SOURCE_DIR}/mwrap-oct-support.c
          -DOUTPUT=${MWRAP_OCT_SUPPORT_HEADER}
          -DNAME=oct_header
          -P ${PROJECT_SOURCE_DIR}/cmake/run_stringify.cmake
  DEPENDS stringify ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-oct-support.c
  COMMENT "Generating mwrap-oct-support.h"
  VERBATIM
)
set_source_files_properties(${MWRAP_OCT_SUPPORT_HEADER} PROPERTIES GENERATED TRUE)
add_custom_target(mwrap_oct_support_header DEPENDS ${MWRAP_OCT_SUPPORT_HEADER})

set(MWRAP_CPP_SUPPORT_HEADER ${CMAKE_CURRENT_BINARY_DIR}/mwrap-cpp-support.h)
add_custom_command(
  OUTPUT ${MWRAP_CPP_SUPPORT_HEADER}
  COMMAND ${CMAKE_COMMAND}
          -DSTRINGIFY=$<TARGET_FILE:stringify>
          -DINPUT=${CMAKE_CURRENT_SOURCE_DIR}/mwrap-cpp-support.c
          -DOUTPUT=${MWRAP_CPP_SUPPORT_HEADER}
          -DNAME=cpp_header
          -P ${PROJECT_SOURCE_DIR}/cmake/run_stringify.cmake
  DEPENDS stringify ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-cpp-support.c
  COMMENT "Generating mwrap-cpp-support.h"
  VERBATIM
)
set_source_files_properties(${MWRAP_CPP_SUPPORT_HEADER} PROPERTIES GENERATED TRUE)
add_custom_target(mwrap_cpp_support_header DEPENDS ${MWRAP_CPP_SUPPORT_HEADER})

set(MWRAP_FMEX_SUPPORT_HEADER ${CMAKE_CURRENT_BINARY_DIR}/mwrap-fmex-support.h)
add_custom_command(
  OUTPUT ${MWRAP_FMEX_SUPPORT_HEADER}
  COMMAND ${CMAKE_COMMAND}
          -DSTRINGIFY=$<TARGET_FILE:stringify>
          -DINPUT=${CMAKE_CURRENT_SOURCE_DIR}/mwrap-fmex-support.f90
          -DOUTPUT=${MWRAP_FMEX_SUPPORT_HEADER}
          -DNAME=fmex_header
          -P ${PROJECT_SOURCE_DIR}/cmake/run_stringify.cmake
  DEPENDS stringify ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-fmex-support.f90
  COMMENT "Generating mwrap-fmex-support.h"
  VERBATIM
)
set_source_files_properties(${MWRAP_FMEX_SUPPORT_HEADER} PROPERTIES GENERATED TRUE)
add_custom_target(mwrap_fmex_support_header DEPENDS ${MWRAP_FMEX_SUPPORT_HEADER})

set(MWRAP_HANDWRITTEN_SOURCES
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-ast.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-typecheck.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-cgen.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-mgen.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-octgen.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-cppgen.cc
  ${CMAKE_CURRENT_SOURCE_DIR}/mwrap-fmexgen.cc
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
  ${MWRAP_OCT_SUPPORT_HEADER}
  ${MWRAP_CPP_SUPPORT_HEADER}
  ${MWRAP_FMEX_SUPPORT_HEADER}
)
add_dependencies(mwrap mwrap_support_header mwrap_oct_support_header mwrap_cpp_support_header mwrap_fmex_support_header)

target_sources(mwrap PRIVATE ${MWRAP_HANDWRITTEN_HEADERS} ${MWRAP_GENERATED_HEADERS})

target_include_directories(mwrap PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}
  ${CMAKE_CURRENT_BINARY_DIR}
)

target_compile_definitions(mwrap PRIVATE
  $<$<BOOL:${MWRAP_ENABLE_MATLAB_CLASSDEF}>:R2008OO>
  $<$<BOOL:${MWRAP_ENABLE_C99_COMPLEX}>:MWRAP_ENABLE_C99_COMPLEX>
  $<$<BOOL:${MWRAP_ENABLE_CPP_COMPLEX}>:MWRAP_ENABLE_CPP_COMPLEX>
)

install(TARGETS mwrap RUNTIME DESTINATION bin)
