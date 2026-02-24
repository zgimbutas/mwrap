"""
mwrap_octgen.py — Octave oct-file C++ code generator.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Oct-file backend by Zydrunas Gimbutas (2026),
with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
"""

import sys
from dataclasses import dataclass
from mwrap_ast import (
    VT, Expr, TypeQual, Var, Func,
    id_string, print_func,
    is_array, is_obj, complex_tinfo, nullable_return,
)


# ===================================================================
# Type property table for oct-file backend
# ===================================================================

@dataclass(frozen=True)
class OctTypeProps:
    matrix_type: str        # "Matrix", "FloatMatrix", "ComplexMatrix", etc.
    array_getter: str       # "matrix_value", "float_matrix_value", etc.
    scalar_getter: str      # "double_value", "float_value", etc.
    type_check: str         # "is_double_type", "is_single_type", etc.
    scalar_type: str        # C scalar type for casts: "double", "float", etc.
    numeric_create: str     # Octave type constructor: "Matrix", "FloatMatrix", etc.

_DEFAULT_OCT_PROPS = OctTypeProps("Matrix", "matrix_value", "double_value",
                                  "is_double_type", "double", "Matrix")

OCT_TYPE_PROPS = {
    "double":   OctTypeProps("Matrix",             "matrix_value",               "double_value",          "is_double_type",  "double",               "Matrix"),
    "float":    OctTypeProps("FloatMatrix",        "float_matrix_value",         "float_value",           "is_single_type",  "float",                "FloatMatrix"),
    "int32_t":  OctTypeProps("int32NDArray",       "int32_array_value",          "int_value",             "is_int32_type",   "int32_t",              "int32NDArray"),
    "int64_t":  OctTypeProps("int64NDArray",       "int64_array_value",          "int64_value",           "is_int64_type",   "int64_t",              "int64NDArray"),
    "uint32_t": OctTypeProps("uint32NDArray",      "uint32_array_value",         "uint_value",            "is_uint32_type",  "uint32_t",             "uint32NDArray"),
    "uint64_t": OctTypeProps("uint64NDArray",      "uint64_array_value",         "uint64_value",          "is_uint64_type",  "uint64_t",             "uint64NDArray"),
    "dcomplex": OctTypeProps("ComplexMatrix",      "complex_matrix_value",       "complex_value",         "is_complex_type", "std::complex<double>", "ComplexMatrix"),
    "fcomplex": OctTypeProps("FloatComplexMatrix", "float_complex_matrix_value", "float_complex_value",   "is_single_type",  "std::complex<float>",  "FloatComplexMatrix"),
    "char":     OctTypeProps("charMatrix",         "char_matrix_value",          "string_value",          "is_string",       "char",                 "charMatrix"),
}


def _oct_type_props(name):
    return OCT_TYPE_PROPS.get(name, _DEFAULT_OCT_PROPS)


# ===================================================================
# Utility functions (shared with mwrap_cgen.py)
# ===================================================================

def vname(v):
    if v.iospec == 'o':
        return f"out{v.output_label}_"
    return f"in{v.input_label}_"


def has_fortran(funcs):
    return any(f.fort for f in funcs)


def max_routine_id(funcs):
    maxid = 0
    for f in funcs:
        if f.id > maxid:
            maxid = f.id
    return maxid


def _alloc_size_expr(args):
    """Return C expression for product of dim args."""
    if not args:
        return "1"
    return "*".join(f"dim{e.input_label}_" for e in args)


# ===================================================================
# Complex type definitions (always C++ for oct-files)
# ===================================================================

def oct_cpp_complex(fp):
    fp.write("#include <complex>\n\n"
           "typedef std::complex<double> dcomplex;\n"
           "#define real_dcomplex(z) std::real(z)\n"
           "#define imag_dcomplex(z) std::imag(z)\n"
           "#define setz_dcomplex(z,r,i)  *z = dcomplex(r,i)\n\n"
           "typedef std::complex<float> fcomplex;\n"
           "#define real_fcomplex(z) std::real(z)\n"
           "#define imag_fcomplex(z) std::imag(z)\n"
           "#define setz_fcomplex(z,r,i)  *z = fcomplex(r,i)\n\n")


# ===================================================================
# Fortran name mangling (reused from mwrap_cgen.py)
# ===================================================================

def _fortran_funcs(funcs):
    """Yield unique Func objects for fortran functions."""
    seen = set()
    for f in funcs:
        if f.fort and f.funcv not in seen:
            seen.add(f.funcv)
            yield f


