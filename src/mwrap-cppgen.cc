/*
 * mwrap-cppgen.cc
 *   Generate MATLAB C++ MEX API code from MWrap AST.
 *
 * Copyright (c) 2007  David Bindel
 * See the file COPYING for copying permissions
 *
 * C++ MEX API backend by Zydrunas Gimbutas (2026),
 * with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cassert>
#include "mwrap-ast.h"
#include "mwrap-cpp-support.h"


/* -- C++ MEX API type property table -- */

struct CppTypeProps {
    const char* array_type_enum;  /* "ArrayType::DOUBLE", etc. */
    const char* scalar_type;     /* "double", "float", "int32_t", etc. */
    const char* typed_array;     /* "TypedArray<double>", etc. */
};

static const CppTypeProps cpp_default_props =
    {"ArrayType::DOUBLE", "double", "TypedArray<double>"};

struct CppTypeEntry {
    const char* name;
    CppTypeProps props;
};

static const CppTypeEntry cpp_type_table[] = {
    {"double",   {"ArrayType::DOUBLE",         "double",               "TypedArray<double>"}},
    {"float",    {"ArrayType::SINGLE",         "float",                "TypedArray<float>"}},
    {"int32_t",  {"ArrayType::INT32",          "int32_t",              "TypedArray<int32_t>"}},
    {"int64_t",  {"ArrayType::INT64",          "int64_t",              "TypedArray<int64_t>"}},
    {"uint32_t", {"ArrayType::UINT32",         "uint32_t",             "TypedArray<uint32_t>"}},
    {"uint64_t", {"ArrayType::UINT64",         "uint64_t",             "TypedArray<uint64_t>"}},
    {"dcomplex", {"ArrayType::COMPLEX_DOUBLE", "std::complex<double>", "TypedArray<std::complex<double>>"}},
    {"fcomplex", {"ArrayType::COMPLEX_SINGLE", "std::complex<float>",  "TypedArray<std::complex<float>>"}},
    {"char",     {"ArrayType::CHAR",           "char",                 "CharArray"}},
    {NULL, {NULL, NULL, NULL}}
};


static const CppTypeProps* cpp_type_props(const char* name)
{
    for (const CppTypeEntry* e = cpp_type_table; e->name; ++e)
        if (strcmp(e->name, name) == 0)
            return &e->props;
    return &cpp_default_props;
}


static bool cpp_is_known_type(const char* name)
{
    for (const CppTypeEntry* e = cpp_type_table; e->name; ++e)
        if (strcmp(e->name, name) == 0)
            return true;
    return false;
}


/* -- Complex type definitions (always C++ for C++ MEX API) -- */

static void cpp_cpp_complex(FILE* fp)
{
    fprintf(fp,
            "#include <complex>\n"
            "\n"
            "typedef std::complex<double> dcomplex;\n"
            "#define real_dcomplex(z) std::real(z)\n"
            "#define imag_dcomplex(z) std::imag(z)\n"
            "#define setz_dcomplex(z,r,i)  *z = dcomplex(r,i)\n"
            "\n"
            "typedef std::complex<float> fcomplex;\n"
            "#define real_fcomplex(z) std::real(z)\n"
            "#define imag_fcomplex(z) std::imag(z)\n"
            "#define setz_fcomplex(z,r,i)  *z = fcomplex(r,i)\n\n");
}


/* -- Alloc size expression -- */

static void cpp_print_alloc_size_expr(FILE* fp, Expr* args)
{
    if (!args) {
        fprintf(fp, "1");
        return;
    }
    bool first = true;
    for (Expr* e = args; e; e = e->next) {
        if (!first)
            fprintf(fp, "*");
        fprintf(fp, "dim%d_", e->input_label);
        first = false;
    }
}


/* -- Fortran name mangling -- */

static void cpp_define_fnames(FILE* fp, Func* funcs)
{
    set<string> seen;

    fprintf(fp, "#if defined(MWF77_CAPS)\n");
    for (Func* f = funcs; f; f = f->next) {
        if (f->fort && seen.find(f->funcv) == seen.end()) {
            seen.insert(f->funcv);
            fprintf(fp, "#define MWF77_%s ", f->funcv);
            for (const char* p = f->funcv; *p; ++p)
                fputc(toupper(*p), fp);
            fprintf(fp, "\n");
        }
    }

    seen.clear();
    fprintf(fp, "#elif defined(MWF77_UNDERSCORE1)\n");
    for (Func* f = funcs; f; f = f->next) {
        if (f->fort && seen.find(f->funcv) == seen.end()) {
            seen.insert(f->funcv);
            fprintf(fp, "#define MWF77_%s ", f->funcv);
            for (const char* p = f->funcv; *p; ++p)
                fputc(tolower(*p), fp);
            fprintf(fp, "_\n");
        }
    }

    seen.clear();
    fprintf(fp, "#elif defined(MWF77_UNDERSCORE0)\n");
    for (Func* f = funcs; f; f = f->next) {
        if (f->fort && seen.find(f->funcv) == seen.end()) {
            seen.insert(f->funcv);
            fprintf(fp, "#define MWF77_%s ", f->funcv);
            for (const char* p = f->funcv; *p; ++p)
                fputc(tolower(*p), fp);
            fprintf(fp, "\n");
        }
    }

    seen.clear();
    fprintf(fp, "#else /* f2c convention */\n");
    for (Func* f = funcs; f; f = f->next) {
        if (f->fort && seen.find(f->funcv) == seen.end()) {
            seen.insert(f->funcv);
            fprintf(fp, "#define MWF77_%s ", f->funcv);
            bool has_underscore = false;
            for (const char* p = f->funcv; *p; ++p) {
                fputc(tolower(*p), fp);
                if (*p == '_') has_underscore = true;
            }
            fprintf(fp, has_underscore ? "__\n" : "_\n");
        }
    }
    fprintf(fp, "#endif\n\n");
}


static void cpp_fortran_decls(FILE* fp, Func* funcs)
{
    set<string> seen;

    fprintf(fp,
            "#ifdef __cplusplus\n"
            "extern \"C\" { /* Prevent C++ name mangling */\n"
            "#endif\n"
            "\n"
            "#ifndef MWF77_RETURN\n"
            "#define MWF77_RETURN int\n"
            "#endif\n\n");

    for (Func* f = funcs; f; f = f->next) {
        if (f->fort && seen.find(f->funcv) == seen.end()) {
            seen.insert(f->funcv);
            if (f->ret)
                fprintf(fp, "%s ", f->ret->basetype);
            else
                fprintf(fp, "MWF77_RETURN ");
            fprintf(fp, "MWF77_%s(", f->funcv);
            bool first = true;
            for (Var* v = f->args; v; v = v->next) {
                if (!first) fprintf(fp, ", ");
                fprintf(fp, "%s*", v->basetype);
                first = false;
            }
            fprintf(fp, ");\n");
        }
    }

    fprintf(fp,
            "\n#ifdef __cplusplus\n"
            "} /* end extern C */\n"
            "#endif\n\n");
}


