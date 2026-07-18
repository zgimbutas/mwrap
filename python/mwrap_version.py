"""Single source of truth for the mwrap version (Python implementation).

Keep in sync with src/mwrap-version.h; the parity suite
(testing/test_python.sh) fails on any mismatch because both
implementations stamp this version into their generated output.
"""

__version__ = "1.3.5"