def oct_define_fnames(fp, funcs):
    fp.write("#if defined(MWF77_CAPS)\n")
    for fc in _fortran_funcs(funcs):
        fp.write(f"#define MWF77_{fc.funcv} {fc.funcv.upper()}\n")
    fp.write("#elif defined(MWF77_UNDERSCORE1)\n")
    for fc in _fortran_funcs(funcs):
        fp.write(f"#define MWF77_{fc.funcv} {fc.funcv.lower()}_\n")
    fp.write("#elif defined(MWF77_UNDERSCORE0)\n")
    for fc in _fortran_funcs(funcs):
        fp.write(f"#define MWF77_{fc.funcv} {fc.funcv.lower()}\n")
    fp.write("#else /* f2c convention */\n")
    for fc in _fortran_funcs(funcs):
        low = fc.funcv.lower()
        suffix = "__" if '_' in low else "_"
        fp.write(f"#define MWF77_{fc.funcv} {low}{suffix}\n")
    fp.write("#endif\n\n")


def _oct_fortran_arg(fp, args):
    parts = []
    for v in args:
        parts.append(f"{v.basetype}*")
    fp.write(", ".join(parts))


def oct_fortran_decls(fp, funcs):
    fp.write("#ifdef __cplusplus\n"
           "extern \"C\" { /* Prevent C++ name mangling */\n"
           "#endif\n\n"
           "#ifndef MWF77_RETURN\n"
           "#define MWF77_RETURN int\n"
           "#endif\n\n")
    for fc in _fortran_funcs(funcs):
        if fc.ret:
            fp.write(f"{fc.ret[0].basetype} ")
        else:
            fp.write("MWF77_RETURN ")
        fp.write(f"MWF77_{fc.funcv}(")
        _oct_fortran_arg(fp, fc.args)
        fp.write(");\n")
    fp.write("\n#ifdef __cplusplus\n"
           "} /* end extern C */\n"
           "#endif\n\n")


# ===================================================================
# Class polymorphism getters (oct-file version)
# ===================================================================

def _oct_casting_getter_type(fp, name):
    fp.write(f"    {name}* p_{name} = NULL;\n"
           f"    sscanf(pbuf, \"{name}:%p\", &p_{name});\n"
           f"    if (p_{name})\n"
           f"        return p_{name};\n\n")


def _oct_casting_getter(fp, cname, inherits):
    fp.write(f"\nstatic {cname}* mwOctGetP_{cname}(const octave_value& a, const char** e)\n")
    fp.write("{\n"
           "    if (a.is_double_type() && a.numel() == 1 && a.double_value() == 0)\n"
           "        return NULL;\n"
           "    if (!a.is_string()) {\n"
           "        *e = \"Invalid pointer\";\n"
           "        return NULL;\n"
           "    }\n"
           "    char pbuf[128];\n"
           "    std::string s = a.string_value();\n"
           "    strncpy(pbuf, s.c_str(), sizeof(pbuf)-1);\n"
           "    pbuf[sizeof(pbuf)-1] = '\\0';\n\n")
    _oct_casting_getter_type(fp, cname)
    for name in inherits:
        _oct_casting_getter_type(fp, name)
    fp.write(f"    *e = \"Invalid pointer to {cname}\";\n"
           f"    return NULL;\n"
           f"}}\n\n")


def oct_casting_getters(fp, ctx):
    for parent in sorted(ctx.class_decls.keys()):
        _oct_casting_getter(fp, parent, ctx.class_decls[parent])


# ===================================================================
# Per-stub helpers: declarations
# ===================================================================

def _declare_type(v):
    """Return C type string for a variable declaration."""
    if is_obj(v.tinfo) or is_array(v.tinfo):
        return f"{v.basetype}*"
    if v.tinfo == VT.rarray:
        return f"const {v.basetype}*"
    if v.tinfo in (VT.scalar, VT.cscalar, VT.zscalar,
                   VT.r_scalar, VT.r_cscalar, VT.r_zscalar,
                   VT.p_scalar, VT.p_cscalar, VT.p_zscalar):
        return v.basetype
    if v.tinfo == VT.string:
        return "char*"
    if v.tinfo == VT.mx:
        if v.iospec == 'i':
            return "octave_value"
        return "octave_value"
    assert False, f"Unknown tinfo {v.tinfo} for {v.name}"


def _declare_in_args(fp, args):
    for v in args:
        if v.iospec != 'o' and v.tinfo != VT.const:
            tb = _declare_type(v)
            if is_array(v.tinfo) or is_obj(v.tinfo) or v.tinfo == VT.string:
                fp.write(f"    {tb:10s}  in{v.input_label}_ =0; /* {v.name:10s} */\n")
                # For arrays backed by Octave Matrix, declare the Matrix at function scope
                if is_array(v.tinfo):
                    zinfo = _complex_matrix_info(v)
                    bt = v.basetype
                    if zinfo:
                        fp.write(f"    {zinfo[0]}  mat_in{v.input_label}_;\n")
                    elif bt in OCT_TYPE_PROPS:
                        tp = _oct_type_props(bt)
                        fp.write(f"    {tp.matrix_type}  mat_in{v.input_label}_;\n")
            elif v.tinfo == VT.mx:
                fp.write(f"    {tb:10s}  in{v.input_label}_;    /* {v.name:10s} */\n")
            else:
                fp.write(f"    {tb:10s}  in{v.input_label}_;    /* {v.name:10s} */\n")