/* -- Class polymorphism getters (C++ MEX API version) -- */

static void cpp_casting_getter_type(FILE* fp, const char* name)
{
    fprintf(fp,
            "    %s* p_%s = NULL;\n"
            "    sscanf(pbuf, \"%s:%%p\", &p_%s);\n"
            "    if (p_%s)\n"
            "        return p_%s;\n\n",
            name, name, name, name, name, name);
}


static void cpp_casting_getter(FILE* fp, const char* cname, InheritsDecl* inherits)
{
    fprintf(fp,
            "\nstatic %s* mwCppGetP_%s(const Array& a, const char** e)\n"
            "{\n"
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
            "    pbuf[sizeof(pbuf)-1] = '\\0';\n\n",
            cname, cname);

    cpp_casting_getter_type(fp, cname);
    for (InheritsDecl* d = inherits; d; d = d->next)
        cpp_casting_getter_type(fp, d->name);

    fprintf(fp,
            "    *e = \"Invalid pointer to %s\";\n"
            "    return NULL;\n"
            "}\n\n", cname);
}


static void cpp_casting_getters(FILE* fp)
{
    for (map<string, InheritsDecl*>::iterator it = class_decls.begin();
         it != class_decls.end(); ++it)
        cpp_casting_getter(fp, it->first.c_str(), it->second);
}


/* -- Complex array info helper -- */

struct CppComplexInfo {
    const char* array_type_enum;
    const char* scalar_type;
    const char* typed_array;
};

static bool get_cpp_complex_info(Var* v, CppComplexInfo* info)
{
    if (!complex_tinfo(v))
        return false;
    if (v->tinfo == VT_zarray) {
        info->array_type_enum = "ArrayType::COMPLEX_DOUBLE";
        info->scalar_type = "std::complex<double>";
        info->typed_array = "TypedArray<std::complex<double>>";
        return true;
    }
    if (v->tinfo == VT_carray) {
        info->array_type_enum = "ArrayType::COMPLEX_SINGLE";
        info->scalar_type = "std::complex<float>";
        info->typed_array = "TypedArray<std::complex<float>>";
        return true;
    }
    return false;
}


/* -- Per-stub helpers: declarations -- */

static const char* cpp_declare_type(Var* v)
{
    static char buf[256];
    if (is_obj(v->tinfo) || is_array(v->tinfo)) {
        snprintf(buf, sizeof(buf), "%s*", v->basetype);
        return buf;
    }
    if (v->tinfo == VT_rarray) {
        snprintf(buf, sizeof(buf), "const %s*", v->basetype);
        return buf;
    }
    if (v->tinfo == VT_scalar || v->tinfo == VT_cscalar || v->tinfo == VT_zscalar ||
        v->tinfo == VT_r_scalar || v->tinfo == VT_r_cscalar || v->tinfo == VT_r_zscalar ||
        v->tinfo == VT_p_scalar || v->tinfo == VT_p_cscalar || v->tinfo == VT_p_zscalar)
        return v->basetype;
    if (v->tinfo == VT_string)
        return "char*";
    if (v->tinfo == VT_mx)
        return "Array";
    assert(0 && "Unknown tinfo in cpp_declare_type");
    return "void";
}


static void cpp_declare_in_args(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec != 'o' && v->tinfo != VT_const) {
            const char* tb = cpp_declare_type(v);
            if (is_array(v->tinfo) || is_obj(v->tinfo) || v->tinfo == VT_string) {
                fprintf(fp, "    %-10s  in%d_ =0; /* %-10s */\n",
                        tb, v->input_label, v->name);
                /* For arrays, declare storage at function scope */
                if (is_array(v->tinfo)) {
                    const CppTypeProps* tp = cpp_type_props(v->basetype);
                    if (v->nocopy && v->iospec != 'b' && cpp_is_known_type(v->basetype)) {
                        /* Nocopy: declare unique_ptr<TypedArray> handle (ref-counted, keeps data alive) */
                        /* TypedArray default ctor is deleted in R2024b+, so wrap in unique_ptr */
                        CppComplexInfo zinfo;
                        const char* ta;
                        if (get_cpp_complex_info(v, &zinfo)) {
                            ta = zinfo.typed_array;
                            /* Also declare vec_ for real-to-complex fallback */
                            fprintf(fp, "    std::unique_ptr<%s>  ta_nc_in%d_;\n",
                                    ta, v->input_label);
                            fprintf(fp, "    std::vector<%s>  vec_in%d_;\n",
                                    tp->scalar_type, v->input_label);
                        } else {
                            ta = tp->typed_array;
                            fprintf(fp, "    std::unique_ptr<%s>  ta_nc_in%d_;\n",
                                    ta, v->input_label);
                        }
                    } else {
                        fprintf(fp, "    std::vector<%s>  vec_in%d_;\n",
                                tp->scalar_type, v->input_label);
                    }
                }
            } else if (v->tinfo == VT_mx) {
                fprintf(fp, "    %-10s  in%d_;    /* %-10s */\n",
                        tb, v->input_label, v->name);
            } else {
                fprintf(fp, "    %-10s  in%d_;    /* %-10s */\n",
                        tb, v->input_label, v->name);
            }
        }
    }
}


static void cpp_declare_out_args(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec == 'o') {
            if (v->tinfo == VT_mx) {
                fprintf(fp, "    Array      retval_mx%d_;   /* %-10s */\n",
                        v->output_label, v->name);
                continue;
            }
            const char* tb = cpp_declare_type(v);
            if (is_array(v->tinfo) || is_obj(v->tinfo) || v->tinfo == VT_string) {
                fprintf(fp, "    %-10s  out%d_=0; /* %-10s */\n",
                        tb, v->output_label, v->name);
                /* Nocopy output: declare buffer_ptr_t at function scope */
                if (v->nocopy && v->iospec == 'o' && is_array(v->tinfo)) {
                    const CppTypeProps* tp = cpp_type_props(v->basetype);
                    CppComplexInfo zinfo;
                    const char* st;
                    if (get_cpp_complex_info(v, &zinfo))
                        st = zinfo.scalar_type;
                    else
                        st = tp->scalar_type;
                    fprintf(fp, "    buffer_ptr_t<%s>  buf_out%d_{nullptr, nullptr};\n",
                            st, v->output_label);
                }
            } else
                fprintf(fp, "    %-10s  out%d_;   /* %-10s */\n",
                        tb, v->output_label, v->name);
        }
    }
}


