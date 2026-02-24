"""
mwrap_cgen.py — C/MEX code generator.

Copyright (c) 2007-2008  David Bindel
See the file COPYING for copying permissions

Converted to Python by Zydrunas Gimbutas (2026),
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
# Type property table — single source of truth for type dispatch
# ===================================================================

@dataclass(frozen=True)
class TypeProps:
    mxclass: str             # "mxDOUBLE_CLASS", "mxSINGLE_CLASS", etc.
    accessor: str | None     # interleaved API accessor: "mxGetDoubles", etc.
    is_single: bool          # True → use _single copier variants
    scalar_getter: str       # "mxWrapGetScalar" / "_single" / "_char"
    scalar_class: str        # mxClass for scalar validation
    direct_input: bool = False  # True → use direct accessor for input-only arrays

_DEFAULT_PROPS = TypeProps("mxVOID_CLASS", None, False, "mxWrapGetScalar", "mxDOUBLE_CLASS")

TYPE_PROPS = {
    "double":   TypeProps("mxDOUBLE_CLASS", "mxGetDoubles",        False, "mxWrapGetScalar",        "mxDOUBLE_CLASS", True),
    "float":    TypeProps("mxSINGLE_CLASS", "mxGetSingles",        True,  "mxWrapGetScalar_single", "mxSINGLE_CLASS", True),
    "int32_t":  TypeProps("mxINT32_CLASS",  "mxGetInt32s",         False, "mxWrapGetScalar",        "mxDOUBLE_CLASS"),
    "int64_t":  TypeProps("mxINT64_CLASS",  "mxGetInt64s",         False, "mxWrapGetScalar",        "mxDOUBLE_CLASS"),
    "uint32_t": TypeProps("mxUINT32_CLASS", "mxGetUint32s",        False, "mxWrapGetScalar",        "mxDOUBLE_CLASS"),
    "uint64_t": TypeProps("mxUINT64_CLASS", "mxGetUint64s",        False, "mxWrapGetScalar",        "mxDOUBLE_CLASS"),
    "dcomplex": TypeProps("mxDOUBLE_CLASS", "mxGetComplexDoubles", False, "mxWrapGetScalar",        "mxDOUBLE_CLASS"),
    "fcomplex": TypeProps("mxSINGLE_CLASS", "mxGetComplexSingles", True,  "mxWrapGetScalar_single", "mxSINGLE_CLASS"),
    "char":     TypeProps("mxCHAR_CLASS",   None,                  False, "mxWrapGetScalar_char",   "mxCHAR_CLASS"),
}


def _type_props(name):
    return TYPE_PROPS.get(name, _DEFAULT_PROPS)


def _copier_suffix(bt):
    """Return 'single_' for float-precision types, '' otherwise."""
    return "single_" if _type_props(bt).is_single else ""


# ===================================================================
# Utility functions
# ===================================================================

def basetype_to_cucomplex(name):
    if name == "fcomplex": return "cuFloatComplex"
    if name == "dcomplex": return "cuDoubleComplex"
    return name


def basetype_to_mxclassid(name):
    return _type_props(name).mxclass


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


def _interleaved_branch(fp, interleaved, fallback):
    """Emit #if MX_HAS_INTERLEAVED_COMPLEX / #else / #endif block."""
    fp.write(f"#if MX_HAS_INTERLEAVED_COMPLEX\n{interleaved}#else\n{fallback}#endif\n")


# ===================================================================
# Complex type definitions
# ===================================================================

def mex_cpp_complex(fp):
    fp.write("#include <complex>\n\n"
           "typedef std::complex<double> dcomplex;\n"
           "#define real_dcomplex(z) std::real(z)\n"
           "#define imag_dcomplex(z) std::imag(z)\n"
           "#define setz_dcomplex(z,r,i)  *z = dcomplex(r,i)\n\n"
           "typedef std::complex<float> fcomplex;\n"
           "#define real_fcomplex(z) std::real(z)\n"
           "#define imag_fcomplex(z) std::imag(z)\n"
           "#define setz_fcomplex(z,r,i)  *z = fcomplex(r,i)\n\n")


def mex_c99_complex(fp):
    fp.write("#include <complex.h>\n\n"
           "typedef _Complex double dcomplex;\n"
           "#define real_dcomplex(z) creal(z)\n"
           "#define imag_dcomplex(z) cimag(z)\n"
           "#define setz_dcomplex(z,r,i)  *z = r + i*_Complex_I\n\n"
           "typedef _Complex float fcomplex;\n"
           "#define real_fcomplex(z) crealf(z)\n"
           "#define imag_fcomplex(z) cimagf(z)\n"
           "#define setz_fcomplex(z,r,i)  *z = r + i*_Complex_I\n\n")


def mex_gpucpp_complex(fp):
    fp.write("#include <cuComplex.h>\n\n")


# ===================================================================
# Copier instantiation
# ===================================================================

