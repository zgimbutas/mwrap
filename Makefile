include make.inc

.PHONY: bin doc test demo clean realclean

bin:
	(cd src; make)

doc:
	(cd doc; make)

test: bin
	(cd testing; make)

demo:
	(cd example; make)

clean:
	rm -f mwrap
	(cd src; make clean)
	(cd example; make clean)
	(cd testing; make clean)

realclean: clean
	(cd src; make realclean)