static void cpp_declare_dim_args_expr(FILE* fp, Expr* args)
{
    for (Expr* e = args; e; e = e->next)
        fprintf(fp, "    %-10s  dim%d_;   /* %-10s */\n",
                "size_t", e->input_label, e->value);
}


static void cpp_declare_dim_args_var(FILE* fp, Var* vars)
{
    for (Var* v = vars; v; v = v->next)
        if (v->qual)
            cpp_declare_dim_args_expr(fp, v->qual->args);
}


static void cpp_declare_args(FILE* fp, Func* f)
{
    if (f->thisv) {
        char tb[256];
        snprintf(tb, sizeof(tb), "%s*", f->classv);
        fprintf(fp, "    %-10s  in0_ =0; /* %-10s */\n", tb, f->thisv);
    }
    cpp_declare_in_args(fp, f->args);
    if (!nullable_return(f))
        cpp_declare_out_args(fp, f->ret);
    cpp_declare_out_args(fp, f->args);
    cpp_declare_dim_args_var(fp, f->ret);
    cpp_declare_dim_args_var(fp, f->args);
    if (f->ret || f->args || f->thisv)
        fprintf(fp, "\n");
}


/* -- Unpack dims (C++ MEX API version) -- */

static int cpp_unpack_dims_expr(FILE* fp, Expr* args)
{
    int count = 0;
    for (Expr* e = args; e; e = e->next) {
        fprintf(fp,
                "    dim%d_ = (size_t) mwCppGetScalar(args[%d], &mw_err_txt_);\n",
                e->input_label, e->input_label);
        count++;
    }
    return count;
}


static int cpp_unpack_dims_var(FILE* fp, Var* vars)
{
    int count = 0;
    for (Var* v = vars; v; v = v->next)
        if (v->qual)
            count += cpp_unpack_dims_expr(fp, v->qual->args);
    return count;
}


static void cpp_unpack_dims(FILE* fp, Func* f)
{
    int c = cpp_unpack_dims_var(fp, f->ret) + cpp_unpack_dims_var(fp, f->args);
    if (c)
        fprintf(fp, "\n");
}


/* -- Check dim consistency (C++ MEX API version) -- */

static void cpp_check_dims(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec != 'o' && (!v->nocopy || v->iospec == 'b') &&
            is_array(v->tinfo) && v->qual && v->qual->args) {
            Expr* a = v->qual->args;
            if (a->next) {
                fprintf(fp,
                        "    if (args[%d].getDimensions()[0] != dim%d_ ||\n"
                        "        args[%d].getDimensions()[1] != dim%d_) {\n"
                        "        mw_err_txt_ = \"Bad argument size: %s\";\n"
                        "        goto mw_err_label;\n"
                        "    }\n\n",
                        v->input_label, a->input_label,
                        v->input_label, a->next->input_label,
                        v->name);
            } else {
                fprintf(fp,
                        "    if (args[%d].getNumberOfElements() != dim%d_) {\n"
                        "        mw_err_txt_ = \"Bad argument size: %s\";"
                        "        goto mw_err_label;\n"
                        "    }\n\n",
                        v->input_label, a->input_label,
                        v->name);
            }
        }
    }
}


/* -- Unpack inputs (C++ MEX API version) -- */

static void cpp_cast_get_p(FILE* fp, const char* basetype, int input_label)
{
    fprintf(fp, "    in%d_ = ", input_label);
    if (class_decls.find(basetype) == class_decls.end())
        fprintf(fp, "(%s*) mwCppGetP(args[%d], \"%s:%%p\", &mw_err_txt_);\n",
                basetype, input_label, basetype);
    else
        fprintf(fp, "mwCppGetP_%s(args[%d], &mw_err_txt_);\n",
                basetype, input_label);
    fprintf(fp,
            "    if (mw_err_txt_)\n"
            "        goto mw_err_label;\n\n");
}