def _mex_define_copiers_type(fp, ctx, name):
    """Emit copier macro calls for one scalar type."""
    # Skip types not actually used
    if name == "int32_t"  and not ctx.mw_use_int32_t:  return
    if name == "int64_t"  and not ctx.mw_use_int64_t:  return
    if name == "uint32_t" and not ctx.mw_use_uint32_t: return
    if name == "uint64_t" and not ctx.mw_use_uint64_t: return
    if name == "ulong"    and not ctx.mw_use_ulong:    return
    if name == "uint"     and not ctx.mw_use_uint:     return
    if name == "ushort"   and not ctx.mw_use_ushort:   return
    if name == "uchar"    and not ctx.mw_use_uchar:    return

    fp.write(f"mxWrapGetArrayDef(mxWrapGetArray_{name}, {name})\n")
    fp.write(f"mxWrapCopyDef    (mxWrapCopy_{name},     {name})\n")
    fp.write(f"mxWrapReturnDef  (mxWrapReturn_{name},   {name})\n")
    fp.write(f"mxWrapGetArrayDef_single(mxWrapGetArray_single_{name}, {name})\n")
    fp.write(f"mxWrapCopyDef_single    (mxWrapCopy_single_{name},     {name})\n")
    fp.write(f"mxWrapReturnDef_single  (mxWrapReturn_single_{name},   {name})\n")


def _mex_define_zcopiers(fp, name, ztype):
    """Emit complex copier macro calls for one complex type."""
    fp.write(f"mxWrapGetScalarZDef(mxWrapGetScalar_{name}, {name},\n"
           f"                    {ztype}, setz_{name})\n")
    fp.write(f"mxWrapGetArrayZDef (mxWrapGetArray_{name}, {name},\n"
           f"                    {ztype}, setz_{name})\n")
    fp.write(f"mxWrapCopyZDef     (mxWrapCopy_{name}, {name},\n"
           f"                    real_{name}, imag_{name})\n")
    fp.write(f"mxWrapReturnZDef   (mxWrapReturn_{name}, {name},\n"
           f"                    real_{name}, imag_{name})\n")
    fp.write(f"mxWrapGetScalarZDef_single(mxWrapGetScalar_single_{name}, {name},\n"
           f"                    {ztype}, setz_{name})\n")
    fp.write(f"mxWrapGetArrayZDef_single (mxWrapGetArray_single_{name}, {name},\n"
           f"                    {ztype}, setz_{name})\n")
    fp.write(f"mxWrapCopyZDef_single     (mxWrapCopy_single_{name}, {name},\n"
           f"                    real_{name}, imag_{name})\n")
    fp.write(f"mxWrapReturnZDef_single   (mxWrapReturn_single_{name}, {name},\n"
           f"                    real_{name}, imag_{name})\n")


def mex_define_copiers(fp, ctx):
    fp.write("\n\n\n/* Array copier definitions */\n")
    for name in sorted(ctx.scalar_decls):
        _mex_define_copiers_type(fp, ctx, name)
    for name in sorted(ctx.cscalar_decls):
        _mex_define_zcopiers(fp, name, "float")
    for name in sorted(ctx.zscalar_decls):
        _mex_define_zcopiers(fp, name, "double")
    fp.write("\n")


# ===================================================================
# Fortran name mangling
# ===================================================================

def _fortran_funcs(funcs):
    """Yield unique Func objects for fortran functions."""
    seen = set()
    for f in funcs:
        if f.fort and f.funcv not in seen:
            seen.add(f.funcv)
            yield f


def mex_define_fnames(fp, funcs):
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


def _mex_fortran_arg(fp, args):
    parts = []
    for v in args:
        if v.tinfo == VT.mx:
            parts.append("const mxArray*")
        else:
            parts.append(f"{v.basetype}*")
    fp.write(", ".join(parts))


def mex_fortran_decls(fp, funcs):
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
        _mex_fortran_arg(fp, fc.args)
        fp.write(");\n")
    fp.write("\n#ifdef __cplusplus\n"
           "} /* end extern C */\n"
           "#endif\n\n")


# ===================================================================
# Class polymorphism getters
# ===================================================================

def _mex_casting_getter_type(fp, name):
    fp.write(f"    {name}* p_{name} = NULL;\n"
           f"    sscanf(pbuf, \"{name}:%p\", &p_{name});\n"
           f"    if (p_{name})\n"
           f"        return p_{name};\n\n")


def _mex_casting_getter(fp, cname, inherits):
    fp.write(f"\n{cname}* mxWrapGetP_{cname}(const mxArray* a, const char** e)\n")
    fp.write("{\n"
           "    char pbuf[128];\n"
           "    if (mxGetClassID(a) == mxDOUBLE_CLASS &&\n"
           "        mxGetM(a)*mxGetN(a) == 1 &&\n"
           "#if MX_HAS_INTERLEAVED_COMPLEX\n"
           "        ((mxIsComplex(a) ? ((*mxGetComplexDoubles(a)).real == 0 && (*mxGetComplexDoubles(a)).imag == 0) : *mxGetDoubles(a) == 0))\n"
           "#else\n"
           "        *mxGetPr(a) == 0\n"
           "#endif\n"
           "        )\n"
           "        return NULL;\n"
           "    if (!mxIsChar(a)) {\n"
           "#ifdef R2008OO\n"
           f"        mxArray* ap = mxGetProperty(a, 0, \"mwptr\");\n"
           f"        if (ap)\n"
           f"            return mxWrapGetP_{cname}(ap, e);\n"
           "#endif\n"
           "        *e = \"Invalid pointer\";\n"
           "        return NULL;\n"
           "    }\n"
           "    mxGetString(a, pbuf, sizeof(pbuf));\n\n")
    _mex_casting_getter_type(fp, cname)
    for name in inherits:
        _mex_casting_getter_type(fp, name)
    fp.write(f"    *e = \"Invalid pointer to {cname}\";\n"
           f"    return NULL;\n"
           f"}}\n\n")


