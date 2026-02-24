"""
mwrap_ast.py — AST nodes, type registries, and helpers for mwrap.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Converted to Python by Zydrunas Gimbutas (2026),
with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
"""

from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# VT_* classification codes
# ---------------------------------------------------------------------------

class VT(IntEnum):
    unk       = 0
    obj       = 1
    array     = 2
    carray    = 3
    zarray    = 4
    rarray    = 5
    scalar    = 6
    cscalar   = 7
    zscalar   = 8
    string    = 9
    mx        = 10
    p_obj     = 11
    p_scalar  = 12
    p_cscalar = 13
    p_zscalar = 14
    r_obj     = 15
    r_scalar  = 16
    r_cscalar = 17
    r_zscalar = 18
    const     = 19


# ---------------------------------------------------------------------------
# iospec / VT classification helpers (single source of truth)
# ---------------------------------------------------------------------------

def iospec_is_input(c):   return c in ('i', 'b')
def iospec_is_output(c):  return c in ('o', 'b')
def iospec_is_inonly(c):  return c == 'i'

def is_array(tinfo):
    return tinfo in (VT.array, VT.carray, VT.zarray)

def is_obj(tinfo):
    return tinfo in (VT.obj, VT.p_obj, VT.r_obj)

def complex_tinfo(v):
    return v.tinfo in (VT.carray, VT.zarray,
                       VT.cscalar, VT.zscalar,
                       VT.r_cscalar, VT.r_zscalar,
                       VT.p_cscalar, VT.p_zscalar)

def nullable_return(f):
    return (f.ret and f.ret[0].tinfo in (
        VT.string, VT.array, VT.carray, VT.zarray,
        VT.p_scalar, VT.p_cscalar, VT.p_zscalar))


# ---------------------------------------------------------------------------
# AST node dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Expr:
    value: str
    input_label: int = -1


@dataclass
class TypeQual:
    qual: str          # '*', '&', 'a' (array), 'r' (array ref)
    args: list = field(default_factory=list)  # list[Expr]


@dataclass
class Var:
    devicespec: str    # 'c' (cpu) or 'g' (gpu)
    iospec: str        # 'i','o','b'
    basetype: str
    qual: Optional[TypeQual]
    name: str
    tinfo: int = VT.unk
    input_label: int = -1
    output_label: int = -1


@dataclass
class Func:
    thisv: Optional[str]
    classv: Optional[str]
    funcv: str
    fname: str
    line: int
    fort: bool = False
    id: int = -1
    args: list = field(default_factory=list)  # list[Var]
    ret: list = field(default_factory=list)   # list[Var] (0 or 1 elements)
    same: list = field(default_factory=list)  # list[Func] — duplicate signatures


# ---------------------------------------------------------------------------
# MwrapContext — all mutable state in one object
# ---------------------------------------------------------------------------

class MwrapContext:
    def __init__(self):
        # CLI flags
        self.mw_use_gpu = False
        self.mw_generate_catch = False
        self.mw_use_c99_complex = False
        self.mw_use_cpp_complex = False
        self.mw_promote_int = 0

        # Type registries
        self.scalar_decls = set()
        self.cscalar_decls = set()
        self.zscalar_decls = set()
        self.mxarray_decls = set()
        self.class_decls = {}   # str -> list[str]

        # Type usage tracking
        self.mw_use_int32_t = 0
        self.mw_use_int64_t = 0
        self.mw_use_uint32_t = 0
        self.mw_use_uint64_t = 0
        self.mw_use_longlong = 0
        self.mw_use_ulonglong = 0
        self.mw_use_ulong = 0
        self.mw_use_uint = 0
        self.mw_use_ushort = 0
        self.mw_use_uchar = 0

    def init_scalar_types(self):
        self.scalar_decls.clear()
        for t in ("double", "float",
                  "long", "int", "short", "char",
                  "ulong", "uint", "ushort", "uchar",
                  "int32_t", "int64_t", "uint32_t", "uint64_t",
                  "bool", "size_t", "ptrdiff_t"):
            self.scalar_decls.add(t)

    def is_scalar_type(self, name):    return name in self.scalar_decls
    def is_cscalar_type(self, name):   return name in self.cscalar_decls
    def is_zscalar_type(self, name):   return name in self.zscalar_decls
    def is_mxarray_type(self, name):   return name in self.mxarray_decls

    def add_scalar_type(self, name):   self.scalar_decls.add(name)
    def add_cscalar_type(self, name):  self.cscalar_decls.add(name)
    def add_zscalar_type(self, name):  self.zscalar_decls.add(name)
    def add_mxarray_type(self, name):  self.mxarray_decls.add(name)


# ---------------------------------------------------------------------------
# Functions that need context
# ---------------------------------------------------------------------------

