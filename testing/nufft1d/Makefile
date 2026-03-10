#
# Makefile for nufft1d Fortran MEX test
#
# Targets:
#   make             — generate gateway + stubs, compile, and run test
#   make generate    — generate .f90 gateway and .m stubs only
#   make compile     — compile MEX file (requires generate first)
#   make test        — run Octave test
#   make clean       — remove generated files
#
# Requirements:
#   - python3 (for mwrap)
#   - mkoctfile (for compilation with Octave)
#   - octave (for testing)
#
# For MATLAB, replace the compile target with:
#   mex nufft1dmex.f90 dirft1d.f nufft1df90.f next235.f dfft.f
#

MWRAP = ../../python/mwrap

# Fortran source files for nufft1d
FORT_SRC = dirft1d.f nufft1df90.f next235.f dfft.f

# Default: generate, compile, and test
all: test

# Generate the Fortran MEX gateway and MATLAB stubs
generate: nufft1dmex.f90

nufft1dmex.f90: nufft1d.mw $(MWRAP)
	python3 $(MWRAP) -cppcomplex -fmex nufft1dmex -c nufft1dmex.f90 -mb nufft1d.mw

# Compile with Octave mkoctfile
compile: nufft1dmex.mex

nufft1dmex.mex: nufft1dmex.f90 $(FORT_SRC)
	mkoctfile --mex nufft1dmex.f90 $(FORT_SRC)

# Run Octave test
test: nufft1dmex.mex
	octave --eval " \
	  nj = 100; \
	  xj = -pi + 2*pi*rand(nj,1); \
	  cj = randn(nj,1) + 1i*randn(nj,1); \
	  iflag = 1; ms = 50; eps0 = 1e-12; \
	  fk1 = dirft1d1(nj, xj, cj, iflag, ms); \
	  [fk2,ier] = nufft1d1(nj, xj, cj, iflag, eps0, ms); \
	  err1 = norm(fk1-fk2)/norm(fk1); \
	  fprintf('nufft1d1 vs dirft1d1: err=%e ier=%d\n', err1, ier); \
	  assert(err1 < 1e-10 && ier == 0); \
	  cj2 = dirft1d2(nj, xj, iflag, ms, fk1); \
	  [cj3,ier2] = nufft1d2(nj, xj, iflag, eps0, ms, fk1); \
	  err2 = norm(cj2-cj3)/norm(cj2); \
	  fprintf('nufft1d2 vs dirft1d2: err=%e ier=%d\n', err2, ier2); \
	  assert(err2 < 1e-10 && ier2 == 0); \
	  nk = 30; sk = -10 + 20*rand(nk,1); \
	  fk3 = dirft1d3(nj, xj, cj, iflag, nk, sk); \
	  [fk4,ier3] = nufft1d3(nj, xj, cj, iflag, eps0, nk, sk); \
	  err3 = norm(fk3-fk4)/norm(fk3); \
	  fprintf('nufft1d3 vs dirft1d3: err=%e ier=%d\n', err3, ier3); \
	  assert(err3 < 1e-10 && ier3 == 0); \
	  fprintf('ALL nufft1d TESTS PASSED (fmex backend)\n'); \
	"

clean:
	rm -f nufft1dmex.f90 nufft1dmex.mex nufft1dmex.o
	rm -f dirft1d1.m dirft1d2.m dirft1d3.m
	rm -f nufft1d1.m nufft1d2.m nufft1d3.m
	rm -f *.o

.PHONY: all generate compile test clean