def mex_casting_getters(fp, ctx):
    for parent in sorted(ctx.class_decls.keys()):
        _mex_casting_getter(fp, parent, ctx.class_decls[parent])


# ===================================================================
# Per-stub helpers: declarations, unpack, check, alloc, call, marshal, dealloc
# ===================================================================

def _declare_type(v):
    """Return C type string for a variable declaration."""
    if is_obj(v.tinfo) or is_array(v.tinfo):
        if v.devicespec == 'g':
            return f"{basetype_to_cucomplex(v.basetype)}*"
        return f"{v.basetype}*"
    if v.tinfo == VT.rarray:
        if v.devicespec == 'g':
            return f"const {basetype_to_cucomplex(v.basetype)}*"
        return f"const {v.basetype}*"
    if v.tinfo in (VT.scalar, VT.cscalar, VT.zscalar,
                   VT.r_scalar, VT.r_cscalar, VT.r_zscalar,
                   VT.p_scalar, VT.p_cscalar, VT.p_zscalar):
        return v.basetype
    if v.tinfo == VT.string:
        return "char*"
    if v.tinfo == VT.mx:
        if v.iospec == 'i':
            return "const mxArray*"
        return "mxArray*"
    assert False, f"Unknown tinfo {v.tinfo} for {v.name}"


# --- Step 1: Declare locals ---

def _declare_in_args(fp, args):
    for v in args:
        if v.iospec != 'o' and v.tinfo != VT.const:
            tb = _declare_type(v)
            if is_array(v.tinfo) or is_obj(v.tinfo) or v.tinfo == VT.string:
                fp.write(f"    {tb:10s}  in{v.input_label}_ =0; /* {v.name:10s} */\n")
                if v.devicespec == 'g':
                    fp.write(f"    {'mxGPUArray const':10s} *mxGPUArray_in{v.input_label}_ =0; /* {v.name:10s} */\n")
            else:
                fp.write(f"    {tb:10s}  in{v.input_label}_;    /* {v.name:10s} */\n")


def _declare_out_args(fp, args):
    for v in args:
        if v.iospec == 'o' and v.tinfo != VT.mx:
            tb = _declare_type(v)
            if is_array(v.tinfo) or is_obj(v.tinfo) or v.tinfo == VT.string:
                fp.write(f"    {tb:10s}  out{v.output_label}_=0; /* {v.name:10s} */\n")
                if v.devicespec == 'g':
                    fp.write(f"    {'mxGPUArray':10s} *mxGPUArray_out{v.output_label}_ =0; /* {v.name:10s} */\n")
                    fp.write(f"    {'mwSize':10s} gpu_outdims{v.output_label}_[2] = {{0,0}}; /* {v.name:10s} dims*/\n")
            else:
                fp.write(f"    {tb:10s}  out{v.output_label}_;   /* {v.name:10s} */\n")


def _declare_dim_args_expr(fp, args):
    for e in args:
        fp.write(f"    {'mwSize':10s}  dim{e.input_label}_;   /* {e.value:10s} */\n")


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


# --- Step 2: Unpack dims ---

def _unpack_dims_expr(fp, args):
    count = 0
    for e in args:
        fp.write(f"    dim{e.input_label}_ = (mwSize) mxWrapGetScalar(prhs[{e.input_label}], &mw_err_txt_);\n")
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


# --- Step 3: Check dim consistency ---

def _check_dims(fp, args):
    for v in args:
        if (v.iospec != 'o' and is_array(v.tinfo) and
                v.qual and v.qual.args and v.devicespec != 'g'):
            a = v.qual.args
            if len(a) > 1:
                fp.write(f"    if (mxGetM(prhs[{v.input_label}]) != dim{a[0].input_label}_ ||\n"
                       f"        mxGetN(prhs[{v.input_label}]) != dim{a[1].input_label}_) {{\n"
                       f"        mw_err_txt_ = \"Bad argument size: {v.name}\";\n"
                       f"        goto mw_err_label;\n"
                       f"    }}\n\n")
            else:
                fp.write(f"    if (mxGetM(prhs[{v.input_label}])*mxGetN(prhs[{v.input_label}]) != dim{a[0].input_label}_) {{\n"
                       f"        mw_err_txt_ = \"Bad argument size: {v.name}\";"
                       f"        goto mw_err_label;\n"
                       f"    }}\n\n")


# --- Step 4: Unpack inputs ---

def _cast_get_p(fp, ctx, basetype, input_label):
    fp.write(f"    in{input_label}_ = ")
    if ctx.is_mxarray_type(basetype):
        fp.write(f"mxWrapGet_{basetype}(prhs[{input_label}], &mw_err_txt_);\n")
    elif basetype not in ctx.class_decls:
        fp.write(f"({basetype}*) mxWrapGetP(prhs[{input_label}], \"{basetype}:%p\", &mw_err_txt_);\n")
    else:
        fp.write(f"mxWrapGetP_{basetype}(prhs[{input_label}], &mw_err_txt_);\n")
    fp.write("    if (mw_err_txt_)\n"
           "        goto mw_err_label;\n\n")