static void cpp_unpack_input_array(FILE* fp, Var* v)
{
    int il = v->input_label;
    const char* bt = v->basetype;
    const CppTypeProps* tp = cpp_type_props(bt);

    /* --- Nocopy path --- */
    if (v->nocopy && v->iospec != 'b' && cpp_is_known_type(bt)) {
        CppComplexInfo zinfo;
        if (get_cpp_complex_info(v, &zinfo)) {
            /* Complex nocopy: auto-promote real to complex */
            const char* ate = zinfo.array_type_enum;
            const char* st = zinfo.scalar_type;
            const char* ta = zinfo.typed_array;
            const char* real_ate;
            const char* real_ta;
            if (v->tinfo == VT_zarray) {
                real_ate = "ArrayType::DOUBLE";
                real_ta = "TypedArray<double>";
            } else {
                real_ate = "ArrayType::SINGLE";
                real_ta = "TypedArray<float>";
            }
            fprintf(fp, "    if (args[%d].getNumberOfElements() != 0) {\n", il);
            fprintf(fp,
                    "        if (args[%d].getType() == %s) {\n"
                    "            ta_nc_in%d_ = std::make_unique<%s>(args[%d]);\n"
                    "            in%d_ = (%s*) &(*ta_nc_in%d_->begin());\n"
                    "        } else if (args[%d].getType() == %s) {\n"
                    "            %s ta_real_ = args[%d];\n"
                    "            vec_in%d_.reserve(ta_real_.getNumberOfElements());\n"
                    "            for (auto v_ : ta_real_) vec_in%d_.push_back(%s(v_, 0));\n"
                    "            in%d_ = (%s*) vec_in%d_.data();\n"
                    "        } else {\n"
                    "            mw_err_txt_ = \"Invalid array argument, numeric type expected\";\n"
                    "            goto mw_err_label;\n"
                    "        }\n",
                    il, ate,
                    il, ta, il,
                    il, bt, il,
                    il, real_ate,
                    real_ta, il,
                    il,
                    il, st,
                    il, bt, il);
        } else {
            /* Non-complex nocopy: strict type check */
            const char* ate = tp->array_type_enum;
            const char* ta = tp->typed_array;
            fprintf(fp, "    if (args[%d].getNumberOfElements() != 0) {\n", il);
            fprintf(fp,
                    "        if (args[%d].getType() != %s) {\n"
                    "            mw_err_txt_ = \"Invalid array argument, %s expected\";\n"
                    "            goto mw_err_label;\n"
                    "        }\n",
                    il, ate, ate);
            fprintf(fp, "        ta_nc_in%d_ = std::make_unique<%s>(args[%d]);\n", il, ta, il);
            fprintf(fp, "        in%d_ = (%s*) &(*ta_nc_in%d_->begin());\n", il, bt, il);
        }
        fprintf(fp,
                "    } else\n"
                "        in%d_ = NULL;\n\n", il);
        return;
    }

    /* --- Regular (copy) path --- */
    fprintf(fp, "    if (args[%d].getNumberOfElements() != 0) {\n", il);

    CppComplexInfo zinfo;
    if (get_cpp_complex_info(v, &zinfo)) {
        /* Complex array: auto-promote real to complex */
        const char* ate = zinfo.array_type_enum;
        const char* st = zinfo.scalar_type;
        const char* ta = zinfo.typed_array;
        const char* real_ate;
        const char* real_ta;
        if (v->tinfo == VT_zarray) {
            real_ate = "ArrayType::DOUBLE";
            real_ta = "TypedArray<double>";
        } else {
            real_ate = "ArrayType::SINGLE";
            real_ta = "TypedArray<float>";
        }
        fprintf(fp,
                "        if (args[%d].getType() == %s) {\n"
                "            %s ta_in%d_ = args[%d];\n"
                "            vec_in%d_.assign(ta_in%d_.begin(), ta_in%d_.end());\n"
                "            in%d_ = (%s*) vec_in%d_.data();\n"
                "        } else if (args[%d].getType() == %s) {\n"
                "            %s ta_real_ = args[%d];\n"
                "            vec_in%d_.reserve(ta_real_.getNumberOfElements());\n"
                "            for (auto v_ : ta_real_) vec_in%d_.push_back(%s(v_, 0));\n"
                "            in%d_ = (%s*) vec_in%d_.data();\n"
                "        } else {\n"
                "            mw_err_txt_ = \"Invalid array argument, numeric type expected\";\n"
                "            goto mw_err_label;\n"
                "        }\n",
                il, ate,
                ta, il, il,
                il, il, il,
                il, bt, il,
                il, real_ate,
                real_ta, il,
                il,
                il, st,
                il, bt, il);
    } else if (cpp_is_known_type(bt)) {
        /* Known scalar types: type check + copy via iterators */
        fprintf(fp,
                "        if (args[%d].getType() != %s) {\n"
                "            mw_err_txt_ = \"Invalid array argument, %s expected\";\n"
                "            goto mw_err_label;\n"
                "        }\n",
                il, tp->array_type_enum, tp->array_type_enum);
        if (strcmp(bt, "char") == 0) {
            /* CharArray needs special handling */
            fprintf(fp, "        CharArray ca_in%d_ = args[%d];\n", il, il);
            fprintf(fp, "        std::string s_in%d_ = ca_in%d_.toAscii();\n", il, il);
            fprintf(fp, "        vec_in%d_.assign(s_in%d_.begin(), s_in%d_.end());\n",
                    il, il, il);
        } else {
            fprintf(fp, "        %s ta_in%d_ = args[%d];\n",
                    tp->typed_array, il, il);
            fprintf(fp, "        vec_in%d_.assign(ta_in%d_.begin(), ta_in%d_.end());\n",
                    il, il, il);
        }
        fprintf(fp, "        in%d_ = (%s*) vec_in%d_.data();\n",
                il, bt, il);
    } else {
        /* Unknown types: copy through double array */
        fprintf(fp, "        TypedArray<double> ta_in%d_ = args[%d];\n", il, il);
        fprintf(fp, "        size_t len_in%d_ = ta_in%d_.getNumberOfElements();\n", il, il);
        fprintf(fp, "        in%d_ = new %s[len_in%d_];\n", il, bt, il);
        fprintf(fp, "        size_t idx_in%d_ = 0;\n", il);
        fprintf(fp, "        for (auto elem_ : ta_in%d_)\n", il);
        fprintf(fp, "            in%d_[idx_in%d_++] = (%s) elem_;\n", il, il, bt);
    }

    fprintf(fp,
            "    } else\n"
            "        in%d_ = NULL;\n", il);
    fprintf(fp, "\n");
}


static void cpp_unpack_input_string(FILE* fp, Var* v)
{
    int il = v->input_label;
    if (!v->qual || !v->qual->args) {
        fprintf(fp,
                "    in%d_ = mwCppGetString(args[%d], &mw_err_txt_);\n"
                "    if (mw_err_txt_)\n"
                "        goto mw_err_label;\n",
                il, il);
    } else {
        fprintf(fp, "    in%d_ = new char[", il);
        cpp_print_alloc_size_expr(fp, v->qual->args);
        fprintf(fp, "];\n");
        fprintf(fp, "    {\n");
        fprintf(fp, "        CharArray ca_ = args[%d];\n", il);
        fprintf(fp, "        std::string s_ = ca_.toAscii();\n");
        fprintf(fp, "        strncpy(in%d_, s_.c_str(), ", il);
        cpp_print_alloc_size_expr(fp, v->qual->args);
        fprintf(fp, ");\n");
        fprintf(fp, "        in%d_[", il);
        cpp_print_alloc_size_expr(fp, v->qual->args);
        fprintf(fp, "-1] = '\\0';\n");
        fprintf(fp, "    }\n");
    }
    fprintf(fp, "\n");
}


static void cpp_unpack_inputs_var(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec == 'o')
            continue;
        if (is_obj(v->tinfo)) {
            cpp_cast_get_p(fp, v->basetype, v->input_label);
        } else if (is_array(v->tinfo)) {
            cpp_unpack_input_array(fp, v);
        } else if (v->tinfo == VT_scalar || v->tinfo == VT_r_scalar ||
                   v->tinfo == VT_p_scalar) {
            int il = v->input_label;
            const char* bt = v->basetype;
            if (strcmp(bt, "char") == 0)
                fprintf(fp, "    in%d_ = (%s) mwCppGetScalar_char(args[%d], &mw_err_txt_);\n",
                        il, bt, il);
            else if (strcmp(bt, "float") == 0)
                fprintf(fp, "    in%d_ = (%s) mwCppGetScalar_single(args[%d], &mw_err_txt_);\n",
                        il, bt, il);
            else
                fprintf(fp, "    in%d_ = (%s) mwCppGetScalar(args[%d], &mw_err_txt_);\n",
                        il, bt, il);
            fprintf(fp,
                    "    if (mw_err_txt_)\n"
                    "        goto mw_err_label;\n");
            if (strcmp(bt, "char") != 0)
                fprintf(fp, "\n");
        } else if (v->tinfo == VT_cscalar || v->tinfo == VT_zscalar ||
                   v->tinfo == VT_r_cscalar || v->tinfo == VT_r_zscalar ||
                   v->tinfo == VT_p_cscalar || v->tinfo == VT_p_zscalar) {
            int il = v->input_label;
            const char* bt = v->basetype;
            if (strcmp(bt, "fcomplex") == 0) {
                fprintf(fp, "    {\n");
                fprintf(fp, "        TypedArray<std::complex<float>> ta_ = args[%d];\n", il);
                fprintf(fp, "        in%d_ = (%s) ta_[0];\n", il, bt);
                fprintf(fp, "    }\n\n");
            } else {
                fprintf(fp, "    {\n");
                fprintf(fp, "        TypedArray<std::complex<double>> ta_ = args[%d];\n", il);
                fprintf(fp, "        in%d_ = (%s) ta_[0];\n", il, bt);
                fprintf(fp, "    }\n\n");
            }
        } else if (v->tinfo == VT_string) {
            cpp_unpack_input_string(fp, v);
        } else if (v->tinfo == VT_mx) {
            fprintf(fp, "    in%d_ = args[%d];\n\n",
                    v->input_label, v->input_label);
        }
    }
}


