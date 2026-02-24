include ../make.inc


# === Primary targets ===

../mwrap: mwrap.o lex.yy.o mwrap-ast.o mwrap-typecheck.o \
	mwrap-mgen.o mwrap-cgen.o mwrap-octgen.o mwrap-cppgen.o mwrap-ast.h
	$(CXX) -o ../mwrap mwrap.o mwrap-ast.o \
		mwrap-typecheck.o mwrap-mgen.o mwrap-cgen.o \
		mwrap-octgen.o mwrap-cppgen.o \
		lex.yy.o

mwrap.o: mwrap.cc lex.yy.c mwrap-ast.h
	$(CXX) -c mwrap.cc

mwrap.cc mwrap.hh: mwrap.y
	$(BISON) -d -v mwrap.y -o mwrap.cc

ifeq ($(shell bison --version 2>&1 | sed -n 's/^.*GNU Bison.* \([0-9]*\).*$$/\1/p'), 3)
ERROR_VERBOSE = %define parse.error verbose
else
ERROR_VERBOSE = %error-verbose
endif

mwrap.y: mwrap.y.in
	sed -e 's/@ERROR_VERBOSE@/$(ERROR_VERBOSE)/' < mwrap.y.in > mwrap.y

lex.yy.o: lex.yy.c mwrap.hh
	$(CC) -c lex.yy.c

lex.yy.c: mwrap.l
	$(FLEX) mwrap.l

mwrap-ast.o: mwrap-ast.cc mwrap-ast.h 
	$(CXX) -c -g mwrap-ast.cc

mwrap-typecheck.o: mwrap-typecheck.cc mwrap-ast.h
	$(CXX) -c -g mwrap-typecheck.cc

mwrap-cgen.o: mwrap-cgen.cc mwrap-ast.h mwrap-support.h
	$(CXX) -c -g mwrap-cgen.cc

mwrap-mgen.o: mwrap-mgen.cc mwrap-ast.h
	$(CXX) -c -g mwrap-mgen.cc

mwrap-octgen.o: mwrap-octgen.cc mwrap-ast.h mwrap-oct-support.h
	$(CXX) -c -g mwrap-octgen.cc

mwrap-cppgen.o: mwrap-cppgen.cc mwrap-ast.h mwrap-cpp-support.h
	$(CXX) -c -g mwrap-cppgen.cc

mwrap-support.h: mwrap-support.c stringify
	./stringify mex_header < mwrap-support.c > mwrap-support.h

mwrap-oct-support.h: mwrap-oct-support.c stringify
	./stringify oct_header < mwrap-oct-support.c > mwrap-oct-support.h

mwrap-cpp-support.h: mwrap-cpp-support.c stringify
	./stringify cpp_header < mwrap-cpp-support.c > mwrap-cpp-support.h

stringify: stringify.c
	$(CC) -o stringify stringify.c


# === Clean-up targets ===

clean:
	rm -f mwrap.output
	rm -f *.o *~
	rm -f stringify

realclean: clean
	rm -f mwrap.y lex.yy.c mwrap.cc mwrap.hh mwrap-support.h mwrap-oct-support.h mwrap-cpp-support.h