def _declare_out_args(fp, args):
    for v in args:
        if v.iospec == 'o':
            if v.tinfo == VT.mx:
                # For oct-files, output mxArray maps to octave_value
                fp.write(f"    octave_value  retval_mx{v.output_label}_;   /* {v.name:10s} */\n")
                continue
            tb = _declare_type(v)
            if is_array(v.tinfo) or is_obj(v.tinfo) or v.tinfo == VT.string:
                fp.write(f"    {tb:10s}  out{v.output_label}_=0; /* {v.name:10s} */\n")
            else:
                fp.write(f"    {tb:10s}  out{v.output_label}_;   /* {v.name:10s} */\n")


def _declare_dim_args_expr(fp, args):
    for e in args:
        fp.write(f"    {'octave_idx_type':10s}  dim{e.input_label}_;   /* {e.value:10s} */\n")


def _declare_dim_args_var(fp, vars):
    for v in vars:
        if v.qual:
            _declare_dim_args_expr(fp, v.qual.args)


def _declare_args(fp, f):
    if f.thisv:
        tb = f"{f.classv}*"
        fp.write(f"    {tb:10s}  in0_ =0; /* {f.thisv:10s} */\n")
    _declare_in_args(fp, f.args)
    if not nullable_return(f):
        _declare_out_args(fp, f.ret)
    _declare_out_args(fp, f.args)
    _declare_dim_args_var(fp, f.ret)
    _declare_dim_args_var(fp, f.args)
    if f.ret or f.args or f.thisv:
        fp.write("\n")


# ===================================================================
# Unpack dims (oct-file version)
# ===================================================================

def _unpack_dims_expr(fp, args):
    count = 0
    for e in args:
        fp.write(f"    dim{e.input_label}_ = (octave_idx_type) mwOctGetScalar(args({e.input_label}), &mw_err_txt_);\n")
        count += 1
    return count


def _unpack_dims_var(fp, vars):
    count = 0
    for v in vars:
        if v.qual:
            count += _unpack_dims_expr(fp, v.qual.args)
    return count


def _unpack_dims(fp, f):
    c = _unpack_dims_var(fp, f.ret) + _unpack_dims_var(fp, f.args)
    if c:
        fp.write("\n")


# ===================================================================
# Check dim consistency (oct-file version)
# ===================================================================

def _check_dims(fp, args):
    for v in args:
        if (v.iospec != 'o' and is_array(v.tinfo) and
                v.qual and v.qual.args):
            a = v.qual.args
            if len(a) > 1:
                fp.write(f"    if (args({v.input_label}).rows() != dim{a[0].input_label}_ ||\n"
                       f"        args({v.input_label}).columns() != dim{a[1].input_label}_) {{\n"
                       f"        mw_err_txt_ = \"Bad argument size: {v.name}\";\n"
                       f"        goto mw_err_label;\n"
                       f"    }}\n\n")
            else:
                fp.write(f"    if (args({v.input_label}).numel() != dim{a[0].input_label}_) {{\n"
                       f"        mw_err_txt_ = \"Bad argument size: {v.name}\";"
                       f"        goto mw_err_label;\n"
                       f"    }}\n\n")


# ===================================================================
# Unpack inputs (oct-file version)
# ===================================================================

def _cast_get_p(fp, ctx, basetype, input_label):
    fp.write(f"    in{input_label}_ = ")
    if basetype not in ctx.class_decls:
        fp.write(f"({basetype}*) mwOctGetP(args({input_label}), \"{basetype}:%p\", &mw_err_txt_);\n")
    else:
        fp.write(f"mwOctGetP_{basetype}(args({input_label}), &mw_err_txt_);\n")
    fp.write("    if (mw_err_txt_)\n"
           "        goto mw_err_label;\n\n")


def _complex_matrix_info(v):
    """For complex array types, return (matrix_type, array_getter, type_check).
    Returns None if not a complex array type."""
    if not complex_tinfo(v):
        return None
    if v.tinfo in (VT.zarray,):
        return ("ComplexMatrix", "complex_matrix_value", "is_complex_type")
    if v.tinfo in (VT.carray,):
        return ("FloatComplexMatrix", "float_complex_matrix_value", "is_single_type")
    return None


