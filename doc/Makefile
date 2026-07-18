all: mwrap.pdf

RELEASE_DATE = $(shell grep "^Version " ../NEWS | head -n1 | sed "s/^Version .*(\(.*\)):/\1/")
VERSION = $(shell sed -n 's/^\#define MWRAP_VERSION "\(.*\)"/\1/p' ../src/mwrap-version.h)

mwrap.tex: mwrap.tex.in ../src/mwrap-version.h
	sed -e "s/@RELEASE_DATE@/$(RELEASE_DATE)/" -e "s/@VERSION@/$(VERSION)/" < mwrap.tex.in > mwrap.tex

mwrap.pdf: mwrap.tex
	pdflatex mwrap.tex

clean:
	rm -f mwrap.aux mwrap.log mwrap.tex mwrap.pdf