static void cpp_unpack_inputs(FILE* fp, Func* f)
{
    if (f->thisv)
        cpp_cast_get_p(fp, f->classv, 0);
    cpp_unpack_inputs_var(fp, f->args);
}


/* -- Null-check objects/this -- */

static void cpp_check_inputs(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec != 'o' && (v->tinfo == VT_obj || v->tinfo == VT_r_obj))
            fprintf(fp,
                    "    if (!in%d_) {\n"
                    "        mw_err_txt_ = \"Argument %s cannot be null\";\n"
                    "        goto mw_err_label;\n"
                    "    }\n",
                    v->input_label, v->name);
    }
}


/* -- Allocate outputs (C++ MEX API version) -- */

static void cpp_alloc_output(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->nocopy && v->iospec == 'o') {
            /* Nocopy output: allocate MATLAB buffer directly */
            if (is_array(v->tinfo) && cpp_is_known_type(v->basetype)) {
                const CppTypeProps* tp = cpp_type_props(v->basetype);
                CppComplexInfo zinfo;
                const char* st;
                if (get_cpp_complex_info(v, &zinfo))
                    st = zinfo.scalar_type;
                else
                    st = tp->scalar_type;
                fprintf(fp, "    buf_out%d_ = factory.createBuffer<%s>(",
                        v->output_label, st);
                cpp_print_alloc_size_expr(fp, v->qual->args);
                fprintf(fp, ");\n");
                fprintf(fp, "    out%d_ = (%s*) buf_out%d_.get();\n",
                        v->output_label, v->basetype, v->output_label);
            } else if (is_array(v->tinfo)) {
                /* Unknown type: fall back to regular alloc */
                fprintf(fp, "    out%d_ = new %s[", v->output_label, v->basetype);
                cpp_print_alloc_size_expr(fp, v->qual->args);
                fprintf(fp, "];\n");
            }
        } else if (!v->nocopy && v->iospec == 'o') {
            if (is_array(v->tinfo)) {
                fprintf(fp, "    out%d_ = new %s[", v->output_label, v->basetype);
                cpp_print_alloc_size_expr(fp, v->qual->args);
                fprintf(fp, "];\n");
            } else if (v->tinfo == VT_rarray) {
                fprintf(fp, "    out%d_ = (%s*) NULL;\n",
                        v->output_label, v->basetype);
            } else if (v->tinfo == VT_string) {
                fprintf(fp, "    out%d_ = new char[", v->output_label);
                cpp_print_alloc_size_expr(fp, v->qual->args);
                fprintf(fp, "];\n");
            }
        }
    }
}


static void cpp_alloc_outputs(FILE* fp, Func* f)
{
    if (!nullable_return(f))
        cpp_alloc_output(fp, f->ret);
    cpp_alloc_output(fp, f->args);
}


/* -- Make the call -- */

static void cpp_make_call_args(FILE* fp, Var* args, bool first)
{
    char buf[64];
    for (Var* v = args; v; v = v->next) {
        if (!first)
            fprintf(fp, ", ");
        const char* n = vname(v, buf);
        if (v->tinfo == VT_obj || v->tinfo == VT_r_obj)
            fprintf(fp, "*%s", n);
        else if (v->tinfo == VT_mx && v->iospec == 'o')
            fprintf(fp, "&retval_mx%d_", v->output_label);
        else if (v->tinfo == VT_p_scalar || v->tinfo == VT_p_cscalar ||
                 v->tinfo == VT_p_zscalar)
            fprintf(fp, "&%s", n);
        else if (v->tinfo == VT_const)
            fprintf(fp, "%s", v->name);
        else
            fprintf(fp, "%s", n);
        first = false;
    }
}


static void cpp_make_call_expr(FILE* fp, Func* f)
{
    if (f->thisv)
        fprintf(fp, "in0_->");
    if (strcmp(f->funcv, "new") == 0)
        fprintf(fp, "new %s(", f->classv);
    else {
        if (f->fort)
            fprintf(fp, "MWF77_");
        fprintf(fp, "%s(", f->funcv);
    }
    cpp_make_call_args(fp, f->args, true);
    fprintf(fp, ")");
}


static void cpp_make_stmt(FILE* fp, Func* f)
{
    if (f->thisv)
        fprintf(fp,
                "    if (!in0_) {\n"
                "        mw_err_txt_ = \"Cannot dispatch to NULL\";\n"
                "        goto mw_err_label;\n"
                "    }\n");

    if (mw_generate_catch)
        fprintf(fp, "    try {\n    ");

    if (f->ret) {
        Var* v = f->ret;
        if (v->tinfo == VT_obj) {
            fprintf(fp, "    out0_ = new %s(", v->basetype);
            cpp_make_call_expr(fp, f);
            fprintf(fp, ");\n");
        } else if (is_array(v->tinfo)) {
            fprintf(fp, "    out0_ = (%s*) ", v->basetype);
            cpp_make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_scalar || v->tinfo == VT_r_scalar ||
                   v->tinfo == VT_cscalar || v->tinfo == VT_r_cscalar ||
                   v->tinfo == VT_zscalar || v->tinfo == VT_r_zscalar) {
            fprintf(fp, "    out0_ = ");
            cpp_make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_string) {
            fprintf(fp, "    out0_ = (char*) ");
            cpp_make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_p_obj) {
            fprintf(fp, "    out0_ = ");
            cpp_make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_p_scalar || v->tinfo == VT_p_cscalar ||
                   v->tinfo == VT_p_zscalar) {
            fprintf(fp, "    out0_ = *");
            cpp_make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_mx) {
            fprintf(fp, "    retval[0] = ");
            cpp_make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_r_obj) {
            fprintf(fp, "    out0_ = &(");
            cpp_make_call_expr(fp, f);
            fprintf(fp, ");\n");
        }
    } else {
        fprintf(fp, "    ");
        cpp_make_call_expr(fp, f);
        fprintf(fp, ";\n");
    }

    if (mw_generate_catch)
        fprintf(fp,
                "    } catch(...) {\n"
                "        mw_err_txt_ = \"Caught C++ exception from %s\";\n"
                "    }\n"
                "    if (mw_err_txt_)\n"
                "        goto mw_err_label;\n",
                f->funcv);
}


/* -- Marshal results (C++ MEX API version) -- */