def _unpack_input_array(fp, v):
    il = v.input_label
    bt = v.basetype

    # --- Regular (copy) path for CPU ---
    if v.devicespec != 'g':
        tp = _type_props(bt)
        cs = _copier_suffix(bt)
        fp.write(f"    if (mxGetM(prhs[{il}])*mxGetN(prhs[{il}]) != 0) {{\n")
        if complex_tinfo(v) and bt in TYPE_PROPS:
            # Known complex types: class check + copier
            fp.write(f"        if( mxGetClassID(prhs[{il}]) != {tp.mxclass} )\n"
                   f"            mw_err_txt_ = \"Invalid array argument, {tp.mxclass} expected\";\n"
                   f"        if (mw_err_txt_) goto mw_err_label;\n"
                   f"        in{il}_ = mxWrapGetArray_{cs}{bt}(prhs[{il}], &mw_err_txt_);\n"
                   f"        if (mw_err_txt_)\n"
                   f"            goto mw_err_label;\n")
        elif tp.direct_input and v.iospec == 'i':
            # float/double input-only: class check + direct accessor
            fp.write(f"        if( mxGetClassID(prhs[{il}]) != {tp.mxclass} )\n"
                   f"            mw_err_txt_ = \"Invalid array argument, {tp.mxclass} expected\";\n"
                   f"        if (mw_err_txt_) goto mw_err_label;\n"
                   f"#if MX_HAS_INTERLEAVED_COMPLEX\n"
                   f"        in{il}_ = {tp.accessor}(prhs[{il}]);\n"
                   f"#else\n")
            if bt == "double":
                fp.write(f"        in{il}_ = mxGetPr(prhs[{il}]);\n")
            else:
                fp.write(f"        in{il}_ = ({bt}*) mxGetData(prhs[{il}]);\n")
            fp.write(f"#endif\n")
        else:
            # All other types (including float/double inout): copier
            fp.write(f"        in{il}_ = mxWrapGetArray_{cs}{bt}(prhs[{il}], &mw_err_txt_);\n"
                   f"        if (mw_err_txt_)\n"
                   f"            goto mw_err_label;\n")
        fp.write(f"    }} else\n"
               f"        in{il}_ = NULL;\n")
        fp.write("\n")

    # --- GPU path ---
    if v.devicespec == 'g':
        if v.iospec in ('i', 'b'):
            cutype = basetype_to_cucomplex(bt)
            fp.write(f"    // extract input GPU array pointer\n"
                   f"    if(!(mxIsGPUArray(prhs[{il}])))\n"
                   f"        mw_err_txt_ = \"Invalid array argument, gpuArray expected\";\n"
                   f"    if (mw_err_txt_) goto mw_err_label;\n"
                   f"    mxGPUArray_in{il}_ = mxGPUCreateFromMxArray(prhs[{il}]);\n"
                   f"    in{il}_ = ({cutype} *)mxGPUGetDataReadOnly(mxGPUArray_in{il}_);\n\n")


def _unpack_input_string(fp, v):
    il = v.input_label
    if not (v.qual and v.qual.args):
        fp.write(f"    in{il}_ = mxWrapGetString(prhs[{il}], &mw_err_txt_);\n"
               f"    if (mw_err_txt_)\n"
               f"        goto mw_err_label;\n")
    else:
        sz = _alloc_size_expr(v.qual.args)
        fp.write(f"    in{il}_ = (char*) mxMalloc({sz}*sizeof(char));\n")
        fp.write(f"    if (mxGetString(prhs[{il}], in{il}_, {sz}) != 0) {{\n"
               f"        mw_err_txt_ = \"Invalid string argument\";\n"
               f"        goto mw_err_label;\n"
               f"    }}\n")
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
            tp = _type_props(bt)
            fp.write(f"    if( mxGetClassID(prhs[{il}]) != {tp.scalar_class} )\n"
                   f"        mw_err_txt_ = \"Invalid scalar argument, {tp.scalar_class} expected\";\n"
                   f"    if (mw_err_txt_) goto mw_err_label;\n"
                   f"    in{il}_ = ({bt}) {tp.scalar_getter}(prhs[{il}], &mw_err_txt_);\n"
                   f"    if (mw_err_txt_)\n"
                   f"        goto mw_err_label;\n")
            if bt != "char":
                fp.write("\n")
        elif v.tinfo in (VT.cscalar, VT.zscalar,
                         VT.r_cscalar, VT.r_zscalar,
                         VT.p_cscalar, VT.p_zscalar):
            il = v.input_label
            bt = v.basetype
            tp = _type_props(bt)
            fp.write(f"    if( mxGetClassID(prhs[{il}]) != {tp.scalar_class} )\n"
                   f"        mw_err_txt_ = \"Invalid scalar argument, {tp.scalar_class} expected\";\n"
                   f"    if (mw_err_txt_) goto mw_err_label;\n")
            cs = _copier_suffix(bt)
            fp.write(f"    mxWrapGetScalar_{cs}{bt}(&in{il}_, prhs[{il}]);\n\n")
        elif v.tinfo == VT.string:
            _unpack_input_string(fp, v)
        elif v.tinfo == VT.mx:
            fp.write(f"    in{v.input_label}_ = prhs[{v.input_label}];\n\n")