def _unpack_input_array(fp, v):
    il = v.input_label
    bt = v.basetype
    tp = _oct_type_props(bt)

    fp.write(f"    if (args({il}).numel() != 0) {{\n")

    zinfo = _complex_matrix_info(v)
    if zinfo:
        # Complex array: use ComplexMatrix/FloatComplexMatrix
        mat_type, getter, checker = zinfo
        fp.write(f"        if (!args({il}).{checker}()) {{\n"
               f"            mw_err_txt_ = \"Invalid array argument, {checker} expected\";\n"
               f"            goto mw_err_label;\n"
               f"        }}\n")
        fp.write(f"        mat_in{il}_ = args({il}).{getter}();\n")
        if v.iospec == 'i':
            fp.write(f"        in{il}_ = ({bt}*) mat_in{il}_.data();\n")
        else:
            fp.write(f"        in{il}_ = ({bt}*) mat_in{il}_.rwdata();\n")
    elif bt in OCT_TYPE_PROPS:
        # Known scalar types: type check + matrix_value
        fp.write(f"        if (!args({il}).{tp.type_check}()) {{\n"
               f"            mw_err_txt_ = \"Invalid array argument, {tp.type_check} expected\";\n"
               f"            goto mw_err_label;\n"
               f"        }}\n")
        if v.iospec == 'i':
            fp.write(f"        mat_in{il}_ = args({il}).{tp.array_getter}();\n")
            fp.write(f"        in{il}_ = ({bt}*) mat_in{il}_.data();\n")
        else:
            fp.write(f"        mat_in{il}_ = args({il}).{tp.array_getter}();\n")
            fp.write(f"        in{il}_ = ({bt}*) mat_in{il}_.rwdata();\n")
    else:
        # Unknown types: copy through double matrix
        fp.write(f"        Matrix mat_in{il}_ = args({il}).matrix_value();\n")
        fp.write(f"        octave_idx_type len_in{il}_ = mat_in{il}_.numel();\n")
        fp.write(f"        in{il}_ = new {bt}[len_in{il}_];\n")
        fp.write(f"        const double* src_in{il}_ = mat_in{il}_.data();\n")
        fp.write(f"        for (octave_idx_type i_ = 0; i_ < len_in{il}_; ++i_)\n")
        fp.write(f"            in{il}_[i_] = ({bt}) src_in{il}_[i_];\n")

    fp.write(f"    }} else\n"
           f"        in{il}_ = NULL;\n")
    fp.write("\n")


def _unpack_input_string(fp, v):
    il = v.input_label
    if not (v.qual and v.qual.args):
        fp.write(f"    in{il}_ = mwOctGetString(args({il}), &mw_err_txt_);\n"
               f"    if (mw_err_txt_)\n"
               f"        goto mw_err_label;\n")
    else:
        sz = _alloc_size_expr(v.qual.args)
        fp.write(f"    in{il}_ = new char[{sz}];\n")
        fp.write(f"    {{\n")
        fp.write(f"        std::string s_ = args({il}).string_value();\n")
        fp.write(f"        strncpy(in{il}_, s_.c_str(), {sz});\n")
        fp.write(f"        in{il}_[{sz}-1] = '\\0';\n")
        fp.write(f"    }}\n")
    fp.write("\n")


def _unpack_inputs_var(fp, ctx, args):
    for v in args:
        if v.iospec == 'o':
            continue
        if is_obj(v.tinfo):
            _cast_get_p(fp, ctx, v.basetype, v.input_label)
        elif is_array(v.tinfo):
            _unpack_input_array(fp, v)
        elif v.tinfo in (VT.scalar, VT.r_scalar, VT.p_scalar):
            il = v.input_label
            bt = v.basetype
            tp = _oct_type_props(bt)
            if bt == "char":
                fp.write(f"    in{il}_ = ({bt}) mwOctGetScalar_char(args({il}), &mw_err_txt_);\n")
            elif bt == "float":
                fp.write(f"    in{il}_ = ({bt}) mwOctGetScalar_single(args({il}), &mw_err_txt_);\n")
            else:
                fp.write(f"    in{il}_ = ({bt}) mwOctGetScalar(args({il}), &mw_err_txt_);\n")
            fp.write(f"    if (mw_err_txt_)\n"
                   f"        goto mw_err_label;\n")
            if bt != "char":
                fp.write("\n")
        elif v.tinfo in (VT.cscalar, VT.zscalar,
                         VT.r_cscalar, VT.r_zscalar,
                         VT.p_cscalar, VT.p_zscalar):
            il = v.input_label
            bt = v.basetype
            tp = _oct_type_props(bt)
            # For complex scalars, extract via complex_value()
            if bt == "fcomplex":
                fp.write(f"    in{il}_ = ({bt}) args({il}).float_complex_value();\n\n")
            else:
                fp.write(f"    in{il}_ = ({bt}) args({il}).complex_value();\n\n")
        elif v.tinfo == VT.string:
            _unpack_input_string(fp, v)
        elif v.tinfo == VT.mx:
            fp.write(f"    in{v.input_label}_ = args({v.input_label});\n\n")


