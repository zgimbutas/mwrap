"""
mwrap_typecheck.py — Semantic analysis and type classification.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Converted to Python by Zydrunas Gimbutas (2026),
with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
"""

import sys
from mwrap_ast import (
    VT, Expr, TypeQual, Var, Func,
    promote_int,
    iospec_is_input, iospec_is_output, iospec_is_inonly,
)


# ---------------------------------------------------------------------------
# Label assignment
# ---------------------------------------------------------------------------

def _label_dim_args_expr(args, icount):
    """Assign input_label to dimension expressions; returns updated icount."""
    for e in args:
        e.input_label = icount
        icount += 1
    return icount


def _label_dim_args_var(vars, icount):
    """Walk var list, label dimension expressions."""
    for v in vars:
        if v.qual:
            icount = _label_dim_args_expr(v.qual.args, icount)
    return icount


def _label_args_var(vars, icount, ocount):
    """Assign input/output labels to vars; returns (icount, ocount)."""
    for v in vars:
        if iospec_is_input(v.iospec):
            v.input_label = icount
            icount += 1
        if iospec_is_output(v.iospec):
            v.output_label = ocount
            ocount += 1
    return icount, ocount


def label_args(f):
    """Assign prhs[] / plhs[] indices to a Func's variables."""
    icount = 1 if f.thisv else 0
    ocount = 0
    icount, ocount = _label_args_var(f.ret, icount, ocount)
    icount, ocount = _label_args_var(f.args, icount, ocount)
    icount = _label_dim_args_var(f.ret, icount)
    icount = _label_dim_args_var(f.args, icount)


# ---------------------------------------------------------------------------
# Type-info assignment
# ---------------------------------------------------------------------------

def _assign_scalar_tinfo(v, line, tags, tagp, tagr, taga, tagar):
    """Assign tinfo for a scalar/complex type. Returns error count."""
    if not v.qual:
        v.tinfo = tags
    elif v.qual.qual == '*':
        v.tinfo = tagp
    elif v.qual.qual == '&':
        v.tinfo = tagr
    elif v.qual.qual == 'a':
        v.tinfo = taga
        # check max 2D
        if len(v.qual.args) > 2:
            print(f"Error ({line}): Array {v.name} should be 1D or 2D",
                  file=sys.stderr)
            return 1
    elif v.qual.qual == 'r':
        v.tinfo = tagar
        if tagar == VT.unk:
            print(f"Error ({line}): Array ref {v.name} must be to a real array",
                  file=sys.stderr)
            return 1
        if len(v.qual.args) > 2:
            print(f"Error ({line}): Array {v.name} should be 1D or 2D",
                  file=sys.stderr)
            return 1
    else:
        assert False, f"Unknown qual '{v.qual.qual}'"
    return 0


def assign_tinfo(ctx, v, line):
    """Assign VT_* tinfo to a single Var. Returns error count."""
    bt = v.basetype

    if ctx.is_scalar_type(bt):
        return _assign_scalar_tinfo(v, line,
                                    VT.scalar, VT.p_scalar, VT.r_scalar,
                                    VT.array, VT.rarray)
    elif ctx.is_cscalar_type(bt):
        return _assign_scalar_tinfo(v, line,
                                    VT.cscalar, VT.p_cscalar, VT.r_cscalar,
                                    VT.carray, VT.unk)
    elif ctx.is_zscalar_type(bt):
        return _assign_scalar_tinfo(v, line,
                                    VT.zscalar, VT.p_zscalar, VT.r_zscalar,
                                    VT.zarray, VT.unk)
    elif bt == "const":
        if v.qual:
            print(f"Error ({line}): Constant {v.name} cannot have modifiers",
                  file=sys.stderr)
            return 1
        v.tinfo = VT.const
        # Strip quotes from name if present
        if v.name and v.name.startswith("'"):
            v.name = v.name.replace("'", "")

    elif bt == "cstring":
        if v.qual and v.qual.qual != 'a':
            print(f"Error ({line}): String type {v.name} cannot have modifiers",
                  file=sys.stderr)
            return 1
        if v.qual and len(v.qual.args) > 1:
            print(f"Error ({line}): Strings are one dimensional",
                  file=sys.stderr)
            return 1
        v.tinfo = VT.string

    elif bt == "mxArray":
        if v.qual:
            print(f"Error ({line}): mxArray {v.name} cannot have modifiers",
                  file=sys.stderr)
            return 1
        v.tinfo = VT.mx

    else:
        # Object type
        if not v.qual:
            v.tinfo = VT.obj
        elif v.qual.qual == '*':
            v.tinfo = VT.p_obj
        elif v.qual.qual == '&':
            v.tinfo = VT.r_obj
        elif v.qual.qual in ('a', 'r'):
            print(f"Error ({line}): {v.name} cannot be an array of object {bt}",
                  file=sys.stderr)
            return 1
        else:
            assert False

    return 0