def _unpack_inputs(fp, ctx, f):
    if f.thisv:
        _cast_get_p(fp, ctx, f.classv, 0)
    _unpack_inputs_var(fp, ctx, f.args)


# --- Step 5: Null-check objects/this ---

def _check_inputs(fp, args):
    for v in args:
        if v.iospec != 'o' and v.tinfo in (VT.obj, VT.r_obj):
            fp.write(f"    if (!in{v.input_label}_) {{\n"
                   f"        mw_err_txt_ = \"Argument {v.name} cannot be null\";\n"
                   f"        goto mw_err_label;\n"
                   f"    }}\n")


# --- Step 6: Allocate outputs ---

def _alloc_output(fp, ctx, args, return_flag):
    for v in args:
        if v.iospec == 'o':
            if v.devicespec != 'g':
                if not return_flag and is_obj(v.tinfo) and ctx.is_mxarray_type(v.basetype):
                    fp.write(f"    out{v.output_label}_ = mxWrapAlloc_{v.basetype}();\n")
                elif is_array(v.tinfo):
                    fp.write(f"    out{v.output_label}_ = ({v.basetype}*) mxMalloc({_alloc_size_expr(v.qual.args)}*sizeof({v.basetype}));\n")
                elif v.tinfo == VT.rarray:
                    fp.write(f"    out{v.output_label}_ = ({v.basetype}*) NULL;\n")
                elif v.tinfo == VT.string:
                    fp.write(f"    out{v.output_label}_ = (char*) mxMalloc({_alloc_size_expr(v.qual.args)}*sizeof(char));\n")
            if v.devicespec == 'g':
                da = v.qual.args
                ndims = 2 if len(da) == 2 else 1
                mtype = "mxCOMPLEX" if complex_tinfo(v) else "mxREAL"
                mxcid = basetype_to_mxclassid(v.basetype)
                cutype = basetype_to_cucomplex(v.basetype)
                if ndims == 2:
                    fp.write(f"    gpu_outdims{v.output_label}_[0] = dim{da[0].input_label}_; gpu_outdims{v.output_label}_[1] = dim{da[1].input_label}_;\n")
                else:
                    fp.write(f"    gpu_outdims{v.output_label}_[0] = dim{da[0].input_label}_;\n")
                fp.write(f"    mxGPUArray_out{v.output_label}_ = mxGPUCreateGPUArray({ndims}, gpu_outdims{v.output_label}_, {mxcid}, {mtype}, MX_GPU_DO_NOT_INITIALIZE);\n")
                fp.write(f"    out{v.output_label}_ = ({cutype} *)mxGPUGetData(mxGPUArray_out{v.output_label}_);\n\n")


def _alloc_outputs(fp, ctx, f):
    if not nullable_return(f):
        _alloc_output(fp, ctx, f.ret, True)
    _alloc_output(fp, ctx, f.args, False)


# --- Step 7: Profiler ---

def _record_call(fp, f):
    fp.write(f"    if (mexprofrecord_)\n"
           f"        mexprofrecord_[{f.id}]++;\n")


# --- Step 8: Make the call ---

