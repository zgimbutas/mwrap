# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MWrap is a MEX interface generator that creates C/C++/Fortran MEX gateway code for MATLAB and Octave from annotated `.mw` interface files. It has two implementations: a C++ version (using Flex/Bison) in `src/` and a pure Python port in `python/`.

## Build Commands

### CMake (primary)
```bash
cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build --target mwrap
cmake --build build --target mwrap_tests    # runs ctest
```

Key CMake options: `-DMWRAP_ENABLE_MATLAB_CLASSDEF=ON` (classdef), `-DMWRAP_ENABLE_C99_COMPLEX=ON`, `-DMWRAP_ENABLE_CPP_COMPLEX=ON`, `-DMWRAP_BUILD_EXAMPLES=ON`, `-DMWRAP_COMPILE_MEX=ON`, `-DMWRAP_MEX_BACKEND=OCTAVE|MATLAB|ALL`.

### Makefile (legacy)
```bash
make bin          # build C++ mwrap executable
make test         # run tests (requires Octave)
```
Edit `make.inc` to configure compilers and flags (MEX backend, OOFLAG, etc.).

### Python version
No build step. Run directly: `python/mwrap -mex name -c out.c -m out.m input.mw`

## Test Infrastructure

- **CMake tests**: `mwrap.test_syntax` and `mwrap.test_typecheck` compare stderr against `.ref` reference files in `testing/`
- **MEX functional tests** (require MATLAB or Octave): `testing/test_all.m` runs test_transfers, test_cpp_complex, test_c99_complex, test_catch, test_fortran1/2, test_include, test_single, test_char
- **MATLAB**: `addpath('testing'); run_matlab_tests('build-matlab', '.')`
- **Octave via CMake**: `ctest --test-dir build-octave --output-on-failure -R '^octave-'`

## Architecture

The processing pipeline for both C++ and Python versions is: **Lexer → Parser → Type Checker → Code Generator**.

### C++ implementation (`src/`)
- `mwrap.l` — Flex lexer
- `mwrap.y.in` — Bison grammar (configured for Bison 2.x or 3.x via CMake)
- `mwrap-ast.cc/h` — AST node types (`Expr`, `TypeQual`, `Var`, `Func`)
- `mwrap-typecheck.cc` — type validation
- `mwrap-cgen.cc` — MEX C code generation (the largest/most complex file)
- `mwrap-mgen.cc` — MATLAB `.m` stub generation
- `mwrap-cppgen.cc` — MATLAB C++ MEX API (R2018a+) code generation
- `mwrap-octgen.cc` — Octave oct-file (DEFUN_DLD) code generation
- `mwrap-support.c` — runtime support library embedded into generated C MEX files (stringified into `mwrap-support.h` at build time via `stringify.c`)
- `mwrap-cpp-support.c` — runtime support library for C++ MEX API backend
- `mwrap-oct-support.c` — runtime support library for Octave oct-file backend

### Python implementation (`python/`)
- `mwrap` — entry point
- `mwrap_lexer.py`, `mwrap_parser.py`, `mwrap_ast.py`, `mwrap_typecheck.py` — mirror the C++ pipeline
- `mwrap_cgen.py` — MEX C code generator (parallel to `mwrap-cgen.cc`)
- `mwrap_mgen.py` — MATLAB stub generator
- `mwrap_cppgen.py` — MATLAB C++ MEX API code generator (parallel to `mwrap-cppgen.cc`)
- `mwrap_octgen.py` — Octave oct-file code generator (parallel to `mwrap-octgen.cc`)
- `mwrap_support.c` — runtime support file for C MEX backend
- `mwrap_cpp_support.h` — runtime support for C++ MEX API backend
- `mwrap_oct_support.h` — runtime support for Octave oct-file backend

### Key data structures
- **`VT` enum** (in `mwrap_ast.py` / implicit in C++) — classifies variable types: scalar, array, complex, object, pointer, reference, string, mxArray, GPU variants. The `Var` node also carries a `nocopy` field for zero-copy array passing.
- **`TYPE_PROPS`** (in `mwrap_cgen.py` / `mwrap-cgen.cc`) — maps types to mxClassID, accessor functions, precision info
- **`MwrapContext`** — holds parsed interface state: function list, typedefs, includes

### Generated code structure
There are four code generation backends:
- **C MEX** (`-mex` + `-c`) — traditional `mexFunction` gateway, compiled with `mex` or `mkoctfile --mex`
- **C++ MEX** (`-cppmex`) — MATLAB C++ MEX API (R2018a+) using `MexFunction::operator()`
- **Octave oct-file** (`-oct`) — native Octave `DEFUN_DLD` gateway, compiled with `mkoctfile`
- **MATLAB stubs** (`-m` / `-mb`) — `.m` files that call the compiled gateway

Each backend uses an integer dispatch table: each wrapped function gets an ID, and the entry point dispatches via switch. Input validation, data conversion, memory management, and complex type handling are all generated per-function.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs four jobs: Makefile build, CMake build, MATLAB examples, and Octave examples — all on Ubuntu.