def _unpack_inputs(fp, ctx, f):
    if f.thisv:
        _cast_get_p(fp, ctx, f.classv, 0)
    _unpack_inputs_var(fp, ctx, f.args)


# ===================================================================
# Null-check objects/this
# ===================================================================

def _check_inputs(fp, args):
    for v in args:
        if v.iospec != 'o' and v.tinfo in (VT.obj, VT.r_obj):
            fp.write(f"    if (!in{v.input_label}_) {{\n"
                   f"        mw_err_txt_ = \"Argument {v.name} cannot be null\";\n"
                   f"        goto mw_err_label;\n"
                   f"    }}\n")


# ===================================================================
# Allocate outputs (oct-file version)
# ===================================================================

def _alloc_output(fp, ctx, args, return_flag):
    for v in args:
        if v.iospec == 'o':
            if is_array(v.tinfo):
                fp.write(f"    out{v.output_label}_ = new {v.basetype}[{_alloc_size_expr(v.qual.args)}];\n")
            elif v.tinfo == VT.rarray:
                fp.write(f"    out{v.output_label}_ = ({v.basetype}*) NULL;\n")
            elif v.tinfo == VT.string:
                fp.write(f"    out{v.output_label}_ = new char[{_alloc_size_expr(v.qual.args)}];\n")


def _alloc_outputs(fp, ctx, f):
    if not nullable_return(f):
        _alloc_output(fp, ctx, f.ret, True)
    _alloc_output(fp, ctx, f.args, False)


# ===================================================================
# Make the call (shared logic, with oct-file tweaks)
# ===================================================================

def _make_call_args(fp, args, first):
    for v in args:
        if not first:
            fp.write(", ")
        n = vname(v)
        if v.tinfo in (VT.obj, VT.r_obj):
            fp.write(f"*{n}")
        elif v.tinfo == VT.mx and v.iospec == 'o':
            # Output mxArray: pass pointer to retval slot
            fp.write(f"&retval_mx{v.output_label}_")
        elif v.tinfo in (VT.p_scalar, VT.p_cscalar, VT.p_zscalar):
            fp.write(f"&{n}")
        elif v.tinfo == VT.const:
            fp.write(v.name)
        else:
            fp.write(n)
        first = False


def _make_call_expr(fp, f):
    """Write the function call expression (without assignment/semicolon)."""
    if f.thisv:
        fp.write("in0_->")
    if f.funcv == "new":
        fp.write(f"new {f.classv}(")
    else:
        if f.fort:
            fp.write("MWF77_")
        fp.write(f"{f.funcv}(")
    _make_call_args(fp, f.args, True)
    fp.write(")")