# ---------------------------------------------------------------------------
# Return-value validation
# ---------------------------------------------------------------------------

def _typecheck_return(ctx, ret, line):
    if not ret:
        return 0
    v = ret[0]
    err = assign_tinfo(ctx, v, line)

    if v.tinfo in (VT.array, VT.carray, VT.zarray):
        if not (v.qual and v.qual.args):
            print(f"Error ({line}): Return array {v.name} must have dims",
                  file=sys.stderr)
            err += 1
    elif v.tinfo == VT.const:
        print(f"Error ({line}): Cannot return constant", file=sys.stderr)
        err += 1
    elif v.tinfo == VT.rarray:
        print(f"Error ({line}): Ref to array {v.name} looks just like array on return",
              file=sys.stderr)
        err += 1
    elif v.tinfo == VT.string and v.qual:
        print(f"Error ({line}): Return string {v.name} cannot have dims",
              file=sys.stderr)
        err += 1
    return err


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------

def _typecheck_args(ctx, args, line):
    err = 0
    for v in args:
        err += assign_tinfo(ctx, v, line)

        if iospec_is_inonly(v.iospec):
            continue

        # Output / inout checks
        if v.name and v.name[0:1].isdigit():
            print(f"Error ({line}): Number {v.name} cannot be output",
                  file=sys.stderr)
            err += 1

        if (v.tinfo in (VT.obj, VT.p_obj, VT.r_obj) and
                not ctx.is_mxarray_type(v.basetype)):
            print(f"Error ({line}): Object {v.name} cannot be output",
                  file=sys.stderr)
            err += 1
        elif (v.tinfo in (VT.array, VT.carray, VT.zarray, VT.rarray) and
              v.iospec == 'o' and
              not (v.qual and v.qual.args)):
            print(f"Error ({line}): Output array {v.name} must have dims",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.rarray and not iospec_is_output(v.iospec):
            print(f"Error ({line}): Array ref {v.name} *must* be output",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.scalar:
            print(f"Error ({line}): Scalar {v.name} cannot be output",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.const:
            print(f"Error ({line}): Constant {v.name} cannot be output",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.string and not (v.qual and v.qual.args):
            print(f"Error ({line}): String {v.name} cannot be output without size",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.mx and v.iospec == 'b':
            print(f"Error ({line}): mxArray {v.name} cannot be used for inout",
                  file=sys.stderr)
            err += 1

    return err


# ---------------------------------------------------------------------------
# Fortran-ize arguments
# ---------------------------------------------------------------------------

def _fortranize_args_var(args, line):
    """Convert scalar args to pointer-to-scalar for FORTRAN. Returns error count."""
    err = 0
    for v in args:
        if v.tinfo in (VT.obj, VT.p_obj, VT.r_obj):
            print(f"Error ({line}): Cannot pass object {v.name} to FORTRAN",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.rarray:
            print(f"Error ({line}): Cannot pass pointer ref {v.name} to FORTRAN",
                  file=sys.stderr)
            err += 1
        elif v.tinfo == VT.string:
            print(f"Warning ({line}): Danger passing C string {v.name} to FORTRAN",
                  file=sys.stderr)
        elif v.tinfo in (VT.scalar, VT.r_scalar):
            v.tinfo = VT.p_scalar
        elif v.tinfo in (VT.cscalar, VT.r_cscalar):
            v.tinfo = VT.p_cscalar
        elif v.tinfo in (VT.zscalar, VT.r_zscalar):
            v.tinfo = VT.p_zscalar
    return err


def _fortranize_ret(v, line):
    if not v:
        return 0
    if v.tinfo in (VT.cscalar, VT.zscalar):
        print(f"Warning ({line}): Danger returning complex from FORTRAN",
              file=sys.stderr)
    elif v.tinfo != VT.scalar:
        print(f"Error ({line}): Can only return scalars from FORTRAN",
              file=sys.stderr)
        return 1
    return 0


def _fortranize_args(f, line):
    if not f.fort:
        return 0
    err = _fortranize_args_var(f.args, line)
    if f.ret:
        err += _fortranize_ret(f.ret[0], line)
    return err


# ---------------------------------------------------------------------------
# Top-level typecheck
# ---------------------------------------------------------------------------

def typecheck(ctx, f, line):
    """Run full semantic analysis on a Func. Returns error count."""
    label_args(f)
    return (_typecheck_return(ctx, f.ret, line) +
            _typecheck_args(ctx, f.args, line) +
            _fortranize_args(f, line))
