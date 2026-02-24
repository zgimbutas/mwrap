set(_mwrap_log_test_driver "${CMAKE_CURRENT_BINARY_DIR}/mwrap_log_test.cmake")
set(_mwrap_log_test_script [[
if(NOT DEFINED MWRAP_EXECUTABLE)
  message(FATAL_ERROR "MWRAP_EXECUTABLE is required")
endif()

foreach(var OUTPUT_FILE REFERENCE_FILE)
  if(NOT DEFINED ${var})
    message(FATAL_ERROR "${var} is required")
  endif()
endforeach()

if(NOT DEFINED TEST_NAME)
  set(TEST_NAME "mwrap_test")
endif()

set(_args)
if(DEFINED ARGC AND ARGC GREATER 0)
  math(EXPR _last_index "${ARGC} - 1")
  foreach(_arg_index RANGE 0 ${_last_index})
    set(_var_name ARG${_arg_index})
    if(NOT DEFINED ${_var_name})
      message(FATAL_ERROR "${TEST_NAME}: missing argument ${_var_name}")
    endif()
    list(APPEND _args "${${_var_name}}")
  endforeach()
endif()

set(_working_directory "${CMAKE_CURRENT_LIST_DIR}")
if(DEFINED WORKING_DIRECTORY)
  set(_working_directory "${WORKING_DIRECTORY}")
endif()

file(MAKE_DIRECTORY "${_working_directory}")

set(stdout_file "${OUTPUT_FILE}.stdout")
execute_process(
  COMMAND ${MWRAP_EXECUTABLE} ${_args}
  RESULT_VARIABLE run_result
  OUTPUT_FILE "${stdout_file}"
  ERROR_FILE "${OUTPUT_FILE}"
  WORKING_DIRECTORY "${_working_directory}"
)

set(expect_nonzero FALSE)
if(DEFINED EXPECT_NONZERO AND EXPECT_NONZERO)
  set(expect_nonzero TRUE)
endif()

if(expect_nonzero AND run_result EQUAL 0)
  message(FATAL_ERROR "${TEST_NAME}: expected failure but command succeeded")
endif()

if(NOT expect_nonzero AND NOT run_result EQUAL 0)
  message(FATAL_ERROR "${TEST_NAME}: command failed with exit code ${run_result}")
endif()

if(NOT EXISTS "${REFERENCE_FILE}")
  message(FATAL_ERROR "${TEST_NAME}: reference file '${REFERENCE_FILE}' not found")
endif()

file(READ "${OUTPUT_FILE}" output_contents)
string(REPLACE "end of file" "$end" normalized_output "${output_contents}")
if(NOT normalized_output STREQUAL output_contents)
  file(WRITE "${OUTPUT_FILE}" "${normalized_output}")
endif()

execute_process(
  COMMAND ${CMAKE_COMMAND} -E compare_files "${OUTPUT_FILE}" "${REFERENCE_FILE}"
  RESULT_VARIABLE diff_result
)

if(NOT diff_result EQUAL 0)
  file(READ "${OUTPUT_FILE}" normalized_output)
  message(FATAL_ERROR "${TEST_NAME}: output does not match reference.\n--- Actual stderr ---\n${normalized_output}")
endif()
]])
file(WRITE "${_mwrap_log_test_driver}" "${_mwrap_log_test_script}")

