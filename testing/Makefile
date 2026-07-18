include ../make.inc

MWRAP = ../mwrap

all: test_transfers test_cpp_complex $(TESTC99COMPLEX) test_syntax \
	test_typecheck test_catch test_fortran1 test_fortran2 \
	test_redirect test_include test_single_cpp test_char_cpp
# run the tests...
	octave-cli --no-init-file --quiet test_all.m

test_transfers: 
	$(MWRAP) -mex test_transfersmex \
		-c test_transfersmex.cc \
		-m test_transfers.m test_transfers.mw
	$(MEX) test_transfersmex.cc

test_cpp_complex: 
	$(MWRAP) -cppcomplex \
		-mex test_cpp_complexmex \
		-c test_cpp_complexmex.cc \
		-m test_cpp_complex.m test_cpp_complex.mw
	$(MEX) test_cpp_complexmex.cc

test_c99_complex: 
	$(MWRAP) -c99complex \
		-mex test_c99_complexmex \
		-c test_c99_complexmex.c \
		-m test_c99_complex.m test_c99_complex.mw
	$(MEX) test_c99_complexmex.c

# The following two are designed to create mwrap errors, whose stderr is
# compared against reference files. The minus sign only ignores mwrap's
# (intentional) nonzero exit status; the diff still gates the test.
# Bison >= 3.6 says "end of file" where older versions said "$end", so the
# log is normalized before comparison (as in CMake and test_python.sh).
test_syntax:
	- $(MWRAP) -cppcomplex test_syntax.mw 2> test_syntax.log
	sed 's/end of file/$$end/g' test_syntax.log | diff - test_syntax.ref

test_typecheck:
	- $(MWRAP) -cppcomplex test_typecheck.mw 2> test_typecheck.log
	diff test_typecheck.log test_typecheck.ref


test_catch:
	$(MWRAP) -mex test_catchmex -catch \
		-c test_catchmex.cc \
		-m test_catch.m \
		test_catch.mw
	$(MEX) test_catchmex.cc

test_fortran1:
	$(MWRAP) -mex test_fortran1mex \
		-c test_fortran1mex.cc \
		-m test_fortran1.m \
		test_fortran1.mw
	$(MEX) test_fortran1mex.cc

test_fortran2:
	$(MWRAP) -mex test_fortran2mex \
		-c test_fortran2mex.c \
		-m test_fortran2.m \
		test_fortran2.mw
	$(MEX) test_fortran2mex.c

test_redirect:
	$(MWRAP) -mb test_redirect.mw 

test_include: 
	$(MWRAP) -mex test_includemex\
		-c test_includemex.cc \
		-m test_include.m test_include.mw
	$(MEX) test_includemex.cc

# these two are tested by test_char.m ...
test_char_cpp: 
	$(MWRAP) -cppcomplex -mex test_charmex \
		-c test_charmex.cc \
		-mb test_char.mw
	$(MEX) test_charmex.cc

test_char_c99: 
	$(MWRAP) -mex test_charmex \
		-c test_charmex.c \
		-mb test_char.mw
	$(MEX) test_charmex.c

# these last two are tested by test_single.m ...
test_single_cpp: 
	$(MWRAP) -cppcomplex -mex test_singlemex \
		-c test_singlemex.cc \
		-mb test_single.mw
	$(MEX) test_singlemex.cc

test_single_c99: 
	$(MWRAP) -c99complex -mex test_singlemex \
		-c test_singlemex.c \
		-mb test_single.mw
	$(MEX) test_singlemex.c

test_gpu:
	$(MWRAP) -gpu -list -cppcomplex -mb -mex test_gpu -c test_gpu.cu test_gpu.mw

test_gpu_complex:
	$(MWRAP) -gpu -list -cppcomplex -mb -mex test_gpu_complex -c test_gpu_complex.cu test_gpu_complex.mw

test_gpu_int32:
	$(MWRAP) -gpu -list -cppcomplex -mb -mex test_gpu_int32 -c test_gpu_int32.cu test_gpu_int32.mw

# GPU tests: requires CUDA toolkit and GPU device
# Run mwrap targets first (test_gpu, test_gpu_complex, test_gpu_int32),
# then run this target from MATLAB/Octave with GPU support.
test_all_gpu: test_gpu test_gpu_complex test_gpu_int32
	matlab -batch "test_all_gpu"

test_cpu:
	$(MWRAP) -list -cppcomplex -mb -mex test_cpu -c test_cpu.cc test_cpu.mw

test_cpu_int32:
	$(MWRAP) -list -cppcomplex -mb -mex test_cpu_int32 -c test_cpu_int32.cc test_cpu_int32.mw

clean:
	rm -f *~ *.mex* *.o* test_typecheck.log test_syntax.log
	rm -f test_fortran1.m test_fortran2.m test_transfers.m test_catch.m
	rm -f test_fortran1mex.cc test_fortran2mex.c
	rm -f test_cpp_complex.m test_c99_complex.m
	rm -f test_transfersmex.cc test_catchmex.cc test_fortranmex.cc
	rm -f test_cpp_complexmex.cc test_c99_complexmex.c 
	rm -f test_redirect.m test_redirect1.m
	rm -f test_singlemex.c test_singlemex.cc
	rm -f add.m addf.m addz.m addc.m 
	rm -f arradd.m arraddf.m arraddz.m arraddc.m 
	rm -f test_include.m test_includemex.cc
	rm -f test_charmex.c test_charmex.cc
	rm -f addchar.m arraddchar.m
	rm -f test_cpu.cc timestwo_cpu.m
	rm -f test_cpu_int32.cc timestwo_cpu_int32.m
