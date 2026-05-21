MWrap
=====

MWrap is an interface generation system in the spirit of SWIG or matwrap.
**It makes wrapping C/C++/Fortran/CUDA from MATLAB almost pleasant!**
From a set of augmented MATLAB script files, it generates a MEX gateway to the desired C/C++/Fortran/CUDA function calls, and also generates MATLAB function files to access that gateway. It hides the details of converting to and from MATLAB's data structures, and of allocating and freeing temporary storage.
It is compatible with modern GNU Octave via `mkoctfile --mex`.
It also includes `gpuArray` support (for MATLAB/CUDA only).

MWrap was originally created by David Bindel in 2009.
Some simple (including OpenMP) demos are to be found at
[MWrapDemo](https://github.com/ahbarnett/mwrapdemo).
MWrap is now used in many projects including
[FINUFFT](https://finufft.readthedocs.io),
[FMM2D](https://fmm2d.readthedocs.io),
[FMM3D](https://fmm3d.readthedocs.io), and
[FMM3DBIE](https://fmm3dbie.readthedocs.io).

Users may also be interested in the new MATLAB package manager [mip](https://mip.sh/) which includes MEX interface generation.


Dependencies
------------

Building MWrap needs the following tools:

* A C compiler with C99 support and a C++ compiler with C++11 support
* [Bison](https://www.gnu.org/software/bison/) and [Flex](https://github.com/westes/flex)
* (Optional) [CMake](https://cmake.org/) 3.16 or newer (for the CMake build path)
* (Optional) [MATLAB](https://www.mathworks.com/products/matlab.html) with MEX build tooling when compiling wrappers with CMake
* (Optional) MATLAB Parallel Computing Toolbox, and CUDA Toolkit, if you want to wrap `gpuArray` objects.

If you are using a Debian or Ubuntu based system, the required packages can be
installed via

```
sudo apt-get install build-essential bison flex cmake
```

Makefile build
--------------

Edit `make.inc` (this decides whether `MEX` uses MATLAB vs Octave build),
and then run `make`.  The output will be a
standalone executable (`mwrap`) in the main directory.  Bison and Flex are
required for this build path. Then to make the examples use `make demo`,
then cd to subdirectories of `example/` and try each out using MATLAB or Octave as appropriate.


CMake build
-----------

Alternatively, create a build directory and run CMake:

```
mkdir -p build
cd build
cmake ..
cmake --build .
```

Cache options mirror the `make.inc` file.  For example, to enable
MATLAB `classdef` support and the C99 complex helpers:

```
cmake -DMWRAP_ENABLE_MATLAB_CLASSDEF=ON -DMWRAP_ENABLE_C99_COMPLEX=ON ..
```

### Building the MATLAB/Octave examples

The example wrappers under `example/` can be generated through CMake by turning
on the `MWRAP_BUILD_EXAMPLES` option.  This configuration runs `mwrap` to
produce the C++ gateway sources (and any requested MATLAB scaffolding).
By default the build stops after source generation, mirroring the legacy
Makefiles.  The resulting files live under the build tree in per-example
subdirectories.

```
cmake -DMWRAP_BUILD_EXAMPLES=ON ..
cmake --build . --target mwrap_examples
```

To have CMake invoke MATLAB's compiler and produce loadable MEX binaries, add
`-DMWRAP_COMPILE_MEX=ON` when configuring.  CMake will build the generated
sources into MEX targets, attach them to the `mwrap_examples` aggregate target,
and skip executing the binaries during the build.

When running the MATLAB smoke tests locally (for example, `ctest -R matlab-`),
build the `mwrap_examples` target beforehand so that the generated wrappers and
MEX binaries are available to the test runner.

The `MWRAP_MEX_BACKEND` cache entry selects which toolchain to use.  MATLAB
backends require CMake's `FindMatlab` module to locate MATLAB's development
components, while Octave backends require the `mkoctfile` executable to be
available.  Choosing `ALL` emits binaries for both environments (and therefore
requires both toolchains).

```
cmake -DMWRAP_BUILD_EXAMPLES=ON -DMWRAP_COMPILE_MEX=ON -DMWRAP_MEX_BACKEND=MATLAB ..
cmake -DMWRAP_BUILD_EXAMPLES=ON -DMWRAP_COMPILE_MEX=ON -DMWRAP_MEX_BACKEND=OCTAVE ..
cmake -DMWRAP_BUILD_EXAMPLES=ON -DMWRAP_COMPILE_MEX=ON -DMWRAP_MEX_BACKEND=ALL ..
```

If you leave `MWRAP_COMPILE_MEX` disabled, you can still invoke MATLAB or
Octave's `mex` tool manually using the produced `.cc` file and any support
sources that your project requires.  Optional flags such as
`MWRAP_ENABLE_MATLAB_CLASSDEF` remain available while configuring the
examples.


Example usage
-------------

David Bindel's user's guide (`mwrap.pdf`) describes MWrap in detail; you can also look at the example subdirectories and the testing subdirectory to get some idea of how MWrap is used.

Alex Barnett also maintains a set of minimally complete tutorial examples of calling C/Fortran libraries (including OpenMP) from MATLAB/Octave, using MWrap, at https://github.com/ahbarnett/mwrapdemo

The `mwrap.1` man page was written by Nicolas Bourdaud.
It should be manually placed in `/usr/local/share/man/man1/`, for instance.


Contributors and version history
--------------------------------

MWrap was originally written by David Bindel, c. 2009.
He hosts his old version at https://www.cs.cornell.edu/~bindel/sw/mwrap
This is unsupported; we recommend that you use the current version.
It was moved to github in around 2015 in order to add new features, and is now maintained by Zydrunas Gimbutas, Alex Barnett, Libin Lu, Manas Rachh, Rafael Laboissière, and Marco Barbone.

**Version 0.33** (c. 2009)
Author: David Bindel <bindel@cs.cornell.edu>
- Initial revision, clone David's repository (c. 2015)

**Version 1.0** (c. 2020)
Contributors: Zydrunas Gimbutas, Alex Barnett, Libin Lu.
- Add support for 64-bit Matlab and gcc-4.6
- Add support for gcc 7.3+
- Add support for Matlab R2018a complex interleaved API
- Add support for C99 int32_t, int64_t, uint32_t, uint64_t
- Allow single precision Matlab inputs and outputs

**Version 1.1** (2022)
Contributors: Manas Rachh, Zydrunas Gimbutas.
- Add support for gfortran -fno-underscoring flag

**Version 1.2** (2025)
Contributors: Libin Lu, Rafael Laboissière, Zydrunas Gimbutas.
- Cope with error verbose directive in both versions 2 and 3 of Bison
- Add support for Matlab gpuArray
- Add support for char scalar

**Version 1.3** (2026)
Contributors: Marco Barbone, Zydrunas Gimbutas.
- Add CMake build system and GitHub Actions CI
- Validate input files before processing to prevent data loss
- Optimize MEX dispatch with integer ID + function pointer table
- Add `#include <stdint.h>` for int64_t/uint64_t on Windows msys2/mingw64
- Add Python mwrap implementation

Also see https://github.com/zgimbutas/mwrap/tags
