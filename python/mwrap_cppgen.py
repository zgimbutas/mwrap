"""
mwrap_cppgen.py — MATLAB C++ MEX API code generator.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

C++ MEX API backend by Zydrunas Gimbutas (2026),
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
# Type property table for C++ MEX API backend
# ===================================================================

@dataclass(frozen=True)
class CppTypeProps:
    array_type_enum: str   # "ArrayType::DOUBLE", "ArrayType::SINGLE", etc.
    scalar_type: str       # "double", "float", "int32_t", etc.
    typed_array: str       # "TypedArray<double>", "TypedArray<float>", etc.

_DEFAULT_CPP_PROPS = CppTypeProps("ArrayType::DOUBLE", "double",
                                   "TypedArray<double>")

CPP_TYPE_PROPS = {
    "double":   CppTypeProps("ArrayType::DOUBLE",         "double",               "TypedArray<double>"),
    "float":    CppTypeProps("ArrayType::SINGLE",         "float",                "TypedArray<float>"),
    "int32_t":  CppTypeProps("ArrayType::INT32",          "int32_t",              "TypedArray<int32_t>"),
    "int64_t":  CppTypeProps("ArrayType::INT64",          "int64_t",              "TypedArray<int64_t>"),
    "uint32_t": CppTypeProps("ArrayType::UINT32",         "uint32_t",             "TypedArray<uint32_t>"),
    "uint64_t": CppTypeProps("ArrayType::UINT64",         "uint64_t",             "TypedArray<uint64_t>"),
    "dcomplex": CppTypeProps("ArrayType::COMPLEX_DOUBLE", "std::complex<double>", "TypedArray<std::complex<double>>"),
    "fcomplex": CppTypeProps("ArrayType::COMPLEX_SINGLE", "std::complex<float>",  "TypedArray<std::complex<float>>"),
    "char":     CppTypeProps("ArrayType::CHAR",           "char",                 "CharArray"),
}


def _cpp_type_props(name):
    return CPP_TYPE_PROPS.get(name, _DEFAULT_CPP_PROPS)


# ===================================================================
# Utility functions (shared with mwrap_octgen.py)
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
# Complex type definitions (always C++ for C++ MEX API)
# ===================================================================

def cpp_cpp_complex(fp):
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


def cpp_define_fnames(fp, funcs):
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


def _cpp_fortran_arg(fp, args):
    parts = []
    for v in args:
        parts.append(f"{v.basetype}*")
    fp.write(", ".join(parts))


def cpp_fortran_decls(fp, funcs):
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
        _cpp_fortran_arg(fp, fc.args)
        fp.write(");\n")
    fp.write("\n#ifdef __cplusplus\n"
           "} /* end extern C */\n"
           "#endif\n\n")


# ===================================================================
# Class polymorphism getters (C++ MEX API version)
# ===================================================================

def _cpp_casting_getter_type(fp, name):
    fp.write(f"    {name}* p_{name} = NULL;\n"
           f"    sscanf(pbuf, \"{name}:%p\", &p_{name});\n"
           f"    if (p_{name})\n"
           f"        return p_{name};\n\n")


def _cpp_casting_getter(fp, cname, inherits):
    fp.write(f"\nstatic {cname}* mwCppGetP_{cname}(const Array& a, const char** e)\n")
    fp.write("{\n"
           "    if (a.getType() == ArrayType::DOUBLE && a.getNumberOfElements() == 1) {\n"
           "        TypedArray<double> ta = a;\n"
           "        if (ta[0] == 0)\n"
           "            return NULL;\n"
           "    }\n"
           "    if (a.getType() != ArrayType::CHAR) {\n"
           "        *e = \"Invalid pointer\";\n"
           "        return NULL;\n"
           "    }\n"
           "    char pbuf[128];\n"
           "    CharArray ca = a;\n"
           "    std::string s = ca.toAscii();\n"
           "    strncpy(pbuf, s.c_str(), sizeof(pbuf)-1);\n"
           "    pbuf[sizeof(pbuf)-1] = '\\0';\n\n")
    _cpp_casting_getter_type(fp, cname)
    for name in inherits:
        _cpp_casting_getter_type(fp, name)
    fp.write(f"    *e = \"Invalid pointer to {cname}\";\n"
           f"    return NULL;\n"
           f"}}\n\n")


def cpp_casting_getters(fp, ctx):
    for parent in sorted(ctx.class_decls.keys()):
        _cpp_casting_getter(fp, parent, ctx.class_decls[parent])


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
        return "Array"
    assert False, f"Unknown tinfo {v.tinfo} for {v.name}"


def _declare_in_args(fp, args):
    for v in args:
        if v.iospec != 'o' and v.tinfo != VT.const:
            tb = _declare_type(v)
            if is_array(v.tinfo) or is_obj(v.tinfo) or v.tinfo == VT.string:
                fp.write(f"    {tb:10s}  in{v.input_label}_ =0; /* {v.name:10s} */\n")
                # For arrays, declare storage at function scope
                if is_array(v.tinfo):
                    bt = v.basetype
                    tp = _cpp_type_props(bt)
                    if v.nocopy and v.iospec != 'b' and bt in CPP_TYPE_PROPS:
                        # Nocopy: declare unique_ptr<TypedArray> handle (ref-counted, keeps data alive)
                        # TypedArray default ctor is deleted in R2024b+, so wrap in unique_ptr
                        zinfo = _complex_array_info(v)
                        if zinfo:
                            _, _, ta = zinfo
                            # Also declare vec_ for real-to-complex fallback
                            fp.write(f"    std::unique_ptr<{ta}>  ta_nc_in{v.input_label}_;\n")
                            fp.write(f"    std::vector<{tp.scalar_type}>  vec_in{v.input_label}_;\n")
                        else:
                            ta = tp.typed_array
                            fp.write(f"    std::unique_ptr<{ta}>  ta_nc_in{v.input_label}_;\n")
                    else:
                        fp.write(f"    std::vector<{tp.scalar_type}>  vec_in{v.input_label}_;\n")
            elif v.tinfo == VT.mx:
                fp.write(f"    {tb:10s}  in{v.input_label}_;    /* {v.name:10s} */\n")
            else:
                fp.write(f"    {tb:10s}  in{v.input_label}_;    /* {v.name:10s} */\n")


def _declare_out_args(fp, args):
    for v in args:
        if v.iospec == 'o':
            if v.tinfo == VT.mx:
                fp.write(f"    Array      retval_mx{v.output_label}_;   /* {v.name:10s} */\n")
                continue
            tb = _declare_type(v)
            if is_array(v.tinfo) or is_obj(v.tinfo) or v.tinfo == VT.string:
                fp.write(f"    {tb:10s}  out{v.output_label}_=0; /* {v.name:10s} */\n")
                # Nocopy output: declare buffer_ptr_t at function scope
                if v.nocopy and v.iospec == 'o' and is_array(v.tinfo):
                    bt = v.basetype
                    tp = _cpp_type_props(bt)
                    zinfo = _complex_array_info(v)
                    if zinfo:
                        _, st, _ = zinfo
                    else:
                        st = tp.scalar_type
                    fp.write(f"    buffer_ptr_t<{st}>  buf_out{v.output_label}_{{nullptr, nullptr}};\n")
            else:
                fp.write(f"    {tb:10s}  out{v.output_label}_;   /* {v.name:10s} */\n")


def _declare_dim_args_expr(fp, args):
    for e in args:
        fp.write(f"    {'size_t':10s}  dim{e.input_label}_;   /* {e.value:10s} */\n")


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
# Unpack dims (C++ MEX API version)
# ===================================================================

def _unpack_dims_expr(fp, args):
    count = 0
    for e in args:
        fp.write(f"    dim{e.input_label}_ = (size_t) mwCppGetScalar(args[{e.input_label}], &mw_err_txt_);\n")
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
# Check dim consistency (C++ MEX API version)
# ===================================================================

def _check_dims(fp, args):
    for v in args:
        if (v.iospec != 'o' and (not v.nocopy or v.iospec == 'b') and
                is_array(v.tinfo) and v.qual and v.qual.args):
            a = v.qual.args
            if len(a) > 1:
                fp.write(f"    if (args[{v.input_label}].getDimensions()[0] != dim{a[0].input_label}_ ||\n"
                       f"        args[{v.input_label}].getDimensions()[1] != dim{a[1].input_label}_) {{\n"
                       f"        mw_err_txt_ = \"Bad argument size: {v.name}\";\n"
                       f"        goto mw_err_label;\n"
                       f"    }}\n\n")
            else:
                fp.write(f"    if (args[{v.input_label}].getNumberOfElements() != dim{a[0].input_label}_) {{\n"
                       f"        mw_err_txt_ = \"Bad argument size: {v.name}\";"
                       f"        goto mw_err_label;\n"
                       f"    }}\n\n")


# ===================================================================
# Unpack inputs (C++ MEX API version)
# ===================================================================

def _cast_get_p(fp, ctx, basetype, input_label):
    fp.write(f"    in{input_label}_ = ")
    if basetype not in ctx.class_decls:
        fp.write(f"({basetype}*) mwCppGetP(args[{input_label}], \"{basetype}:%p\", &mw_err_txt_);\n")
    else:
        fp.write(f"mwCppGetP_{basetype}(args[{input_label}], &mw_err_txt_);\n")
    fp.write("    if (mw_err_txt_)\n"
           "        goto mw_err_label;\n\n")


def _complex_array_info(v):
    """For complex array types, return (array_type_enum, scalar_type, typed_array).
    Returns None if not a complex array type."""
    if not complex_tinfo(v):
        return None
    if v.tinfo in (VT.zarray,):
        return ("ArrayType::COMPLEX_DOUBLE", "std::complex<double>", "TypedArray<std::complex<double>>")
    if v.tinfo in (VT.carray,):
        return ("ArrayType::COMPLEX_SINGLE", "std::complex<float>", "TypedArray<std::complex<float>>")
    return None


def _unpack_input_array(fp, v):
    il = v.input_label
    bt = v.basetype
    tp = _cpp_type_props(bt)

    # --- Nocopy path (disabled for inout — modifying input in-place is unsafe) ---
    if v.nocopy and v.iospec != 'b' and bt in CPP_TYPE_PROPS:
        zinfo = _complex_array_info(v)
        if zinfo:
            ate, st, ta = zinfo
            # Auto-promote real to complex: fall back to copy path
            if v.tinfo in (VT.zarray,):
                real_ate = "ArrayType::DOUBLE"
                real_ta = "TypedArray<double>"
            else:
                real_ate = "ArrayType::SINGLE"
                real_ta = "TypedArray<float>"
            fp.write(f"    if (args[{il}].getNumberOfElements() != 0) {{\n")
            fp.write(f"        if (args[{il}].getType() == {ate}) {{\n")
            fp.write(f"            ta_nc_in{il}_ = std::make_unique<{ta}>(args[{il}]);\n")
            fp.write(f"            in{il}_ = ({bt}*) &(*ta_nc_in{il}_->begin());\n")
            fp.write(f"        }} else if (args[{il}].getType() == {real_ate}) {{\n")
            fp.write(f"            {real_ta} ta_real_ = args[{il}];\n")
            fp.write(f"            vec_in{il}_.reserve(ta_real_.getNumberOfElements());\n")
            fp.write(f"            for (auto v_ : ta_real_) vec_in{il}_.push_back({st}(v_, 0));\n")
            fp.write(f"            in{il}_ = ({bt}*) vec_in{il}_.data();\n")
            fp.write(f"        }} else {{\n"
                   f"            mw_err_txt_ = \"Invalid array argument, numeric type expected\";\n"
                   f"            goto mw_err_label;\n"
                   f"        }}\n")
        else:
            ate = tp.array_type_enum
            st = tp.scalar_type
            ta = tp.typed_array
            fp.write(f"    if (args[{il}].getNumberOfElements() != 0) {{\n")
            fp.write(f"        if (args[{il}].getType() != {ate}) {{\n"
                   f"            mw_err_txt_ = \"Invalid array argument, {ate} expected\";\n"
                   f"            goto mw_err_label;\n"
                   f"        }}\n")
            fp.write(f"        ta_nc_in{il}_ = std::make_unique<{ta}>(args[{il}]);\n")
            fp.write(f"        in{il}_ = ({bt}*) &(*ta_nc_in{il}_->begin());\n")
        fp.write(f"    }} else\n"
               f"        in{il}_ = NULL;\n\n")
        return

    # --- Regular (copy) path ---
    fp.write(f"    if (args[{il}].getNumberOfElements() != 0) {{\n")

    zinfo = _complex_array_info(v)
    if zinfo:
        # Complex array: use TypedArray<std::complex<T>>
        # Auto-promote real to complex when needed.  MATLAB tracks the
        # complex flag, but user code may still pass a real array where
        # complex is expected (e.g. zeros(n) as placeholder).
        ate, st, ta = zinfo
        if v.tinfo in (VT.zarray,):
            real_ate = "ArrayType::DOUBLE"
            real_ta = "TypedArray<double>"
        else:
            real_ate = "ArrayType::SINGLE"
            real_ta = "TypedArray<float>"
        fp.write(f"        if (args[{il}].getType() == {ate}) {{\n")
        fp.write(f"            {ta} ta_in{il}_ = args[{il}];\n")
        fp.write(f"            vec_in{il}_.assign(ta_in{il}_.begin(), ta_in{il}_.end());\n")
        fp.write(f"        }} else if (args[{il}].getType() == {real_ate}) {{\n")
        fp.write(f"            {real_ta} ta_real_ = args[{il}];\n")
        fp.write(f"            vec_in{il}_.reserve(ta_real_.getNumberOfElements());\n")
        fp.write(f"            for (auto v_ : ta_real_) vec_in{il}_.push_back({st}(v_, 0));\n")
        fp.write(f"        }} else {{\n"
               f"            mw_err_txt_ = \"Invalid array argument, numeric type expected\";\n"
               f"            goto mw_err_label;\n"
               f"        }}\n")
        fp.write(f"        in{il}_ = ({bt}*) vec_in{il}_.data();\n")
    elif bt in CPP_TYPE_PROPS:
        # Known scalar types: type check + copy via iterators
        fp.write(f"        if (args[{il}].getType() != {tp.array_type_enum}) {{\n"
               f"            mw_err_txt_ = \"Invalid array argument, {tp.array_type_enum} expected\";\n"
               f"            goto mw_err_label;\n"
               f"        }}\n")
        if bt == "char":
            # CharArray needs special handling
            fp.write(f"        CharArray ca_in{il}_ = args[{il}];\n")
            fp.write(f"        std::string s_in{il}_ = ca_in{il}_.toAscii();\n")
            fp.write(f"        vec_in{il}_.assign(s_in{il}_.begin(), s_in{il}_.end());\n")
        else:
            fp.write(f"        {tp.typed_array} ta_in{il}_ = args[{il}];\n")
            fp.write(f"        vec_in{il}_.assign(ta_in{il}_.begin(), ta_in{il}_.end());\n")
        fp.write(f"        in{il}_ = ({bt}*) vec_in{il}_.data();\n")
    else:
        # Unknown types: copy through double array
        fp.write(f"        TypedArray<double> ta_in{il}_ = args[{il}];\n")
        fp.write(f"        size_t len_in{il}_ = ta_in{il}_.getNumberOfElements();\n")
        fp.write(f"        in{il}_ = new {bt}[len_in{il}_];\n")
        fp.write(f"        size_t idx_in{il}_ = 0;\n")
        fp.write(f"        for (auto elem_ : ta_in{il}_)\n")
        fp.write(f"            in{il}_[idx_in{il}_++] = ({bt}) elem_;\n")

    fp.write(f"    }} else\n"
           f"        in{il}_ = NULL;\n")
    fp.write("\n")


def _unpack_input_string(fp, v):
    il = v.input_label
    if not (v.qual and v.qual.args):
        fp.write(f"    in{il}_ = mwCppGetString(args[{il}], &mw_err_txt_);\n"
               f"    if (mw_err_txt_)\n"
               f"        goto mw_err_label;\n")
    else:
        sz = _alloc_size_expr(v.qual.args)
        fp.write(f"    in{il}_ = new char[{sz}];\n")
        fp.write(f"    {{\n")
        fp.write(f"        CharArray ca_ = args[{il}];\n")
        fp.write(f"        std::string s_ = ca_.toAscii();\n")
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
            if bt == "char":
                fp.write(f"    in{il}_ = ({bt}) mwCppGetScalar_char(args[{il}], &mw_err_txt_);\n")
            elif bt == "float":
                fp.write(f"    in{il}_ = ({bt}) mwCppGetScalar_single(args[{il}], &mw_err_txt_);\n")
            else:
                fp.write(f"    in{il}_ = ({bt}) mwCppGetScalar(args[{il}], &mw_err_txt_);\n")
            fp.write(f"    if (mw_err_txt_)\n"
                   f"        goto mw_err_label;\n")
            if bt != "char":
                fp.write("\n")
        elif v.tinfo in (VT.cscalar, VT.zscalar,
                         VT.r_cscalar, VT.r_zscalar,
                         VT.p_cscalar, VT.p_zscalar):
            il = v.input_label
            bt = v.basetype
            # For complex scalars, extract via TypedArray<std::complex<T>>
            if bt == "fcomplex":
                fp.write(f"    {{\n")
                fp.write(f"        TypedArray<std::complex<float>> ta_ = args[{il}];\n")
                fp.write(f"        in{il}_ = ({bt}) ta_[0];\n")
                fp.write(f"    }}\n\n")
            else:
                fp.write(f"    {{\n")
                fp.write(f"        TypedArray<std::complex<double>> ta_ = args[{il}];\n")
                fp.write(f"        in{il}_ = ({bt}) ta_[0];\n")
                fp.write(f"    }}\n\n")
        elif v.tinfo == VT.string:
            _unpack_input_string(fp, v)
        elif v.tinfo == VT.mx:
            fp.write(f"    in{v.input_label}_ = args[{v.input_label}];\n\n")


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
# Allocate outputs (C++ MEX API version)
# ===================================================================

def _alloc_output(fp, ctx, args, return_flag):
    for v in args:
        if v.nocopy and v.iospec == 'o':
            # Nocopy output: allocate MATLAB buffer directly
            if is_array(v.tinfo) and v.basetype in CPP_TYPE_PROPS:
                bt = v.basetype
                tp = _cpp_type_props(bt)
                zinfo = _complex_array_info(v)
                if zinfo:
                    _, st, _ = zinfo
                else:
                    st = tp.scalar_type
                sz = _alloc_size_expr(v.qual.args)
                fp.write(f"    buf_out{v.output_label}_ = factory.createBuffer<{st}>({sz});\n")
                fp.write(f"    out{v.output_label}_ = ({bt}*) buf_out{v.output_label}_.get();\n")
            elif is_array(v.tinfo):
                # Unknown type: fall back to regular alloc
                fp.write(f"    out{v.output_label}_ = new {v.basetype}[{_alloc_size_expr(v.qual.args)}];\n")
        elif not v.nocopy and v.iospec == 'o':
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
# Make the call (shared logic, with C++ MEX API tweaks)
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
            fp.write("    retval[0] = ")
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
# Marshal results (C++ MEX API version)
# ===================================================================

def _marshal_array(fp, v):
    il = v.input_label
    ol = v.output_label
    bt = v.basetype
    n = vname(v)
    tp = _cpp_type_props(bt)
    da = v.qual.args if v.qual else []

    # --- Nocopy output: wrap pre-allocated buffer into Array ---
    if v.nocopy and v.iospec == 'o' and bt in CPP_TYPE_PROPS:
        zinfo = _complex_array_info(v)
        if zinfo:
            _, st, _ = zinfo
        else:
            st = tp.scalar_type
        if not da:
            # Inout-like (no explicit dims): use original dimensions
            fp.write(f"    {{\n")
            fp.write(f"        size_t nr_ = args[{il}].getDimensions()[0];\n")
            fp.write(f"        size_t nc_ = args[{il}].getDimensions()[1];\n")
            fp.write(f"        retval[{ol}] = factory.createArrayFromBuffer({{nr_, nc_}}, std::move(buf_out{ol}_));\n")
            fp.write(f"    }}\n")
        elif len(da) == 1:
            fp.write(f"    retval[{ol}] = factory.createArrayFromBuffer({{dim{da[0].input_label}_, 1}}, std::move(buf_out{ol}_));\n")
        elif len(da) == 2:
            fp.write(f"    retval[{ol}] = factory.createArrayFromBuffer({{dim{da[0].input_label}_, dim{da[1].input_label}_}}, std::move(buf_out{ol}_));\n")
        else:
            sz = _alloc_size_expr(da)
            fp.write(f"    retval[{ol}] = factory.createArrayFromBuffer({{({sz}), 1}}, std::move(buf_out{ol}_));\n")
        return


    # Determine effective type info for marshalling
    zinfo = _complex_array_info(v)
    if zinfo:
        ate, st, ta = zinfo
        known_type = True
    elif bt in CPP_TYPE_PROPS:
        ate = tp.array_type_enum
        st = tp.scalar_type
        ta = tp.typed_array
        known_type = True
    else:
        ate = "ArrayType::DOUBLE"
        st = "double"
        ta = "TypedArray<double>"
        known_type = False

    if v.tinfo == VT.rarray:
        fp.write(f"    if (out{ol}_ == NULL) {{\n")
        fp.write(f"        retval[{ol}] = factory.createArray<double>({{0, 0}});\n")
        fp.write(f"    }} else {{\n")
        ws = "        "
    else:
        ws = "    "

    if not da:
        # No dims — inout array: create from original size
        if known_type:
            if bt == "char":
                # char arrays -> create CharArray from string
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    size_t n_ = args[{il}].getNumberOfElements();\n")
                fp.write(f"{ws}    std::string s_(in{il}_, n_);\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createCharArray(s_);\n")
                fp.write(f"{ws}}}\n")
            else:
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    size_t nr_ = args[{il}].getDimensions()[0];\n")
                fp.write(f"{ws}    size_t nc_ = args[{il}].getDimensions()[1];\n")
                fp.write(f"{ws}    auto buf_ = factory.createBuffer<{st}>(nr_*nc_);\n")
                fp.write(f"{ws}    std::memcpy(buf_.get(), in{il}_, nr_*nc_*sizeof({bt}));\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{nr_, nc_}}, std::move(buf_));\n")
                fp.write(f"{ws}}}\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    size_t n_ = args[{il}].getNumberOfElements();\n")
            fp.write(f"{ws}    size_t nr_ = args[{il}].getDimensions()[0];\n")
            fp.write(f"{ws}    size_t nc_ = args[{il}].getDimensions()[1];\n")
            fp.write(f"{ws}    auto buf_ = factory.createBuffer<double>(n_);\n")
            fp.write(f"{ws}    double* dst_ = buf_.get();\n")
            fp.write(f"{ws}    for (size_t i_ = 0; i_ < n_; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) in{il}_[i_];\n")
            fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{nr_, nc_}}, std::move(buf_));\n")
            fp.write(f"{ws}}}\n")
    elif len(da) == 1:
        # 1D
        if known_type:
            if bt == "char":
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    std::string s_({n}, dim{da[0].input_label}_);\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createCharArray(s_);\n")
                fp.write(f"{ws}}}\n")
            else:
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    auto buf_ = factory.createBuffer<{st}>(dim{da[0].input_label}_);\n")
                fp.write(f"{ws}    std::memcpy(buf_.get(), {n}, dim{da[0].input_label}_*sizeof({bt}));\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{dim{da[0].input_label}_, 1}}, std::move(buf_));\n")
                fp.write(f"{ws}}}\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    auto buf_ = factory.createBuffer<double>(dim{da[0].input_label}_);\n")
            fp.write(f"{ws}    double* dst_ = buf_.get();\n")
            fp.write(f"{ws}    for (size_t i_ = 0; i_ < dim{da[0].input_label}_; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) {n}[i_];\n")
            fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{dim{da[0].input_label}_, 1}}, std::move(buf_));\n")
            fp.write(f"{ws}}}\n")
    elif len(da) == 2:
        # 2D
        sz = f"dim{da[0].input_label}_*dim{da[1].input_label}_"
        if known_type:
            if bt == "char":
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    std::string s_({n}, {sz});\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createCharArray(s_);\n")
                fp.write(f"{ws}}}\n")
            else:
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    auto buf_ = factory.createBuffer<{st}>({sz});\n")
                fp.write(f"{ws}    std::memcpy(buf_.get(), {n}, ({sz})*sizeof({bt}));\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{dim{da[0].input_label}_, dim{da[1].input_label}_}}, std::move(buf_));\n")
                fp.write(f"{ws}}}\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    auto buf_ = factory.createBuffer<double>({sz});\n")
            fp.write(f"{ws}    double* dst_ = buf_.get();\n")
            fp.write(f"{ws}    for (size_t i_ = 0; i_ < {sz}; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) {n}[i_];\n")
            fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{dim{da[0].input_label}_, dim{da[1].input_label}_}}, std::move(buf_));\n")
            fp.write(f"{ws}}}\n")
    else:
        # 3D+ — flatten to 1D
        sz = _alloc_size_expr(da)
        if known_type:
            if bt == "char":
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    std::string s_({n}, {sz});\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createCharArray(s_);\n")
                fp.write(f"{ws}}}\n")
            else:
                fp.write(f"{ws}{{\n")
                fp.write(f"{ws}    auto buf_ = factory.createBuffer<{st}>({sz});\n")
                fp.write(f"{ws}    std::memcpy(buf_.get(), {n}, ({sz})*sizeof({bt}));\n")
                fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{({sz}), 1}}, std::move(buf_));\n")
                fp.write(f"{ws}}}\n")
        else:
            fp.write(f"{ws}{{\n")
            fp.write(f"{ws}    auto buf_ = factory.createBuffer<double>({sz});\n")
            fp.write(f"{ws}    double* dst_ = buf_.get();\n")
            fp.write(f"{ws}    for (size_t i_ = 0; i_ < {sz}; ++i_)\n")
            fp.write(f"{ws}        dst_[i_] = (double) {n}[i_];\n")
            fp.write(f"{ws}    retval[{ol}] = factory.createArrayFromBuffer({{({sz}), 1}}, std::move(buf_));\n")
            fp.write(f"{ws}}}\n")

    if v.tinfo == VT.rarray:
        fp.write("    }\n")


def _marshal_result(fp, ctx, v, return_flag):
    n = vname(v)
    ol = v.output_label
    bt = v.basetype

    if is_obj(v.tinfo):
        fp.write(f"    retval[{ol}] = mwCppCreateP(factory, out{ol}_, \"{bt}:%p\");\n")
    elif is_array(v.tinfo) or v.tinfo == VT.rarray:
        _marshal_array(fp, v)
    elif v.tinfo in (VT.scalar, VT.r_scalar, VT.p_scalar):
        fp.write(f"    retval[{ol}] = factory.createScalar<double>((double) {n});\n")
    elif v.tinfo in (VT.cscalar, VT.zscalar,
                     VT.r_cscalar, VT.r_zscalar,
                     VT.p_cscalar, VT.p_zscalar):
        if bt == "fcomplex":
            fp.write(f"    retval[{ol}] = factory.createScalar<std::complex<float>>(std::complex<float>(real_{bt}({n}), imag_{bt}({n})));\n")
        else:
            fp.write(f"    retval[{ol}] = factory.createScalar<std::complex<double>>(std::complex<double>(real_{bt}({n}), imag_{bt}({n})));\n")
    elif v.tinfo == VT.string:
        fp.write(f"    retval[{ol}] = mwCppStrncpy(factory, {n});\n")
    elif v.tinfo == VT.mx:
        if v.iospec == 'o':
            fp.write(f"    retval[{ol}] = retval_mx{ol}_;\n")


def _marshal_results_var(fp, ctx, vars, return_flag):
    for v in vars:
        if v.iospec != 'i':
            _marshal_result(fp, ctx, v, return_flag)


def _marshal_results(fp, ctx, f):
    if not nullable_return(f):
        _marshal_results_var(fp, ctx, f.ret, True)
    _marshal_results_var(fp, ctx, f.args, False)


# ===================================================================
# Dealloc (C++ MEX API version)
# ===================================================================

def _dealloc_var(fp, ctx, vars, return_flag):
    for v in vars:
        if is_array(v.tinfo) or v.tinfo == VT.string:
            if v.nocopy and v.iospec != 'b':
                # Nocopy: MATLAB owns the memory (TypedArray/buffer), no dealloc needed.
                # Exception: unknown types for nocopy output that fell back to new[]
                if v.iospec == 'o' and v.basetype not in CPP_TYPE_PROPS:
                    fp.write(f"    if (out{v.output_label}_) delete[] out{v.output_label}_;\n")
            elif v.iospec == 'o':
                fp.write(f"    if (out{v.output_label}_) delete[] out{v.output_label}_;\n")
            elif v.iospec == 'b':
                # Inout arrays backed by std::vector don't need dealloc.
                # Only dealloc for unknown types (allocated with new[]).
                bt = v.basetype
                zinfo = _complex_array_info(v)
                if bt not in CPP_TYPE_PROPS and not zinfo:
                    fp.write(f"    if (in{v.input_label}_)  delete[] in{v.input_label}_;\n")
            elif v.iospec == 'i':
                # Input-only: known types use std::vector, no dealloc needed.
                bt = v.basetype
                zinfo = _complex_array_info(v)
                if bt not in CPP_TYPE_PROPS and not zinfo:
                    fp.write(f"    if (in{v.input_label}_)  delete[] in{v.input_label}_;\n")


def _dealloc(fp, ctx, f):
    if not nullable_return(f):
        _dealloc_var(fp, ctx, f.ret, True)
    _dealloc_var(fp, ctx, f.args, False)


# ===================================================================
# Print a single C++ MEX API stub
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


def _print_cpp_stub(fp, ctx, f):
    _print_c_comment(fp, f)
    ids = id_string(ctx, f)
    fp.write(f"static const char* stubids{f.id}_ = \"{ids}\";\n\n")
    nout = _count_outputs(f)

    fp.write(f"static void cppStub{f.id}(ArrayFactory& factory,\n"
           f"    const std::vector<Array>& args, std::vector<Array>& retval, int nargout)\n"
           f"{{\n"
           f"    const char* mw_err_txt_ = 0;\n")
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
           "        throw std::runtime_error(mw_err_txt_);\n"
           "}\n\n")


# ===================================================================
# Print all stubs, dispatch table, gateway
# ===================================================================

def _print_cpp_stubs(fp, ctx, funcs):
    for f in funcs:
        _print_cpp_stub(fp, ctx, f)


def _print_cpp_stub_table(fp, funcs):
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

    fp.write("typedef void (*CppStubFunc_t)(ArrayFactory&, const std::vector<Array>&,\n"
           "                               std::vector<Array>&, int);\n\n"
           "static CppStubFunc_t mwStubs_[] = {\n"
           "    NULL")
    for i in range(1, maxid + 1):
        fp.write(",\n")
        if i in id_to_stub:
            fp.write(f"    cppStub{id_to_stub[i]}")
        else:
            fp.write("    NULL")
    fp.write("\n};\n\n")
    fp.write(f"static int mwNumStubs_ = {maxid};\n\n")


def _print_cpp_else_cases(fp, funcs):
    for fc in funcs:
        fp.write(f"        else if (id == stubids{fc.id}_)\n"
               f"            cppStub{fc.id}(factory_, sub_args, out, nargout);\n")
    fp.write("        else\n"
           "            throw std::runtime_error(\"Unknown identifier\");\n")


# ===================================================================
# Top-level: print_cpp_init + print_cpp_file
# ===================================================================

MWRAP_CPP_BANNER = (
    "/* --------------------------------------------------- */\n"
    "/* Automatically generated by mwrap (cppmex backend)    */\n"
    "/* --------------------------------------------------- */\n\n"
)


def print_cpp_init(fp, ctx, support_text):
    """Write the cppmex header: banner + runtime support + complex includes."""
    fp.write(MWRAP_CPP_BANNER)
    fp.write(support_text)
    fp.write("\n")
    # C++ MEX files always use C++ complex
    if ctx.mw_use_c99_complex or ctx.mw_use_cpp_complex:
        cpp_cpp_complex(fp)


def print_cpp_file(fp, ctx, funcs, cppfunc):
    """Write the rest of the cppmex file: getters, stubs, dispatch, gateway."""
    if ctx.mw_use_int32_t or ctx.mw_use_int64_t or ctx.mw_use_uint32_t or ctx.mw_use_uint64_t:
        fp.write("#include <stdint.h>\n\n")

    cpp_casting_getters(fp, ctx)

    if has_fortran(funcs):
        cpp_define_fnames(fp, funcs)
        cpp_fortran_decls(fp, funcs)

    _print_cpp_stubs(fp, ctx, funcs)
    _print_cpp_stub_table(fp, funcs)

    # Gateway class
    fp.write("class MexFunction : public matlab::mex::Function {\n"
           "    ArrayFactory factory_;\n"
           "public:\n"
           "    void operator()(matlab::mex::ArgumentList outputs,\n"
           "                    matlab::mex::ArgumentList inputs) {\n"
           "        int nargout = (int) outputs.size();\n\n"
           "        if (inputs.size() == 0) {\n")
    fp.write(f"            std::shared_ptr<matlab::engine::MATLABEngine> matlabPtr = getEngine();\n"
           f"            matlabPtr->feval(u\"fprintf\", 0,\n"
           f"                std::vector<Array>({{factory_.createScalar(u\"C++ MEX installed\\n\")}}));\n"
           f"            return;\n"
           f"        }}\n\n")
    fp.write("        /* Fast path: integer stub ID */\n"
           "        if (inputs[0].getType() == ArrayType::DOUBLE) {\n"
           "            TypedArray<double> ta = inputs[0];\n"
           "            int stub_id = (int) ta[0];\n"
           "            if (stub_id > 0 && stub_id <= mwNumStubs_ && mwStubs_[stub_id]) {\n"
           "                std::vector<Array> sub_args(inputs.begin()+1, inputs.end());\n"
           "                std::vector<Array> out(nargout > 0 ? nargout : 1);\n"
           "                mwStubs_[stub_id](factory_, sub_args, out, nargout);\n"
           "                for (size_t i = 0; i < out.size() && i < outputs.size(); ++i)\n"
           "                    outputs[i] = out[i];\n"
           "                return;\n"
           "            }\n"
           "        }\n\n"
           "        /* Slow path: string dispatch */\n"
           "        if (inputs[0].getType() == ArrayType::CHAR) {\n"
           "            CharArray ca = inputs[0];\n"
           "            std::string id = ca.toAscii();\n"
           "            std::vector<Array> sub_args(inputs.begin()+1, inputs.end());\n"
           "            int nargout = (int) outputs.size();\n"
           "            std::vector<Array> out(nargout > 0 ? nargout : 1);\n"
           "            if (false)\n"
           "                ; /* placeholder for else-if chain */\n")
    _print_cpp_else_cases(fp, funcs)
    fp.write("            for (size_t i = 0; i < out.size() && i < outputs.size(); ++i)\n"
           "                outputs[i] = out[i];\n"
           "            return;\n"
           "        }\n\n"
           "        throw std::runtime_error(\"First argument must be function ID (integer or string)\");\n"
           "    }\n"
           "};\n\n")