static void cpp_marshal_array(FILE* fp, Var* v)
{
    char nbuf[64];
    int il = v->input_label;
    int ol = v->output_label;
    const char* bt = v->basetype;
    const char* n = vname(v, nbuf);
    const CppTypeProps* tp = cpp_type_props(bt);
    Expr* da = v->qual ? v->qual->args : NULL;

    /* --- Nocopy output: wrap pre-allocated buffer into Array --- */
    if (v->nocopy && v->iospec == 'o' && cpp_is_known_type(bt)) {
        CppComplexInfo zi;
        const char* st_nc;
        if (get_cpp_complex_info(v, &zi))
            st_nc = zi.scalar_type;
        else
            st_nc = tp->scalar_type;

        int ndims_nc = 0;
        for (Expr* e = da; e; e = e->next) ndims_nc++;

        if (ndims_nc == 0) {
            fprintf(fp, "    {\n");
            fprintf(fp, "        size_t nr_ = args[%d].getDimensions()[0];\n", il);
            fprintf(fp, "        size_t nc_ = args[%d].getDimensions()[1];\n", il);
            fprintf(fp, "        retval[%d] = factory.createArrayFromBuffer({nr_, nc_}, std::move(buf_out%d_));\n", ol, ol);
            fprintf(fp, "    }\n");
        } else if (ndims_nc == 1) {
            fprintf(fp, "    retval[%d] = factory.createArrayFromBuffer({dim%d_, 1}, std::move(buf_out%d_));\n",
                    ol, da->input_label, ol);
        } else if (ndims_nc == 2) {
            fprintf(fp, "    retval[%d] = factory.createArrayFromBuffer({dim%d_, dim%d_}, std::move(buf_out%d_));\n",
                    ol, da->input_label, da->next->input_label, ol);
        } else {
            fprintf(fp, "    retval[%d] = factory.createArrayFromBuffer({(", ol);
            cpp_print_alloc_size_expr(fp, da);
            fprintf(fp, "), 1}, std::move(buf_out%d_));\n", ol);
        }
        return;
    }


    /* Determine effective type info for marshalling */
    CppComplexInfo zinfo;
    const char* ate;
    const char* st;
    bool known_type;
    if (get_cpp_complex_info(v, &zinfo)) {
        ate = zinfo.array_type_enum;
        st = zinfo.scalar_type;
        known_type = true;
    } else if (cpp_is_known_type(bt)) {
        ate = tp->array_type_enum;
        st = tp->scalar_type;
        known_type = true;
    } else {
        ate = "ArrayType::DOUBLE";
        st = "double";
        known_type = false;
    }

    const char* ws;
    if (v->tinfo == VT_rarray) {
        fprintf(fp, "    if (out%d_ == NULL) {\n", ol);
        fprintf(fp, "        retval[%d] = factory.createArray<double>({0, 0});\n", ol);
        fprintf(fp, "    } else {\n");
        ws = "        ";
    } else {
        ws = "    ";
    }

    int ndims = 0;
    for (Expr* e = da; e; e = e->next)
        ndims++;

    if (ndims == 0) {
        /* No dims -- inout array: create from original size */
        if (known_type) {
            if (strcmp(bt, "char") == 0) {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    size_t n_ = args[%d].getNumberOfElements();\n", ws, il);
                fprintf(fp, "%s    std::string s_(in%d_, n_);\n", ws, il);
                fprintf(fp, "%s    retval[%d] = factory.createCharArray(s_);\n", ws, ol);
                fprintf(fp, "%s}\n", ws);
            } else {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    size_t nr_ = args[%d].getDimensions()[0];\n", ws, il);
                fprintf(fp, "%s    size_t nc_ = args[%d].getDimensions()[1];\n", ws, il);
                fprintf(fp, "%s    auto buf_ = factory.createBuffer<%s>(nr_*nc_);\n", ws, st);
                fprintf(fp, "%s    std::memcpy(buf_.get(), in%d_, nr_*nc_*sizeof(%s));\n", ws, il, bt);
                fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({nr_, nc_}, std::move(buf_));\n", ws, ol);
                fprintf(fp, "%s}\n", ws);
            }
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    size_t n_ = args[%d].getNumberOfElements();\n", ws, il);
            fprintf(fp, "%s    size_t nr_ = args[%d].getDimensions()[0];\n", ws, il);
            fprintf(fp, "%s    size_t nc_ = args[%d].getDimensions()[1];\n", ws, il);
            fprintf(fp, "%s    auto buf_ = factory.createBuffer<double>(n_);\n", ws);
            fprintf(fp, "%s    double* dst_ = buf_.get();\n", ws);
            fprintf(fp, "%s    for (size_t i_ = 0; i_ < n_; ++i_)\n", ws);
            fprintf(fp, "%s        dst_[i_] = (double) in%d_[i_];\n", ws, il);
            fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({nr_, nc_}, std::move(buf_));\n", ws, ol);
            fprintf(fp, "%s}\n", ws);
        }
    } else if (ndims == 1) {
        /* 1D */
        if (known_type) {
            if (strcmp(bt, "char") == 0) {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    std::string s_(%s, dim%d_);\n", ws, n, da->input_label);
                fprintf(fp, "%s    retval[%d] = factory.createCharArray(s_);\n", ws, ol);
                fprintf(fp, "%s}\n", ws);
            } else {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    auto buf_ = factory.createBuffer<%s>(dim%d_);\n",
                        ws, st, da->input_label);
                fprintf(fp, "%s    std::memcpy(buf_.get(), %s, dim%d_*sizeof(%s));\n",
                        ws, n, da->input_label, bt);
                fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({dim%d_, 1}, std::move(buf_));\n",
                        ws, ol, da->input_label);
                fprintf(fp, "%s}\n", ws);
            }
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    auto buf_ = factory.createBuffer<double>(dim%d_);\n",
                    ws, da->input_label);
            fprintf(fp, "%s    double* dst_ = buf_.get();\n", ws);
            fprintf(fp, "%s    for (size_t i_ = 0; i_ < dim%d_; ++i_)\n",
                    ws, da->input_label);
            fprintf(fp, "%s        dst_[i_] = (double) %s[i_];\n", ws, n);
            fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({dim%d_, 1}, std::move(buf_));\n",
                    ws, ol, da->input_label);
            fprintf(fp, "%s}\n", ws);
        }
    } else if (ndims == 2) {
        /* 2D */
        if (known_type) {
            if (strcmp(bt, "char") == 0) {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    std::string s_(%s, dim%d_*dim%d_);\n",
                        ws, n, da->input_label, da->next->input_label);
                fprintf(fp, "%s    retval[%d] = factory.createCharArray(s_);\n", ws, ol);
                fprintf(fp, "%s}\n", ws);
            } else {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    auto buf_ = factory.createBuffer<%s>(dim%d_*dim%d_);\n",
                        ws, st, da->input_label, da->next->input_label);
                fprintf(fp, "%s    std::memcpy(buf_.get(), %s, dim%d_*dim%d_*sizeof(%s));\n",
                        ws, n, da->input_label, da->next->input_label, bt);
                fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({dim%d_, dim%d_}, std::move(buf_));\n",
                        ws, ol, da->input_label, da->next->input_label);
                fprintf(fp, "%s}\n", ws);
            }
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    auto buf_ = factory.createBuffer<double>(dim%d_*dim%d_);\n",
                    ws, da->input_label, da->next->input_label);
            fprintf(fp, "%s    double* dst_ = buf_.get();\n", ws);
            fprintf(fp, "%s    for (size_t i_ = 0; i_ < dim%d_*dim%d_; ++i_)\n",
                    ws, da->input_label, da->next->input_label);
            fprintf(fp, "%s        dst_[i_] = (double) %s[i_];\n", ws, n);
            fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({dim%d_, dim%d_}, std::move(buf_));\n",
                    ws, ol, da->input_label, da->next->input_label);
            fprintf(fp, "%s}\n", ws);
        }
    } else {
        /* 3D+ -- flatten to 1D */
        if (known_type) {
            if (strcmp(bt, "char") == 0) {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    std::string s_(%s, ", ws, n);
                cpp_print_alloc_size_expr(fp, da);
                fprintf(fp, ");\n");
                fprintf(fp, "%s    retval[%d] = factory.createCharArray(s_);\n", ws, ol);
                fprintf(fp, "%s}\n", ws);
            } else {
                fprintf(fp, "%s{\n", ws);
                fprintf(fp, "%s    auto buf_ = factory.createBuffer<%s>(", ws, st);
                cpp_print_alloc_size_expr(fp, da);
                fprintf(fp, ");\n");
                fprintf(fp, "%s    std::memcpy(buf_.get(), %s, (", ws, n);
                cpp_print_alloc_size_expr(fp, da);
                fprintf(fp, ")*sizeof(%s));\n", bt);
                fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({(", ws, ol);
                cpp_print_alloc_size_expr(fp, da);
                fprintf(fp, "), 1}, std::move(buf_));\n");
                fprintf(fp, "%s}\n", ws);
            }
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    auto buf_ = factory.createBuffer<double>(", ws);
            cpp_print_alloc_size_expr(fp, da);
            fprintf(fp, ");\n");
            fprintf(fp, "%s    double* dst_ = buf_.get();\n", ws);
            fprintf(fp, "%s    for (size_t i_ = 0; i_ < ", ws);
            cpp_print_alloc_size_expr(fp, da);
            fprintf(fp, "; ++i_)\n");
            fprintf(fp, "%s        dst_[i_] = (double) %s[i_];\n", ws, n);
            fprintf(fp, "%s    retval[%d] = factory.createArrayFromBuffer({(", ws, ol);
            cpp_print_alloc_size_expr(fp, da);
            fprintf(fp, "), 1}, std::move(buf_));\n");
            fprintf(fp, "%s}\n", ws);
        }
    }

    if (v->tinfo == VT_rarray)
        fprintf(fp, "    }\n");
}


static void cpp_marshal_result(FILE* fp, Var* v)
{
    char nbuf[64];
    int ol = v->output_label;
    const char* bt = v->basetype;
    const char* n = vname(v, nbuf);

    if (is_obj(v->tinfo)) {
        fprintf(fp, "    retval[%d] = mwCppCreateP(factory, out%d_, \"%s:%%p\");\n",
                ol, ol, bt);
    } else if (is_array(v->tinfo) || v->tinfo == VT_rarray) {
        cpp_marshal_array(fp, v);
    } else if (v->tinfo == VT_scalar || v->tinfo == VT_r_scalar ||
               v->tinfo == VT_p_scalar) {
        fprintf(fp, "    retval[%d] = factory.createScalar<double>((double) %s);\n", ol, n);
    } else if (v->tinfo == VT_cscalar || v->tinfo == VT_zscalar ||
               v->tinfo == VT_r_cscalar || v->tinfo == VT_r_zscalar ||
               v->tinfo == VT_p_cscalar || v->tinfo == VT_p_zscalar) {
        if (strcmp(bt, "fcomplex") == 0)
            fprintf(fp, "    retval[%d] = factory.createScalar<std::complex<float>>(std::complex<float>(real_%s(%s), imag_%s(%s)));\n",
                    ol, bt, n, bt, n);
        else
            fprintf(fp, "    retval[%d] = factory.createScalar<std::complex<double>>(std::complex<double>(real_%s(%s), imag_%s(%s)));\n",
                    ol, bt, n, bt, n);
    } else if (v->tinfo == VT_string) {
        fprintf(fp, "    retval[%d] = mwCppStrncpy(factory, %s);\n", ol, n);
    } else if (v->tinfo == VT_mx) {
        if (v->iospec == 'o')
            fprintf(fp, "    retval[%d] = retval_mx%d_;\n", ol, ol);
    }
}


static void cpp_marshal_results_var(FILE* fp, Var* vars)
{
    for (Var* v = vars; v; v = v->next)
        if (v->iospec != 'i')
            cpp_marshal_result(fp, v);
}


static void cpp_marshal_results(FILE* fp, Func* f)
{
    if (!nullable_return(f))
        cpp_marshal_results_var(fp, f->ret);
    cpp_marshal_results_var(fp, f->args);
}


/* -- Dealloc (C++ MEX API version) -- */

static void cpp_dealloc_var(FILE* fp, Var* vars)
{
    for (Var* v = vars; v; v = v->next) {
        if (is_array(v->tinfo) || v->tinfo == VT_string) {
            if (v->nocopy && v->iospec != 'b') {
                /* Nocopy: MATLAB owns the memory, no dealloc needed.
                 * Exception: unknown types for nocopy output that fell back to new[] */
                if (v->iospec == 'o' && !cpp_is_known_type(v->basetype))
                    fprintf(fp, "    if (out%d_) delete[] out%d_;\n",
                            v->output_label, v->output_label);
            } else if (v->iospec == 'o') {
                fprintf(fp, "    if (out%d_) delete[] out%d_;\n",
                        v->output_label, v->output_label);
            } else if (v->iospec == 'b') {
                /* Inout arrays backed by std::vector don't need dealloc */
                CppComplexInfo zinfo;
                if (!cpp_is_known_type(v->basetype) &&
                    !get_cpp_complex_info(v, &zinfo))
                    fprintf(fp, "    if (in%d_)  delete[] in%d_;\n",
                            v->input_label, v->input_label);
            } else if (v->iospec == 'i') {
                /* Input-only: known types use std::vector, no dealloc needed */
                CppComplexInfo zinfo;
                if (!cpp_is_known_type(v->basetype) &&
                    !get_cpp_complex_info(v, &zinfo))
                    fprintf(fp, "    if (in%d_)  delete[] in%d_;\n",
                            v->input_label, v->input_label);
            }
        }
    }
}


static void cpp_dealloc(FILE* fp, Func* f)
{
    if (!nullable_return(f))
        cpp_dealloc_var(fp, f->ret);
    cpp_dealloc_var(fp, f->args);
}


/* -- Print a single C++ MEX API stub -- */

static void cpp_print_c_comment(FILE* fp, Func* f)
{
    fprintf(fp, "/* ---- %s: %d ----\n * ", f->fname.c_str(), f->line);
    print(fp, f);
    for (Func* fsame = f->same_next; fsame; fsame = fsame->same_next)
        fprintf(fp, " * Also at %s: %d\n", fsame->fname.c_str(), fsame->line);
    fprintf(fp, " */\n");
}


static int cpp_count_outputs(Func* f)
{
    int nout = 0;
    if (f->ret && !nullable_return(f)) {
        for (Var* v = f->ret; v; v = v->next)
            if (v->output_label + 1 > nout)
                nout = v->output_label + 1;
    }
    for (Var* v = f->args; v; v = v->next)
        if ((v->iospec == 'o' || v->iospec == 'b') &&
            v->output_label + 1 > nout)
            nout = v->output_label + 1;
    return nout;
}


static void print_cpp_stub(FILE* fp, Func* f)
{
    cpp_print_c_comment(fp, f);
    string ids = id_string(f);
    fprintf(fp, "static const char* stubids%d_ = \"%s\";\n\n",
            f->id, ids.c_str());

    fprintf(fp,
            "static void cppStub%d(ArrayFactory& factory,\n"
            "    const std::vector<Array>& args, std::vector<Array>& retval, int nargout)\n"
            "{\n"
            "    const char* mw_err_txt_ = 0;\n",
            f->id);
    cpp_declare_args(fp, f);
    cpp_unpack_dims(fp, f);
    cpp_check_dims(fp, f->args);
    cpp_unpack_inputs(fp, f);
    cpp_check_inputs(fp, f->args);
    cpp_alloc_outputs(fp, f);
    cpp_make_stmt(fp, f);
    cpp_marshal_results(fp, f);
    fprintf(fp, "\nmw_err_label:\n");
    cpp_dealloc(fp, f);
    fprintf(fp,
            "    if (mw_err_txt_)\n"
            "        throw std::runtime_error(mw_err_txt_);\n"
            "}\n\n");
}


/* -- Print all stubs, dispatch table, gateway -- */

static void print_cpp_stubs(FILE* fp, Func* f)
{
    for (; f; f = f->next)
        print_cpp_stub(fp, f);
}


static void print_cpp_stub_table(FILE* fp, Func* f)
{
    int maxid = 0;
    map<int, int> id_to_stub;
    for (Func* fcall = f; fcall; fcall = fcall->next) {
        id_to_stub[fcall->id] = fcall->id;
        if (fcall->id > maxid) maxid = fcall->id;
        for (Func* fsame = fcall->same_next; fsame; fsame = fsame->same_next) {
            id_to_stub[fsame->id] = fcall->id;
            if (fsame->id > maxid) maxid = fsame->id;
        }
    }

    if (maxid <= 0)
        return;

    fprintf(fp,
            "typedef void (*CppStubFunc_t)(ArrayFactory&, const std::vector<Array>&,\n"
            "                               std::vector<Array>&, int);\n\n"
            "static CppStubFunc_t mwStubs_[] = {\n"
            "    NULL");
    for (int i = 1; i <= maxid; i++) {
        fprintf(fp, ",\n");
        map<int,int>::iterator it = id_to_stub.find(i);
        if (it != id_to_stub.end())
            fprintf(fp, "    cppStub%d", it->second);
        else
            fprintf(fp, "    NULL");
    }
    fprintf(fp, "\n};\n\n");
    fprintf(fp, "static int mwNumStubs_ = %d;\n\n", maxid);
}


static void print_cpp_else_cases(FILE* fp, Func* f)
{
    for (Func* fcall = f; fcall; fcall = fcall->next)
        fprintf(fp,
                "        else if (id == stubids%d_)\n"
                "            cppStub%d(factory_, sub_args, out, nargout);\n",
                fcall->id, fcall->id);
    fprintf(fp,
            "        else\n"
            "            throw std::runtime_error(\"Unknown identifier\");\n");
}


/* -- Top-level: print_cpp_init + print_cpp_file -- */

static const char* mwrap_cpp_banner =
    "/* --------------------------------------------------- */\n"
    "/* Automatically generated by mwrap (cppmex backend)    */\n"
    "/* --------------------------------------------------- */\n\n";


void print_cpp_init(FILE* fp)
{
    fprintf(fp, "%s", mwrap_cpp_banner);
    fprintf(fp, "%s", cpp_header);
    fprintf(fp, "\n");
    /* C++ MEX files always use C++ complex */
    if (mw_use_c99_complex || mw_use_cpp_complex)
        cpp_cpp_complex(fp);
}


void print_cpp_file(FILE* fp, Func* f, const char* cppfunc)
{
    if (mw_use_int32_t || mw_use_int64_t || mw_use_uint32_t || mw_use_uint64_t)
        fprintf(fp, "#include <stdint.h>\n\n");

    cpp_casting_getters(fp);

    if (has_fortran(f)) {
        cpp_define_fnames(fp, f);
        cpp_fortran_decls(fp, f);
    }

    print_cpp_stubs(fp, f);
    print_cpp_stub_table(fp, f);

    /* Gateway class */
    fprintf(fp,
            "class MexFunction : public matlab::mex::Function {\n"
            "    ArrayFactory factory_;\n"
            "public:\n"
            "    void operator()(matlab::mex::ArgumentList outputs,\n"
            "                    matlab::mex::ArgumentList inputs) {\n"
            "        int nargout = (int) outputs.size();\n\n"
            "        if (inputs.size() == 0) {\n"
            "            std::shared_ptr<matlab::engine::MATLABEngine> matlabPtr = getEngine();\n"
            "            matlabPtr->feval(u\"fprintf\", 0,\n"
            "                std::vector<Array>({factory_.createScalar(u\"C++ MEX installed\\n\")}));\n"
            "            return;\n"
            "        }\n\n"
            "        /* Fast path: integer stub ID */\n"
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
            "                ; /* placeholder for else-if chain */\n");

    print_cpp_else_cases(fp, f);

    fprintf(fp,
            "            for (size_t i = 0; i < out.size() && i < outputs.size(); ++i)\n"
            "                outputs[i] = out[i];\n"
            "            return;\n"
            "        }\n\n"
            "        throw std::runtime_error(\"First argument must be function ID (integer or string)\");\n"
            "    }\n"
            "};\n\n");
}