function(_mwrap_add_log_test name)
  set(options EXPECT_NONZERO)
  set(oneValueArgs REFERENCE)
  set(multiValueArgs ARGS)
  cmake_parse_arguments(_MWRAP_TEST "${options}" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

  if(NOT _MWRAP_TEST_REFERENCE)
    message(FATAL_ERROR "_mwrap_add_log_test requires REFERENCE for test '${name}'")
  endif()

  set(log_file "${CMAKE_CURRENT_BINARY_DIR}/${name}.log")
  list(LENGTH _MWRAP_TEST_ARGS arg_count)
  set(arg_definitions -DARGC=${arg_count})
  if(arg_count GREATER 0)
    math(EXPR arg_max "${arg_count} - 1")
    foreach(arg_index RANGE 0 ${arg_max})
      list(GET _MWRAP_TEST_ARGS ${arg_index} arg_value)
      list(APPEND arg_definitions -DARG${arg_index}=${arg_value})
    endforeach()
  endif()

  add_test(
    NAME ${name}
    COMMAND ${CMAKE_COMMAND}
            -DMWRAP_EXECUTABLE=$<TARGET_FILE:mwrap>
            -DOUTPUT_FILE=${log_file}
            -DREFERENCE_FILE=${_MWRAP_TEST_REFERENCE}
            -DEXPECT_NONZERO=${_MWRAP_TEST_EXPECT_NONZERO}
            -DTEST_NAME=${name}
            -DWORKING_DIRECTORY=${CMAKE_CURRENT_SOURCE_DIR}
            ${arg_definitions}
            -P ${_mwrap_log_test_driver}
  )

  set_tests_properties(${name} PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
endfunction()

_mwrap_add_log_test(
  mwrap.test_syntax
  EXPECT_NONZERO
  REFERENCE ${CMAKE_CURRENT_SOURCE_DIR}/test_syntax.ref
  ARGS -cppcomplex test_syntax.mw
)

_mwrap_add_log_test(
  mwrap.test_typecheck
  EXPECT_NONZERO
  REFERENCE ${CMAKE_CURRENT_SOURCE_DIR}/test_typecheck.ref
  ARGS -cppcomplex test_typecheck.mw
)

if(MWRAP_COMPILE_MEX AND MWRAP_MEX_BACKENDS)
  include(${CMAKE_SOURCE_DIR}/cmake/MwrapAddMex.cmake)

  set(_mwrap_testing_source_dir "${CMAKE_CURRENT_SOURCE_DIR}")
  set(_mwrap_testing_binary_dir "${CMAKE_CURRENT_BINARY_DIR}/octave")
  file(MAKE_DIRECTORY "${_mwrap_testing_binary_dir}")

  configure_file(
    "${_mwrap_testing_source_dir}/test_include2.mw"
    "${_mwrap_testing_binary_dir}/test_include2.mw"
    COPYONLY
  )

  set(_mwrap_testing_generators)

  mwrap_add_mex(test_transfers
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_transfersmex
    CC_FILENAME test_transfersmex.cc
    M_FILENAME test_transfers.m
    MW_FILES "${_mwrap_testing_source_dir}/test_transfers.mw"
  )
  list(APPEND _mwrap_testing_generators test_transfers)

  mwrap_add_mex(test_cpp_complex
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_cpp_complexmex
    CC_FILENAME test_cpp_complexmex.cc
    M_FILENAME test_cpp_complex.m
    MW_FILES "${_mwrap_testing_source_dir}/test_cpp_complex.mw"
    MWRAP_FLAGS -cppcomplex
  )
  list(APPEND _mwrap_testing_generators test_cpp_complex)

  mwrap_add_mex(test_c99_complex
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_c99_complexmex
    CC_FILENAME test_c99_complexmex.c
    M_FILENAME test_c99_complex.m
    MW_FILES "${_mwrap_testing_source_dir}/test_c99_complex.mw"
    MWRAP_FLAGS -c99complex
  )
  list(APPEND _mwrap_testing_generators test_c99_complex)

  mwrap_add_mex(test_catch
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_catchmex
    CC_FILENAME test_catchmex.cc
    M_FILENAME test_catch.m
    MW_FILES "${_mwrap_testing_source_dir}/test_catch.mw"
    MWRAP_FLAGS -catch
  )
  list(APPEND _mwrap_testing_generators test_catch)

  mwrap_add_mex(test_fortran1
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_fortran1mex
    CC_FILENAME test_fortran1mex.cc
    M_FILENAME test_fortran1.m
    MW_FILES "${_mwrap_testing_source_dir}/test_fortran1.mw"
  )
  list(APPEND _mwrap_testing_generators test_fortran1)

  mwrap_add_mex(test_fortran2
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_fortran2mex
    CC_FILENAME test_fortran2mex.c
    M_FILENAME test_fortran2.m
    MW_FILES "${_mwrap_testing_source_dir}/test_fortran2.mw"
  )
  list(APPEND _mwrap_testing_generators test_fortran2)

  mwrap_add_mex(test_include
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_includemex
    CC_FILENAME test_includemex.cc
    M_FILENAME test_include.m
    MW_FILES "${_mwrap_testing_source_dir}/test_include.mw"
  )
  list(APPEND _mwrap_testing_generators test_include)

  mwrap_add_mex(test_single_cpp
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_singlemex
    CC_FILENAME test_singlemex.cc
    MW_FILES "${_mwrap_testing_source_dir}/test_single.mw"
    MWRAP_FLAGS -cppcomplex -mb
  )
  list(APPEND _mwrap_testing_generators test_single_cpp)

  mwrap_add_mex(test_char_cpp
    WORK_DIR "${_mwrap_testing_binary_dir}"
    MEX_NAME test_charmex
    CC_FILENAME test_charmex.cc
    MW_FILES "${_mwrap_testing_source_dir}/test_char.mw"
    MWRAP_FLAGS -cppcomplex -mb
  )
  list(APPEND _mwrap_testing_generators test_char_cpp)

  set(_mwrap_testing_mex_targets)
  foreach(_mwrap_generator IN LISTS _mwrap_testing_generators)
    _mwrap_compile_mex(${_mwrap_generator} OUTPUT_VAR _mwrap_generator_mex_targets)
    if(_mwrap_generator_mex_targets)
      list(APPEND _mwrap_testing_mex_targets ${_mwrap_generator_mex_targets})
    endif()
  endforeach()
  if(_mwrap_testing_mex_targets)
    list(REMOVE_DUPLICATES _mwrap_testing_mex_targets)
  endif()

  set(_mwrap_redirect_output "${_mwrap_testing_binary_dir}/test_redirect.m")
  add_custom_command(
    OUTPUT "${_mwrap_redirect_output}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${_mwrap_testing_binary_dir}"
    COMMAND $<TARGET_FILE:mwrap> -mb "${_mwrap_testing_source_dir}/test_redirect.mw"
    DEPENDS mwrap "${_mwrap_testing_source_dir}/test_redirect.mw"
    WORKING_DIRECTORY "${_mwrap_testing_binary_dir}"
    COMMENT "Generating test_redirect.m with mwrap"
    VERBATIM
  )
  add_custom_target(mwrap_testing_redirect DEPENDS "${_mwrap_redirect_output}")
  set_property(TARGET mwrap_testing_redirect PROPERTY FOLDER "tests")

  set(_mwrap_testing_artifacts ${_mwrap_testing_mex_targets} mwrap_testing_redirect)
  list(REMOVE_DUPLICATES _mwrap_testing_artifacts)

  if(_mwrap_testing_artifacts)
    add_custom_target(mwrap_testing_mex DEPENDS ${_mwrap_testing_artifacts})
    set_property(TARGET mwrap_testing_mex PROPERTY FOLDER "tests")
  endif()

  if("OCTAVE" IN_LIST MWRAP_MEX_BACKENDS)
    if(MWRAP_OCTAVE_EXECUTABLE)
      string(REPLACE "'" "''" _mwrap_octave_binary_dir_escaped "${_mwrap_testing_binary_dir}")
      string(REPLACE "'" "''" _mwrap_octave_source_dir_escaped "${_mwrap_testing_source_dir}")
      set(_mwrap_octave_eval
        "addpath('${_mwrap_octave_binary_dir_escaped}'); addpath('${_mwrap_octave_source_dir_escaped}'); test_all; exit;")
      add_test(NAME mwrap.octave.test_all
        COMMAND ${MWRAP_OCTAVE_EXECUTABLE}
                --quiet --no-init-file
                --eval "${_mwrap_octave_eval}")
      set_tests_properties(mwrap.octave.test_all PROPERTIES
        WORKING_DIRECTORY "${_mwrap_testing_binary_dir}")
    else()
      message(WARNING
        "Octave backend enabled but no Octave interpreter was found; skipping Octave runtime tests.")
    endif()
  endif()
endif()

if(CMAKE_CONFIGURATION_TYPES)
  add_custom_target(mwrap_tests
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure -C $<CONFIG>
    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
  )
else()
  add_custom_target(mwrap_tests
    COMMAND ${CMAKE_CTEST_COMMAND} --output-on-failure
    WORKING_DIRECTORY ${PROJECT_BINARY_DIR}
  )
endif()

add_dependencies(mwrap_tests mwrap)
if(TARGET mwrap_testing_mex)
  add_dependencies(mwrap_tests mwrap_testing_mex)
endif()
set_property(TARGET mwrap_tests PROPERTY FOLDER "tests")