def _make_stmt(fp, ctx, f):
    if f.thisv:
        fp.write("    if (!in0_) {\n"
               "        mw_err_txt_ = \"Cannot dispatch to NULL\";\n"
               "        goto mw_err_label;\n"
               "    }\n")

    if ctx.mw_generate_catch:
        fp.write("    try {\n    ")

    if f.ret:
        v = f.ret[0]
        if v.tinfo == VT.obj:
            fp.write(f"    out0_ = new {v.basetype}(")
            _make_call_expr(fp, f)
            fp.write(");\n")
        elif is_array(v.tinfo):
            # For oct: return array via pointer, will be marshalled later
            # Use a temp to hold the returned pointer
            fp.write(f"    out0_ = ({v.basetype}*) ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo in (VT.scalar, VT.r_scalar, VT.cscalar, VT.r_cscalar, VT.zscalar, VT.r_zscalar):
            fp.write("    out0_ = ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo == VT.string:
            fp.write("    out0_ = (char*) ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo == VT.p_obj:
            fp.write("    out0_ = ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo in (VT.p_scalar, VT.p_cscalar, VT.p_zscalar):
            fp.write("    out0_ = *")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo == VT.mx:
            fp.write("    retval(0) = ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo == VT.r_obj:
            fp.write("    out0_ = &(")
            _make_call_expr(fp, f)
            fp.write(");\n")
    else:
        fp.write("    ")
        _make_call_expr(fp, f)
        fp.write(";\n")

    if ctx.mw_generate_catch:
        fp.write(f"    }} catch(...) {{\n"
               f"        mw_err_txt_ = \"Caught C++ exception from {f.funcv}\";\n"
               f"    }}\n"
               f"    if (mw_err_txt_)\n"
               f"        goto mw_err_label;\n")


# ===================================================================
# Marshal results (oct-file version)
# ===================================================================

def _marshal_array(fp, v):
    il = v.input_label
    ol = v.output_label
    bt = v.basetype
    n = vname(v)
    tp = _oct_type_props(bt)
    da = v.qual.args if v.qual else []

    # Determine effective matrix type for marshalling
    zinfo = _complex_matrix_info(v)
    if zinfo:
        eff_mat_type = zinfo[0]
        known_type = True
    elif bt in OCT_TYPE_PROPS:
        eff_mat_type = tp.matrix_type
        known_type = True
    else:
        eff_mat_type = "Matrix"
        known_type = False

    if v.tinfo == VT.rarray:
        fp.write(f"    if (out{ol}_ == NULL) {{\n")
        fp.write(f"        retval({ol}) = Matrix(0, 0);\n")
        fp.write(f"    }} else {{\n")
        ws = "        "
    else:
        ws = "    "

    if not da:
        # No dims — inout array: create matrix from original size
        if known_type:
            fp.write(f"{ws}{eff_mat_type} mat_out{ol}_(args({il}).rows(), args({il}).columns());\n")
            fp.write(f"{ws}std::memcpy(mat_out{ol}_.rwdata(), in{il}_, args({il}).numel()*sizeof({bt}));\n")
            fp.write(f"{ws}retval({ol}) = mat_out{ol}_;\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    octave_idx_type n_ = args({il}).numel();\n")
            fp.write(f"{ws}    Matrix mat_out{ol}_(args({il}).rows(), args({il}).columns());\n")
            fp.write(f"{ws}    double* dst_ = mat_out{ol}_.rwdata();\n")
            fp.write(f"{ws}    for (octave_idx_type i_ = 0; i_ < n_; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) in{il}_[i_];\n")
            fp.write(f"{ws}    retval({ol}) = mat_out{ol}_;\n")
            fp.write(f"{ws}}}\n")
    elif len(da) == 1:
        # 1D
        if known_type:
            fp.write(f"{ws}{eff_mat_type} mat_out{ol}_(dim{da[0].input_label}_, 1);\n")
            fp.write(f"{ws}std::memcpy(mat_out{ol}_.rwdata(), {n}, dim{da[0].input_label}_*sizeof({bt}));\n")
            fp.write(f"{ws}retval({ol}) = mat_out{ol}_;\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    Matrix mat_out{ol}_(dim{da[0].input_label}_, 1);\n")
            fp.write(f"{ws}    double* dst_ = mat_out{ol}_.rwdata();\n")
            fp.write(f"{ws}    for (octave_idx_type i_ = 0; i_ < dim{da[0].input_label}_; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) {n}[i_];\n")
            fp.write(f"{ws}    retval({ol}) = mat_out{ol}_;\n")
            fp.write(f"{ws}}}\n")
    elif len(da) == 2:
        # 2D
        if known_type:
            fp.write(f"{ws}{eff_mat_type} mat_out{ol}_(dim{da[0].input_label}_, dim{da[1].input_label}_);\n")
            fp.write(f"{ws}std::memcpy(mat_out{ol}_.rwdata(), {n}, dim{da[0].input_label}_*dim{da[1].input_label}_*sizeof({bt}));\n")
            fp.write(f"{ws}retval({ol}) = mat_out{ol}_;\n")
        else:
            sz = f"dim{da[0].input_label}_*dim{da[1].input_label}_"
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    Matrix mat_out{ol}_(dim{da[0].input_label}_, dim{da[1].input_label}_);\n")
            fp.write(f"{ws}    double* dst_ = mat_out{ol}_.rwdata();\n")
            fp.write(f"{ws}    for (octave_idx_type i_ = 0; i_ < {sz}; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) {n}[i_];\n")
            fp.write(f"{ws}    retval({ol}) = mat_out{ol}_;\n")
            fp.write(f"{ws}}}\n")
    else:
        # 3D+ — flatten to 1D
        sz = _alloc_size_expr(da)
        if known_type:
            fp.write(f"{ws}{eff_mat_type} mat_out{ol}_({sz}, 1);\n")
            fp.write(f"{ws}std::memcpy(mat_out{ol}_.rwdata(), {n}, ({sz})*sizeof({bt}));\n")
            fp.write(f"{ws}retval({ol}) = mat_out{ol}_;\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    Matrix mat_out{ol}_({sz}, 1);\n")
            fp.write(f"{ws}    double* dst_ = mat_out{ol}_.rwdata();\n")
            fp.write(f"{ws}    for (octave_idx_type i_ = 0; i_ < {sz}; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) {n}[i_];\n")
            fp.write(f"{ws}    retval({ol}) = mat_out{ol}_;\n")
            fp.write(f"{ws}}}\n")

    if v.tinfo == VT.rarray:
        fp.write("    }\n")


def _marshal_result(fp, ctx, v, return_flag):
    n = vname(v)
    ol = v.output_label
    bt = v.basetype

    if is_obj(v.tinfo):
        fp.write(f"    retval({ol}) = mwOctCreateP(out{ol}_, \"{bt}:%p\");\n")
    elif is_array(v.tinfo) or v.tinfo == VT.rarray:
        _marshal_array(fp, v)
    elif v.tinfo in (VT.scalar, VT.r_scalar, VT.p_scalar):
        fp.write(f"    retval({ol}) = octave_value((double) {n});\n")
    elif v.tinfo in (VT.cscalar, VT.zscalar,
                     VT.r_cscalar, VT.r_zscalar,
                     VT.p_cscalar, VT.p_zscalar):
        if bt == "fcomplex":
            fp.write(f"    retval({ol}) = octave_value(FloatComplex(real_{bt}({n}), imag_{bt}({n})));\n")
        else:
            fp.write(f"    retval({ol}) = octave_value(Complex(real_{bt}({n}), imag_{bt}({n})));\n")
    elif v.tinfo == VT.string:
        fp.write(f"    retval({ol}) = mwOctStrncpy({n});\n")
    elif v.tinfo == VT.mx:
        if v.iospec == 'o':
            fp.write(f"    retval({ol}) = retval_mx{ol}_;\n")


def _marshal_results_var(fp, ctx, vars, return_flag):
    for v in vars:
        if v.iospec != 'i':
            _marshal_result(fp, ctx, v, return_flag)


def _marshal_results(fp, ctx, f):
    if not nullable_return(f):
        _marshal_results_var(fp, ctx, f.ret, True)
    _marshal_results_var(fp, ctx, f.args, False)


# ===================================================================
# Dealloc (oct-file version — simpler, no mxFree)
# ===================================================================

def _dealloc_var(fp, ctx, vars, return_flag):
    for v in vars:
        if is_array(v.tinfo) or v.tinfo == VT.string:
            if v.iospec == 'o':
                fp.write(f"    if (out{v.output_label}_) delete[] out{v.output_label}_;\n")
            elif v.iospec == 'b':
                # Inout arrays backed by known Octave types don't need dealloc
                # (pointer into Matrix). Only dealloc for unknown types.
                bt = v.basetype
                zinfo = _complex_matrix_info(v)
                if bt not in OCT_TYPE_PROPS and not zinfo:
                    fp.write(f"    if (in{v.input_label}_)  delete[] in{v.input_label}_;\n")
            elif v.iospec == 'i':
                # Input-only: known types point into Matrix, no dealloc needed
                bt = v.basetype
                zinfo = _complex_matrix_info(v)
                if bt not in OCT_TYPE_PROPS and not zinfo:
                    fp.write(f"    if (in{v.input_label}_)  delete[] in{v.input_label}_;\n")


def _dealloc(fp, ctx, f):
    if not nullable_return(f):
        _dealloc_var(fp, ctx, f.ret, True)
    _dealloc_var(fp, ctx, f.args, False)


# ===================================================================
# Print a single oct-file stub
# ===================================================================

def _print_c_comment(fp, f):
    fp.write(f"/* ---- {f.fname}: {f.line} ----\n")
    fp.write(f" * {print_func(f)}")
    if f.same:
        fsame = f.same[0]
        fp.write(f" * Also at {fsame.fname}: {fsame.line}\n")
    fp.write(" */\n")


def _count_outputs(f):
    """Count the number of output slots needed for retval."""
    nout = 0
    if f.ret and not nullable_return(f):
        for v in f.ret:
            if v.output_label + 1 > nout:
                nout = v.output_label + 1
    for v in f.args:
        if v.iospec in ('o', 'b') and v.output_label + 1 > nout:
            nout = v.output_label + 1
    return nout


def _print_oct_stub(fp, ctx, f):
    _print_c_comment(fp, f)
    ids = id_string(ctx, f)
    fp.write(f"static const char* stubids{f.id}_ = \"{ids}\";\n\n")
    nout = _count_outputs(f)

    fp.write(f"static octave_value_list octStub{f.id}(const octave_value_list& args, int nargout)\n"
           f"{{\n"
           f"    octave_value_list retval;\n"
           f"    const char* mw_err_txt_ = 0;\n")
    if nout > 0:
        fp.write(f"    retval.resize({nout});\n")
    _declare_args(fp, f)
    _unpack_dims(fp, f)
    _check_dims(fp, f.args)
    _unpack_inputs(fp, ctx, f)
    _check_inputs(fp, f.args)
    _alloc_outputs(fp, ctx, f)
    _make_stmt(fp, ctx, f)
    _marshal_results(fp, ctx, f)
    fp.write("\nmw_err_label:\n")
    _dealloc(fp, ctx, f)
    fp.write("    if (mw_err_txt_)\n"
           "        error(\"%s\", mw_err_txt_);\n"
           "    return retval;\n"
           "}\n\n")


# ===================================================================
# Print all stubs, dispatch table, gateway
# ===================================================================

def _print_oct_stubs(fp, ctx, funcs):
    for f in funcs:
        _print_oct_stub(fp, ctx, f)


def _print_oct_stub_table(fp, funcs):
    id_to_stub = {}
    maxid = 0
    for fc in funcs:
        id_to_stub[fc.id] = fc.id
        if fc.id > maxid:
            maxid = fc.id
        for fsame in fc.same:
            id_to_stub[fsame.id] = fc.id
            if fsame.id > maxid:
                maxid = fsame.id

    if maxid <= 0:
        return

    fp.write("typedef octave_value_list (*octStubFunc_t)(const octave_value_list&, int);\n\n"
           "static octStubFunc_t mwStubs_[] = {\n"
           "    NULL")
    for i in range(1, maxid + 1):
        fp.write(",\n")
        if i in id_to_stub:
            fp.write(f"    octStub{id_to_stub[i]}")
        else:
            fp.write("    NULL")
    fp.write("\n};\n\n")
    fp.write(f"static int mwNumStubs_ = {maxid};\n\n")


def _print_oct_else_cases(fp, funcs):
    for fc in funcs:
        fp.write(f"    else if (id == stubids{fc.id}_)\n"
               f"        return octStub{fc.id}(sub_args, nargout);\n")
    fp.write("    else\n"
           "        error(\"Unknown identifier\");\n")


# ===================================================================
# Top-level: print_oct_init + print_oct_file
# ===================================================================

MWRAP_OCT_BANNER = (
    "/* --------------------------------------------------- */\n"
    "/* Automatically generated by mwrap (oct-file backend) */\n"
    "/* --------------------------------------------------- */\n\n"
)


def print_oct_init(fp, ctx, support_text):
    """Write the oct-file header: banner + runtime support + complex includes."""
    fp.write(MWRAP_OCT_BANNER)
    fp.write(support_text)
    fp.write("\n")
    # Oct-files always use C++ complex
    if ctx.mw_use_c99_complex or ctx.mw_use_cpp_complex:
        oct_cpp_complex(fp)


def print_oct_file(fp, ctx, funcs, octfunc):
    """Write the rest of the oct-file: getters, stubs, dispatch, gateway."""
    if ctx.mw_use_int32_t or ctx.mw_use_int64_t or ctx.mw_use_uint32_t or ctx.mw_use_uint64_t:
        fp.write("#include <stdint.h>\n\n")

    oct_casting_getters(fp, ctx)

    if has_fortran(funcs):
        oct_define_fnames(fp, funcs)
        oct_fortran_decls(fp, funcs)

    _print_oct_stubs(fp, ctx, funcs)
    _print_oct_stub_table(fp, funcs)

    # Gateway function
    fp.write(f"DEFUN_DLD({octfunc}, args, nargout, \"MWrap generated oct-file gateway\")\n")
    fp.write("{\n"
           "    if (args.length() == 0) {\n"
           "        octave_stdout << \"Oct-file installed\" << std::endl;\n"
           "        return octave_value_list();\n"
           "    }\n\n"
           "    /* Fast path: integer stub ID */\n"
           "    if (args(0).is_real_scalar()) {\n"
           "        int stub_id = args(0).int_value();\n"
           "        if (stub_id > 0 && stub_id <= mwNumStubs_ && mwStubs_[stub_id])\n"
           "            return mwStubs_[stub_id](args.slice(1, args.length()-1), nargout);\n"
           "        else\n"
           "            error(\"Unknown function ID %d\", stub_id);\n"
           "        return octave_value_list();\n"
           "    }\n\n"
           "    /* Slow path: string dispatch */\n"
           "    if (args(0).is_string()) {\n"
           "        std::string id = args(0).string_value();\n"
           "        octave_value_list sub_args = args.slice(1, args.length()-1);\n"
           "        if (false)\n"
           "            ; /* placeholder for else-if chain */\n")
    _print_oct_else_cases(fp, funcs)
    fp.write("    }\n\n"
           "    error(\"First argument must be function ID (integer or string)\");\n"
           "    return octave_value_list();\n"
           "}\n\n")
