"""
mwrap_mgen.py — MATLAB stub generator.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Converted to Python by Zydrunas Gimbutas (2026),
with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
"""

from mwrap_ast import VT


def _output_arg_names(args):
    """Collect names of output/inout arguments."""
    return [v.name for v in args if v.iospec in ('o', 'b')]


def _input_arg_strs(args):
    """Collect input argument strings (with leading ', ')."""
    parts = []
    for v in args:
        if v.tinfo == VT.const:
            parts.append(", 0")
        elif v.iospec in ('i', 'b'):
            parts.append(f", {v.name}")
    return parts


def _dim_arg_strs(vars):
    """Collect dimension argument strings (with leading ', ')."""
    parts = []
    for v in vars:
        if v.qual:
            for e in v.qual.args:
                parts.append(f", {e.value}")
    return parts


def print_matlab_call(fp, f, mexfunc):
    """Emit MATLAB stub for function call f."""
    fp.write(f"mex_id_ = {f.id};\n")

    out_names = _output_arg_names(f.ret) + _output_arg_names(f.args)
    if out_names:
        fp.write(f"[{', '.join(out_names)}] = ")

    rhs = [f"mex_id_"]
    if f.thisv:
        rhs.append(f", {f.thisv}")
    rhs.extend(_input_arg_strs(f.args))
    rhs.extend(_dim_arg_strs(f.ret))
    rhs.extend(_dim_arg_strs(f.args))
    fp.write(f"{mexfunc}({''.join(rhs)});\n")