def promote_int(ctx, name: str) -> str:
    if name == "int32_t":  ctx.mw_use_int32_t = 1
    if name == "int64_t":  ctx.mw_use_int64_t = 1
    if name == "uint32_t": ctx.mw_use_uint32_t = 1
    if name == "uint64_t": ctx.mw_use_uint64_t = 1
    if name == "ulong":    ctx.mw_use_ulong = 1
    if name == "uint":     ctx.mw_use_uint = 1
    if name == "ushort":   ctx.mw_use_ushort = 1
    if name == "uchar":    ctx.mw_use_uchar = 1

    if ctx.mw_promote_int == 1:
        if name == "uint":  ctx.mw_use_ulong = 1
        if name == "int":   return "long"
        if name == "uint":  return "ulong"
    elif ctx.mw_promote_int == 2:
        if name == "uint":  ctx.mw_use_ulong = 1
        if name == "ulong": ctx.mw_use_ulong = 1
        if name == "int":   return "long"
        if name == "long":  return "long"
        if name == "uint":  return "ulong"
        if name == "ulong": return "ulong"
    elif ctx.mw_promote_int == 3:
        if name == "int":   ctx.mw_use_int32_t = 1
        if name == "long":  ctx.mw_use_int64_t = 1
        if name == "uint":  ctx.mw_use_uint32_t = 1
        if name == "ulong": ctx.mw_use_uint64_t = 1
        if name == "int":   return "int32_t"
        if name == "long":  return "int32_t"
        if name == "uint":  return "uint64_t"
        if name == "ulong": return "uint64_t"
    elif ctx.mw_promote_int == 4:
        if name == "int":   ctx.mw_use_int64_t = 1
        if name == "long":  ctx.mw_use_int64_t = 1
        if name == "uint":  ctx.mw_use_uint64_t = 1
        if name == "ulong": ctx.mw_use_uint64_t = 1
        if name == "int":   return "int64_t"
        if name == "long":  return "int64_t"
        if name == "uint":  return "uint64_t"
        if name == "ulong": return "uint64_t"
    return name


def add_inherits(ctx, childname: str, parents: list):
    """Register childname as child of each parent in parents list."""
    for parent in parents:
        if parent not in ctx.class_decls:
            ctx.class_decls[parent] = []
        ctx.class_decls[parent].insert(0, childname)


# ---------------------------------------------------------------------------
# ID string (canonical signature for deduplication)
# ---------------------------------------------------------------------------

def _id_expr(args: list) -> str:
    return "x" * len(args)


def _id_qual(q: Optional[TypeQual]) -> str:
    if not q:
        return ""
    if q.qual == 'a':
        return "[" + _id_expr(q.args) + "]"
    return q.qual


def _id_var_single(ctx, v: Var) -> str:
    name = ""
    if v.devicespec == 'c':
        name += "c "
    elif v.devicespec == 'g':
        name += "g "

    io = v.iospec
    if io == 'i':   name += "i "
    elif io == 'o': name += "o "
    else:           name += "io "

    name += promote_int(ctx, v.basetype)
    name += _id_qual(v.qual)
    if v.tinfo == VT.const:
        name += " " + v.name
    return name


def _id_var(ctx, vars: list) -> str:
    return ", ".join(_id_var_single(ctx, v) for v in vars)


def id_string(ctx, f) -> str:
    if not f:
        return ""
    name = ""
    if f.ret:
        name += _id_var(ctx, f.ret) + " = "
    if f.thisv:
        name += f.thisv + "->" + f.classv + "."
    name += f.funcv + "(" + _id_var(ctx, f.args) + ")"
    return name


# ---------------------------------------------------------------------------
# AST printing (for C comments)
# ---------------------------------------------------------------------------

def _print_expr(args: list) -> str:
    return ", ".join(e.value for e in args)


def _print_qual(q):
    if not q:
        return ""
    if q.qual == 'a':
        return "[" + _print_expr(q.args) + "]"
    return q.qual


def _print_devicespec(v):
    if v.devicespec == 'g':
        return "gpu "
    return ""


def _print_iospec(v):
    m = {'o': "output ", 'b': "inout "}
    return m.get(v.iospec, "")


def _print_var(v):
    return v.basetype + _print_qual(v.qual) + " " + v.name


def _print_args(vars: list) -> str:
    return ", ".join(
        _print_devicespec(v) + _print_iospec(v) + _print_var(v)
        for v in vars
    )


def print_func(f):
    """Human-readable translation of Func AST (for C comments)."""
    if not f:
        return ""
    s = ""
    if f.ret:
        s += _print_var(f.ret[0]) + " = "
    if f.thisv:
        s += f"{f.thisv}->{f.classv}."
    s += f"{f.funcv}({_print_args(f.args)});\n"
    return s
