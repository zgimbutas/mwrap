/*
 * mwrap-version.h
 *   Single source of truth for the mwrap version (C++ implementation).
 *
 * Keep in sync with python/mwrap_version.py; the parity suite
 * (testing/test_python.sh) fails on any mismatch because both
 * implementations stamp this version into their generated output.
 */
#ifndef MWRAP_VERSION_H
#define MWRAP_VERSION_H

#define MWRAP_VERSION "1.3.5"

#endif /* MWRAP_VERSION_H */
