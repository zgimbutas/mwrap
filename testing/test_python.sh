#!/usr/bin/env bash
#
# test_python.sh — test the Python mwrap port against reference files
# and against C++ mwrap output.
#
# Usage:
#   bash testing/test_python.sh <path-to-cpp-mwrap> <path-to-python-mwrap>
#
# Example:
#   bash testing/test_python.sh build/mwrap python/mwrap

set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <cpp-mwrap> <python-mwrap>"
    exit 1
fi

MWRAP_CPP="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
MWRAP_PY="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMPDIR_BASE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BASE"' EXIT

PASS=0
FAIL=0
ERRORS=""

pass() {
    PASS=$((PASS + 1))
    echo "  PASS: $1"
}

fail() {
    FAIL=$((FAIL + 1))
    ERRORS="${ERRORS}  FAIL: $1\n"
    echo "  FAIL: $1"
}

# ----------------------------------------------------------------
# Group A: Reference-file tests
# Run from the testing directory with relative .mw paths so that
# error messages use basenames (matching the .ref files).
# ----------------------------------------------------------------
echo "=== Group A: Reference-file tests ==="

run_ref_test() {
    local name="$1"
    local mw_basename="$2"
    local ref_file="$3"
    shift 3
    local flags=("$@")

    local tmpout="$TMPDIR_BASE/${name}.stderr"

    # Run Python mwrap from SCRIPT_DIR with relative .mw path; expect nonzero exit
    if (cd "$SCRIPT_DIR" && "$MWRAP_PY" "${flags[@]}" "$mw_basename" 2>"$tmpout") ; then
        fail "$name (expected nonzero exit, got 0)"
        return
    fi

    # Normalize "end of file" -> "$end" to match Bison 3.x convention
    sed -i.bak 's/end of file/$end/g' "$tmpout"

    if diff -u "$ref_file" "$tmpout" >/dev/null 2>&1; then
        pass "$name"
    else
        fail "$name (stderr differs from reference)"
        diff -u "$ref_file" "$tmpout" || true
    fi
}

run_ref_test test_syntax \
    test_syntax.mw \
    "$SCRIPT_DIR/test_syntax.ref" \
    -cppcomplex

run_ref_test test_typecheck \
    test_typecheck.mw \
    "$SCRIPT_DIR/test_typecheck.ref" \
    -cppcomplex

# ----------------------------------------------------------------
# Group B: Output equivalence tests (Python vs C++)
# ----------------------------------------------------------------
echo ""
echo "=== Group B: Output equivalence tests ==="

run_equiv_test() {
    local name="$1"
    local mw_file="$2"
    local cc_ext="$3"       # .cc or .c
    local gen_m="$4"        # "yes" or "no"
    shift 4
    local flags=()
    if [ $# -gt 0 ]; then
        flags=("$@")
    fi

    local cpp_dir="$TMPDIR_BASE/cpp_${name}"
    local py_dir="$TMPDIR_BASE/py_${name}"
    mkdir -p "$cpp_dir" "$py_dir"

    local mex_name="${name}mex"
    local cc_file="${mex_name}${cc_ext}"

    # Copy test_include2.mw if needed (for @include)
    if [ -f "$SCRIPT_DIR/test_include2.mw" ]; then
        cp "$SCRIPT_DIR/test_include2.mw" "$cpp_dir/"
        cp "$SCRIPT_DIR/test_include2.mw" "$py_dir/"
    fi

    local cpp_args=(-mex "$mex_name" -c "$cc_file")
    local py_args=(-mex "$mex_name" -c "$cc_file")

    if [ "$gen_m" = "yes" ]; then
        cpp_args+=(-m "${name}.m")
        py_args+=(-m "${name}.m")
    else
        cpp_args+=(-mb)
        py_args+=(-mb)
    fi

    if [ ${#flags[@]} -gt 0 ]; then
        cpp_args+=("${flags[@]}")
        py_args+=("${flags[@]}")
    fi
    cpp_args+=("$mw_file")
    py_args+=("$mw_file")

    # Run C++ mwrap
    if ! (cd "$cpp_dir" && "$MWRAP_CPP" "${cpp_args[@]}" 2>/dev/null); then
        fail "$name (C++ mwrap failed)"
        return
    fi

    # Run Python mwrap
    if ! (cd "$py_dir" && "$MWRAP_PY" "${py_args[@]}" 2>/dev/null); then
        fail "$name (Python mwrap failed)"
        return
    fi

    # Compare generated C/C++ file
    if diff -u "$cpp_dir/$cc_file" "$py_dir/$cc_file" >/dev/null 2>&1; then
        pass "$name ($cc_file)"
    else
        fail "$name ($cc_file differs)"
        diff -u "$cpp_dir/$cc_file" "$py_dir/$cc_file" | head -40 || true
    fi

    # Compare generated .m file (if applicable)
    if [ "$gen_m" = "yes" ]; then
        if diff -u "$cpp_dir/${name}.m" "$py_dir/${name}.m" >/dev/null 2>&1; then
            pass "$name (${name}.m)"
        else
            fail "$name (${name}.m differs)"
            diff -u "$cpp_dir/${name}.m" "$py_dir/${name}.m" | head -40 || true
        fi
    fi
}

run_equiv_test test_transfers \
    "$SCRIPT_DIR/test_transfers.mw" .cc yes

run_equiv_test test_cpp_complex \
    "$SCRIPT_DIR/test_cpp_complex.mw" .cc yes \
    -cppcomplex

run_equiv_test test_c99_complex \
    "$SCRIPT_DIR/test_c99_complex.mw" .c yes \
    -c99complex

run_equiv_test test_catch \
    "$SCRIPT_DIR/test_catch.mw" .cc yes \
    -catch

run_equiv_test test_fortran1 \
    "$SCRIPT_DIR/test_fortran1.mw" .cc yes

run_equiv_test test_fortran2 \
    "$SCRIPT_DIR/test_fortran2.mw" .c yes

run_equiv_test test_include \
    "$SCRIPT_DIR/test_include.mw" .cc yes

run_equiv_test test_single \
    "$SCRIPT_DIR/test_single.mw" .cc no \
    -cppcomplex

run_equiv_test test_char \
    "$SCRIPT_DIR/test_char.mw" .cc no \
    -cppcomplex

# ----------------------------------------------------------------
# Summary
# ----------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"

if [ $FAIL -ne 0 ]; then
    echo ""
    echo "Failures:"
    echo -e "$ERRORS"
    exit 1
fi

exit 0