def _make_call_args(fp, args, first):
    for v in args:
        if not first:
            fp.write(", ")
        n = vname(v)
        if v.tinfo in (VT.obj, VT.r_obj):
            fp.write(f"*{n}")
        elif v.tinfo == VT.mx and v.iospec == 'o':
            fp.write(f"plhs+{v.output_label}")
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
            if ctx.is_mxarray_type(v.basetype):
                fp.write(f"    plhs[0] = mxWrapSet_{v.basetype}(&(")
                _make_call_expr(fp, f)
                fp.write("));\n")
            else:
                fp.write(f"    out0_ = new {v.basetype}(")
                _make_call_expr(fp, f)
                fp.write(");\n")
        elif is_array(v.tinfo):
            fp.write(f"    plhs[0] = mxWrapReturn_{v.basetype}(")
            _make_call_expr(fp, f)
            fp.write(", ")
            args = v.qual.args
            if len(args) == 2:
                fp.write(f" dim{args[0].input_label}_, dim{args[1].input_label}_);\n")
            else:
                fp.write(f"{_alloc_size_expr(args)}, 1);\n")
        elif v.tinfo in (VT.scalar, VT.r_scalar, VT.cscalar, VT.r_cscalar, VT.zscalar, VT.r_zscalar):
            fp.write("    out0_ = ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo == VT.string:
            fp.write("    plhs[0] = mxWrapStrncpy(")
            _make_call_expr(fp, f)
            fp.write(");\n")
        elif v.tinfo == VT.mx:
            fp.write("    plhs[0] = ")
            _make_call_expr(fp, f)
            fp.write(";\n")
        elif v.tinfo == VT.p_obj:
            if ctx.is_mxarray_type(v.basetype):
                fp.write(f"    plhs[0] = mxWrapSet_{v.basetype}(")
                _make_call_expr(fp, f)
                fp.write(");\n")
            else:
                fp.write("    out0_ = ")
                _make_call_expr(fp, f)
                fp.write(";\n")
        elif v.tinfo in (VT.p_scalar, VT.p_cscalar, VT.p_zscalar):
            fp.write(f"    plhs[0] = mxWrapReturn_{v.basetype}(")
            _make_call_expr(fp, f)
            fp.write(", 1, 1);\n")
        elif v.tinfo == VT.r_obj:
            if ctx.is_mxarray_type(v.basetype):
                fp.write(f"    plhs[0] = mxWrapSet_{v.basetype}(&(")
                _make_call_expr(fp, f)
                fp.write("));\n")
            else:
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


# --- Step 9: Marshal results ---

def _marshal_array(fp, v):
    il = v.input_label
    ol = v.output_label
    bt = v.basetype
    n = vname(v)

    if v.devicespec != 'g':
        da = v.qual.args
        mtype = "mxCOMPLEX" if complex_tinfo(v) else "mxREAL"
        ws = "    "
        is_single = _type_props(bt).is_single

        if v.tinfo == VT.rarray:
            ws = "        "
            fp.write(f"    if (out{ol}_ == NULL) {{\n")
            fp.write(f"        plhs[{ol}] = mxCreateDoubleMatrix(0,0, mxREAL);\n")
            fp.write(f"    }} else {{\n")

        if not da:
            # No dims — inout array
            if is_single:
                fp.write(f"{ws}plhs[{ol}] = mxCreateNumericMatrix(mxGetM(prhs[{il}]), mxGetN(prhs[{il}]), mxSINGLE_CLASS, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_single_{bt}(plhs[{ol}], in{il}_, ")
            else:
                fp.write(f"{ws}plhs[{ol}] = mxCreateDoubleMatrix(mxGetM(prhs[{il}]), mxGetN(prhs[{il}]), {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_{bt}(plhs[{ol}], in{il}_, ")
            fp.write(f"mxGetM(prhs[{il}])*mxGetN(prhs[{il}])")
            fp.write(");\n")
        elif len(da) == 1:
            # 1D
            if is_single:
                fp.write(f"{ws}plhs[{ol}] = mxCreateNumericMatrix(dim{da[0].input_label}_, 1, mxSINGLE_CLASS, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_single_{bt}(plhs[{ol}], {n}, ")
            else:
                fp.write(f"{ws}plhs[{ol}] = mxCreateDoubleMatrix(dim{da[0].input_label}_, 1, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_{bt}(plhs[{ol}], {n}, ")
            fp.write(f"dim{da[0].input_label}_")
            fp.write(");\n")
        elif len(da) == 2:
            # 2D
            if is_single:
                fp.write(f"{ws}plhs[{ol}] = mxCreateNumericMatrix(dim{da[0].input_label}_, dim{da[1].input_label}_, mxSINGLE_CLASS, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_single_{bt}(plhs[{ol}], {n}, ")
            else:
                fp.write(f"{ws}plhs[{ol}] = mxCreateDoubleMatrix(dim{da[0].input_label}_, dim{da[1].input_label}_, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_{bt}(plhs[{ol}], {n}, ")
            fp.write(f"dim{da[0].input_label}_*dim{da[1].input_label}_")
            fp.write(");\n")
        else:
            # 3D+ — flatten to 1D
            sz = _alloc_size_expr(da)
            if is_single:
                fp.write(f"{ws}plhs[{ol}] = mxCreateNumericMatrix({sz}, 1, mxSINGLE_CLASS, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_single_{bt}(plhs[{ol}], {n}, ")
            else:
                fp.write(f"{ws}plhs[{ol}] = mxCreateDoubleMatrix({sz}, 1, {mtype});\n")
                fp.write(f"{ws}mxWrapCopy_{bt}(plhs[{ol}], {n}, ")
            fp.write(sz)
            fp.write(");\n")

        if v.tinfo == VT.rarray:
            fp.write("    }\n")

    # GPU marshal
    if v.devicespec == 'g':
        if v.iospec == 'b':
            fp.write(f"    plhs[{ol}] = prhs[{il}];\n")
        if v.iospec == 'o':
            fp.write(f"    plhs[{ol}] = mxGPUCreateMxArrayOnGPU(mxGPUArray_out{ol}_);\n")


def _marshal_result(fp, ctx, v, return_flag):
    n = vname(v)
    ol = v.output_label
    bt = v.basetype

    if is_obj(v.tinfo) and ctx.is_mxarray_type(bt):
        if not return_flag:
            fp.write(f"    plhs[{ol}] = mxWrapSet_{bt}({n});\n")
    elif is_obj(v.tinfo):
        fp.write(f"    plhs[{ol}] = mxWrapCreateP(out{ol}_, \"{bt}:%p\");\n")
    elif is_array(v.tinfo) or v.tinfo == VT.rarray:
        _marshal_array(fp, v)
    elif v.tinfo in (VT.scalar, VT.r_scalar, VT.p_scalar):
        _interleaved_branch(fp,
            f"    plhs[{ol}] = mxCreateDoubleMatrix(1, 1, mxREAL);\n"
            f"    *mxGetDoubles(plhs[{ol}]) = {n};\n",
            f"    plhs[{ol}] = mxCreateDoubleMatrix(1, 1, mxREAL);\n"
            f"    *mxGetPr(plhs[{ol}]) = {n};\n")
    elif v.tinfo in (VT.cscalar, VT.zscalar,
                     VT.r_cscalar, VT.r_zscalar,
                     VT.p_cscalar, VT.p_zscalar):
        _interleaved_branch(fp,
            f"    plhs[{ol}] = mxCreateDoubleMatrix(1, 1, mxCOMPLEX);\n"
            f"    mxGetComplexDoubles(plhs[{ol}])->real = real_{bt}({n});\n"
            f"    mxGetComplexDoubles(plhs[{ol}])->imag = imag_{bt}({n});\n",
            f"    plhs[{ol}] = mxCreateDoubleMatrix(1, 1, mxCOMPLEX);\n"
            f"    *mxGetPr(plhs[{ol}]) = real_{bt}({n});\n"
            f"    *mxGetPi(plhs[{ol}]) = imag_{bt}({n});\n")
    elif v.tinfo == VT.string:
        fp.write(f"    plhs[{ol}] = mxCreateString({n});\n")


def _marshal_results_var(fp, ctx, vars, return_flag):
    for v in vars:
        if v.iospec != 'i':
            _marshal_result(fp, ctx, v, return_flag)


def _marshal_results(fp, ctx, f):
    if not nullable_return(f):
        _marshal_results_var(fp, ctx, f.ret, True)
    _marshal_results_var(fp, ctx, f.args, False)


# --- Step 10: Dealloc ---

def _dealloc_var(fp, ctx, vars, return_flag):
    for v in vars:
        if v.devicespec != 'g':
            if is_array(v.tinfo) or v.tinfo == VT.string:
                if v.iospec == 'o':
                    fp.write(f"    if (out{v.output_label}_) mxFree(out{v.output_label}_);\n")
                elif v.iospec == 'b' or not (v.basetype == "double" or v.basetype == "float"):
                    fp.write(f"    if (in{v.input_label}_)  mxFree(in{v.input_label}_);\n")
            elif is_obj(v.tinfo) and ctx.is_mxarray_type(v.basetype):
                if v.iospec in ('i', 'b'):
                    fp.write(f"    if (in{v.input_label}_)  mxWrapFree_{v.basetype}(in{v.input_label}_);\n")
                elif v.iospec == 'o' and not return_flag:
                    fp.write(f"    if (out{v.output_label}_) mxWrapFree_{v.basetype}(out{v.output_label}_);\n")
        if v.devicespec == 'g':
            if v.iospec in ('i', 'b'):
                fp.write(f"    if (mxGPUArray_in{v.input_label}_)  mxGPUDestroyGPUArray(mxGPUArray_in{v.input_label}_);\n")
            if v.iospec == 'o':
                fp.write(f"    if (mxGPUArray_out{v.output_label}_)  mxGPUDestroyGPUArray(mxGPUArray_out{v.output_label}_);\n")


def _dealloc(fp, ctx, f):
    if not nullable_return(f):
        _dealloc_var(fp, ctx, f.ret, True)
    _dealloc_var(fp, ctx, f.args, False)


# ===================================================================
# Print a single MEX stub
# ===================================================================

def _print_c_comment(fp, f):
    fp.write(f"/* ---- {f.fname}: {f.line} ----\n")
    fp.write(f" * {print_func(f)}")
    # Preserve original behavior: only print first duplicate
    if f.same:
        fsame = f.same[0]
        fp.write(f" * Also at {fsame.fname}: {fsame.line}\n")
    fp.write(" */\n")


def _print_mex_stub(fp, ctx, f):
    _print_c_comment(fp, f)
    ids = id_string(ctx, f)
    fp.write(f"static const char* stubids{f.id}_ = \"{ids}\";\n\n")
    fp.write(f"void mexStub{f.id}(int nlhs, mxArray* plhs[],\n"
           f"              int nrhs, const mxArray* prhs[])\n"
           f"{{\n"
           f"    const char* mw_err_txt_ = 0;\n")
    _declare_args(fp, f)
    _unpack_dims(fp, f)
    _check_dims(fp, f.args)
    _unpack_inputs(fp, ctx, f)
    _check_inputs(fp, f.args)
    _alloc_outputs(fp, ctx, f)
    _record_call(fp, f)
    _make_stmt(fp, ctx, f)
    _marshal_results(fp, ctx, f)
    fp.write("\nmw_err_label:\n")
    _dealloc(fp, ctx, f)
    fp.write("    if (mw_err_txt_)\n"
           "        mexErrMsgTxt(mw_err_txt_);\n"
           "}\n\n")


# ===================================================================
# Print all stubs, dispatch table, mexFunction
# ===================================================================

def _print_mex_stubs(fp, ctx, funcs):
    for f in funcs:
        _print_mex_stub(fp, ctx, f)


def _print_mex_stub_table(fp, funcs):
    # Build id → stub_id map
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

    fp.write("typedef void (*mwStubFunc_t)(int nlhs, mxArray* plhs[],\n"
           "                             int nrhs, const mxArray* prhs[]);\n\n"
           "static mwStubFunc_t mwStubs_[] = {\n"
           "    NULL")
    for i in range(1, maxid + 1):
        fp.write(",\n")
        if i in id_to_stub:
            fp.write(f"    mexStub{id_to_stub[i]}")
        else:
            fp.write("    NULL")
    fp.write("\n};\n\n")
    fp.write(f"static int mwNumStubs_ = {maxid};\n\n")


def _make_profile_output(fp, funcs, printfunc):
    fp.write(f"        if (!mexprofrecord_)\n"
           f"            {printfunc}\"Profiler inactive\\n\");\n")
    for fc in funcs:
        fp.write(f"        {printfunc}\"%d calls to {fc.fname}:{fc.line}")
        # Preserve original behavior: only print first duplicate
        if fc.same:
            fp.write(f" ({fc.same[0].fname}:{fc.same[0].line})")
        fp.write(f"\\n\", mexprofrecord_[{fc.id}]);\n")


def _print_mex_else_cases(fp, funcs):
    for fc in funcs:
        fp.write(f"    else if (strcmp(id, stubids{fc.id}_) == 0)\n"
               f"        mexStub{fc.id}(nlhs,plhs, nrhs-1,prhs+1);\n")

    maxid = max_routine_id(funcs)
    fp.write(f"    else if (strcmp(id, \"*profile on*\") == 0) {{\n"
           f"        if (!mexprofrecord_) {{\n"
           f"            mexprofrecord_ = (int*) malloc({maxid+1} * sizeof(int));\n"
           f"            mexLock();\n"
           f"        }}\n"
           f"        memset(mexprofrecord_, 0, {maxid+1} * sizeof(int));\n"
           f"    }} else if (strcmp(id, \"*profile off*\") == 0) {{\n"
           f"        if (mexprofrecord_) {{\n"
           f"            free(mexprofrecord_);\n"
           f"            mexUnlock();\n"
           f"        }}\n"
           f"        mexprofrecord_ = NULL;\n"
           f"    }} else if (strcmp(id, \"*profile report*\") == 0) {{\n")
    _make_profile_output(fp, funcs, "mexPrintf(")
    fp.write(f"    }} else if (strcmp(id, \"*profile log*\") == 0) {{\n"
           f"        FILE* logfp;\n"
           f"        if (nrhs != 2 || mxGetString(prhs[1], id, sizeof(id)) != 0)\n"
           f"            mexErrMsgTxt(\"Must have two string arguments\");\n"
           f"        logfp = fopen(id, \"w+\");\n"
           f"        if (!logfp)\n"
           f"            mexErrMsgTxt(\"Cannot open log for output\");\n")
    _make_profile_output(fp, funcs, "fprintf(logfp, ")
    fp.write("        fclose(logfp);\n")
    fp.write("    } else\n"
           "        mexErrMsgTxt(\"Unknown identifier\");\n")


# ===================================================================
# Top-level: print_mex_init + print_mex_file
# ===================================================================

MWRAP_BANNER = (
    "/* --------------------------------------------------- */\n"
    "/* Automatically generated by mwrap                    */\n"
    "/* --------------------------------------------------- */\n\n"
)

MEX_BASE = (
    "/* ----\n"
    " */\n"
    "void mexFunction(int nlhs, mxArray* plhs[],\n"
    "                 int nrhs, const mxArray* prhs[])\n"
    "{\n"
    "    if (nrhs == 0) {\n"
    "        mexPrintf(\"Mex function installed\\n\");\n"
    "        return;\n"
    "    }\n\n"
    "    /* Fast path: integer stub ID */\n"
    "    if (!mxIsChar(prhs[0])) {\n"
    "        int stub_id = (int) mxGetScalar(prhs[0]);\n"
    "        if (stub_id > 0 && stub_id <= mwNumStubs_ && mwStubs_[stub_id])\n"
    "            mwStubs_[stub_id](nlhs, plhs, nrhs-1, prhs+1);\n"
    "        else\n"
    "            mexErrMsgTxt(\"Unknown function ID\");\n"
    "        return;\n"
    "    }\n\n"
)

MEX_BASE_IF = (
    "    char id[1024];\n"
    "    if (mxGetString(prhs[0], id, sizeof(id)) != 0)\n"
    "        mexErrMsgTxt(\"Identifier should be a string\");\n"
)


def print_mex_init(fp, ctx, support_text):
    """Write the MEX file header: banner + runtime support + complex/GPU includes."""
    fp.write(MWRAP_BANNER)
    fp.write(support_text)
    fp.write("\n")
    if ctx.mw_use_gpu:
        fp.write("#include <gpu/mxGPUArray.h>\n\n")
    if ctx.mw_use_c99_complex:
        mex_c99_complex(fp)
    elif ctx.mw_use_cpp_complex:
        mex_cpp_complex(fp)
        if ctx.mw_use_gpu:
            mex_gpucpp_complex(fp)


def print_mex_file(fp, ctx, funcs):
    """Write the rest of the MEX file: copiers, getters, stubs, dispatch."""
    if ctx.mw_use_int32_t or ctx.mw_use_int64_t or ctx.mw_use_uint32_t or ctx.mw_use_uint64_t:
        fp.write("#include <stdint.h>\n\n")
    mex_define_copiers(fp, ctx)
    mex_casting_getters(fp, ctx)

    if has_fortran(funcs):
        mex_define_fnames(fp, funcs)
        mex_fortran_decls(fp, funcs)

    _print_mex_stubs(fp, ctx, funcs)
    _print_mex_stub_table(fp, funcs)
    fp.write(MEX_BASE)
    fp.write("\n")
    if ctx.mw_use_gpu:
        fp.write("    mxInitGPU();\n")
    fp.write("\n")
    fp.write(MEX_BASE_IF)
    _print_mex_else_cases(fp, funcs)
    fp.write("}\n\n")
