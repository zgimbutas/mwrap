/*
 * mwrap-octgen.cc
 *   Generate Octave oct-file C++ code from MWrap AST.
 *
 * Copyright (c) 2007  David Bindel
 * See the file COPYING for copying permissions
 *
 * Oct-file backend by Zydrunas Gimbutas (2026),
 * with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <cassert>
#include "mwrap-ast.h"
#include "mwrap-oct-support.h"


/* -- Oct-file type property table -- */

struct OctTypeProps {
    const char* matrix_type;     /* "Matrix", "FloatMatrix", etc. */
    const char* array_getter;    /* "matrix_value", "float_matrix_value", etc. */
    const char* scalar_getter;   /* "double_value", "float_value", etc. */
    const char* type_check;      /* "is_double_type", "is_single_type", etc. */
    const char* scalar_type;     /* C scalar type: "double", "float", etc. */
    const char* numeric_create;  /* Octave type constructor */
};

static const OctTypeProps oct_default_props =
    {"Matrix", "matrix_value", "double_value",
     "is_double_type", "double", "Matrix"};

struct OctTypeEntry {
    const char* name;
    OctTypeProps props;
};

static const OctTypeEntry oct_type_table[] = {
    {"double",   {"Matrix",             "matrix_value",               "double_value",          "is_double_type",  "double",               "Matrix"}},
    {"float",    {"FloatMatrix",        "float_matrix_value",         "float_value",           "is_single_type",  "float",                "FloatMatrix"}},
    {"int32_t",  {"int32NDArray",       "int32_array_value",          "int_value",             "is_int32_type",   "int32_t",              "int32NDArray"}},
    {"int64_t",  {"int64NDArray",       "int64_array_value",          "int64_value",           "is_int64_type",   "int64_t",              "int64NDArray"}},
    {"uint32_t", {"uint32NDArray",      "uint32_array_value",         "uint_value",            "is_uint32_type",  "uint32_t",             "uint32NDArray"}},
    {"uint64_t", {"uint64NDArray",      "uint64_array_value",         "uint64_value",          "is_uint64_type",  "uint64_t",             "uint64NDArray"}},
    {"dcomplex", {"ComplexMatrix",      "complex_matrix_value",       "complex_value",         "iscomplex",       "std::complex<double>", "ComplexMatrix"}},
    {"fcomplex", {"FloatComplexMatrix", "float_complex_matrix_value", "float_complex_value",   "is_single_type",  "std::complex<float>",  "FloatComplexMatrix"}},
    {"char",     {"charMatrix",         "char_matrix_value",          "string_value",          "is_string",       "char",                 "charMatrix"}},
    {NULL, {NULL, NULL, NULL, NULL, NULL, NULL}}
};


static const OctTypeProps* oct_type_props(const char* name)
{
    for (const OctTypeEntry* e = oct_type_table; e->name; ++e)
        if (strcmp(e->name, name) == 0)
            return &e->props;
    return &oct_default_props;
}


static bool oct_is_known_type(const char* name)
{
    for (const OctTypeEntry* e = oct_type_table; e->name; ++e)
        if (strcmp(e->name, name) == 0)
            return true;
    return false;
}


/* -- Complex type definitions (always C++ for oct-files) -- */

static void oct_cpp_complex(FILE* fp)
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

static void print_alloc_size_expr(FILE* fp, Expr* args)
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

static void oct_define_fnames(FILE* fp, Func* funcs)
{
    /* Collect unique fortran function names */
    set<string> seen;

    fprintf(fp, "#if defined(MWF77_CAPS)\n");
    for (Func* f = funcs; f; f = f->next) {
        if (f->fort && seen.find(f->funcv) == seen.end()) {
            seen.insert(f->funcv);
            /* upper case */
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


static void oct_fortran_decls(FILE* fp, Func* funcs)
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


/* -- Class polymorphism getters (oct-file version) -- */

static void oct_casting_getter_type(FILE* fp, const char* name)
{
    fprintf(fp,
            "    %s* p_%s = NULL;\n"
            "    sscanf(pbuf, \"%s:%%p\", &p_%s);\n"
            "    if (p_%s)\n"
            "        return p_%s;\n\n",
            name, name, name, name, name, name);
}


static void oct_casting_getter(FILE* fp, const char* cname, InheritsDecl* inherits)
{
    fprintf(fp,
            "\nstatic %s* mwOctGetP_%s(const octave_value& a, const char** e)\n"
            "{\n"
            "    if (a.is_double_type() && a.numel() == 1 && a.double_value() == 0)\n"
            "        return NULL;\n"
            "    if (!a.is_string()) {\n"
            "        *e = \"Invalid pointer\";\n"
            "        return NULL;\n"
            "    }\n"
            "    char pbuf[128];\n"
            "    std::string s = a.string_value();\n"
            "    strncpy(pbuf, s.c_str(), sizeof(pbuf)-1);\n"
            "    pbuf[sizeof(pbuf)-1] = '\\0';\n\n",
            cname, cname);

    oct_casting_getter_type(fp, cname);
    for (InheritsDecl* d = inherits; d; d = d->next)
        oct_casting_getter_type(fp, d->name);

    fprintf(fp,
            "    *e = \"Invalid pointer to %s\";\n"
            "    return NULL;\n"
            "}\n\n", cname);
}


static void oct_casting_getters(FILE* fp)
{
    for (map<string, InheritsDecl*>::iterator it = class_decls.begin();
         it != class_decls.end(); ++it)
        oct_casting_getter(fp, it->first.c_str(), it->second);
}


/* -- Complex array info helper -- */

struct ComplexMatrixInfo {
    const char* matrix_type;
    const char* array_getter;
    const char* type_check;
};

static bool get_complex_matrix_info(Var* v, ComplexMatrixInfo* info)
{
    if (!complex_tinfo(v))
        return false;
    if (v->tinfo == VT_zarray) {
        info->matrix_type = "ComplexMatrix";
        info->array_getter = "complex_matrix_value";
        info->type_check = "iscomplex";
        return true;
    }
    if (v->tinfo == VT_carray) {
        info->matrix_type = "FloatComplexMatrix";
        info->array_getter = "float_complex_matrix_value";
        info->type_check = "is_single_type";
        return true;
    }
    return false;
}


/* -- Per-stub helpers: declarations -- */

static const char* declare_type(Var* v)
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
        return "octave_value";
    assert(0 && "Unknown tinfo in declare_type");
    return "void";
}


static void declare_in_args(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec != 'o' && v->tinfo != VT_const) {
            const char* tb = declare_type(v);
            if (is_array(v->tinfo) || is_obj(v->tinfo) || v->tinfo == VT_string) {
                fprintf(fp, "    %-10s  in%d_ =0; /* %-10s */\n",
                        tb, v->input_label, v->name);
                /* For arrays backed by Octave Matrix, declare the Matrix at function scope */
                if (is_array(v->tinfo)) {
                    ComplexMatrixInfo zinfo;
                    if (get_complex_matrix_info(v, &zinfo)) {
                        fprintf(fp, "    %s  mat_in%d_;\n",
                                zinfo.matrix_type, v->input_label);
                    } else if (oct_is_known_type(v->basetype)) {
                        const OctTypeProps* tp = oct_type_props(v->basetype);
                        fprintf(fp, "    %s  mat_in%d_;\n",
                                tp->matrix_type, v->input_label);
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


static void declare_out_args(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec == 'o') {
            if (v->tinfo == VT_mx) {
                fprintf(fp, "    octave_value  retval_mx%d_;   /* %-10s */\n",
                        v->output_label, v->name);
                continue;
            }
            const char* tb = declare_type(v);
            if (is_array(v->tinfo) || is_obj(v->tinfo) || v->tinfo == VT_string)
                fprintf(fp, "    %-10s  out%d_=0; /* %-10s */\n",
                        tb, v->output_label, v->name);
            else
                fprintf(fp, "    %-10s  out%d_;   /* %-10s */\n",
                        tb, v->output_label, v->name);
            /* Nocopy output: declare backing Matrix at function scope */
            if (v->nocopy && is_array(v->tinfo)) {
                ComplexMatrixInfo zinfo;
                if (get_complex_matrix_info(v, &zinfo))
                    fprintf(fp, "    %s  mat_out%d_;\n",
                            zinfo.matrix_type, v->output_label);
                else if (oct_is_known_type(v->basetype))
                    fprintf(fp, "    %s  mat_out%d_;\n",
                            oct_type_props(v->basetype)->matrix_type,
                            v->output_label);
            }
        }
    }
}


static void declare_dim_args_expr(FILE* fp, Expr* args)
{
    for (Expr* e = args; e; e = e->next)
        fprintf(fp, "    %-10s  dim%d_;   /* %-10s */\n",
                "octave_idx_type", e->input_label, e->value);
}


static void declare_dim_args_var(FILE* fp, Var* vars)
{
    for (Var* v = vars; v; v = v->next)
        if (v->qual)
            declare_dim_args_expr(fp, v->qual->args);
}


static void declare_args(FILE* fp, Func* f)
{
    if (f->thisv) {
        char tb[256];
        snprintf(tb, sizeof(tb), "%s*", f->classv);
        fprintf(fp, "    %-10s  in0_ =0; /* %-10s */\n", tb, f->thisv);
    }
    declare_in_args(fp, f->args);
    if (!nullable_return(f))
        declare_out_args(fp, f->ret);
    declare_out_args(fp, f->args);
    declare_dim_args_var(fp, f->ret);
    declare_dim_args_var(fp, f->args);
    if (f->ret || f->args || f->thisv)
        fprintf(fp, "\n");
}


/* -- Unpack dims (oct-file version) -- */

static int unpack_dims_expr(FILE* fp, Expr* args)
{
    int count = 0;
    for (Expr* e = args; e; e = e->next) {
        fprintf(fp,
                "    dim%d_ = (octave_idx_type) mwOctGetScalar(args(%d), &mw_err_txt_);\n",
                e->input_label, e->input_label);
        count++;
    }
    return count;
}


static int unpack_dims_var(FILE* fp, Var* vars)
{
    int count = 0;
    for (Var* v = vars; v; v = v->next)
        if (v->qual)
            count += unpack_dims_expr(fp, v->qual->args);
    return count;
}


static void unpack_dims(FILE* fp, Func* f)
{
    int c = unpack_dims_var(fp, f->ret) + unpack_dims_var(fp, f->args);
    if (c)
        fprintf(fp, "\n");
}


/* -- Check dim consistency (oct-file version) -- */

static void check_dims(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec != 'o' && is_array(v->tinfo) &&
            v->qual && v->qual->args) {
            Expr* a = v->qual->args;
            if (a->next) {
                fprintf(fp,
                        "    if (args(%d).rows() != dim%d_ ||\n"
                        "        args(%d).columns() != dim%d_) {\n"
                        "        mw_err_txt_ = \"Bad argument size: %s\";\n"
                        "        goto mw_err_label;\n"
                        "    }\n\n",
                        v->input_label, a->input_label,
                        v->input_label, a->next->input_label,
                        v->name);
            } else {
                fprintf(fp,
                        "    if (args(%d).numel() != dim%d_) {\n"
                        "        mw_err_txt_ = \"Bad argument size: %s\";"
                        "        goto mw_err_label;\n"
                        "    }\n\n",
                        v->input_label, a->input_label,
                        v->name);
            }
        }
    }
}


/* -- Unpack inputs (oct-file version) -- */

static void cast_get_p(FILE* fp, const char* basetype, int input_label)
{
    fprintf(fp, "    in%d_ = ", input_label);
    if (class_decls.find(basetype) == class_decls.end())
        fprintf(fp, "(%s*) mwOctGetP(args(%d), \"%s:%%p\", &mw_err_txt_);\n",
                basetype, input_label, basetype);
    else
        fprintf(fp, "mwOctGetP_%s(args(%d), &mw_err_txt_);\n",
                basetype, input_label);
    fprintf(fp,
            "    if (mw_err_txt_)\n"
            "        goto mw_err_label;\n\n");
}


static void unpack_input_array(FILE* fp, Var* v)
{
    int il = v->input_label;
    const char* bt = v->basetype;
    const OctTypeProps* tp = oct_type_props(bt);

    fprintf(fp, "    if (args(%d).numel() != 0) {\n", il);

    ComplexMatrixInfo zinfo;
    if (get_complex_matrix_info(v, &zinfo)) {
        /* Complex array: auto-promote real to complex when needed.
         * Octave's iscomplex() returns false for arrays whose imaginary
         * part is all-zero (unlike MATLAB), so we accept real arrays
         * and promote them. */
        const char* real_type_check;
        const char* real_getter;
        if (v->tinfo == VT_carray) {
            /* fcomplex: checker is is_single_type (precision, not complexity) */
            real_type_check = "is_single_type";
            real_getter = "float_matrix_value";
        } else {
            /* dcomplex: need explicit real-to-complex promotion */
            real_type_check = "is_double_type";
            real_getter = "matrix_value";
        }
        fprintf(fp,
                "        if (args(%d).%s()) {\n"
                "            mat_in%d_ = args(%d).%s();\n"
                "        } else if (args(%d).%s()) {\n"
                "            mat_in%d_ = %s(args(%d).%s());\n"
                "        } else {\n"
                "            mw_err_txt_ = \"Invalid array argument, numeric type expected\";\n"
                "            goto mw_err_label;\n"
                "        }\n",
                il, zinfo.type_check,
                il, il, zinfo.array_getter,
                il, real_type_check,
                il, zinfo.matrix_type, il, real_getter);
        if (v->iospec == 'i')
            fprintf(fp, "        in%d_ = (%s*) mat_in%d_.data();\n",
                    il, bt, il);
        else
            fprintf(fp, "        in%d_ = (%s*) mat_in%d_.fortran_vec();\n",
                    il, bt, il);
    } else if (oct_is_known_type(bt)) {
        /* Known scalar types: type check + matrix_value */
        fprintf(fp,
                "        if (!args(%d).%s()) {\n"
                "            mw_err_txt_ = \"Invalid array argument, %s expected\";\n"
                "            goto mw_err_label;\n"
                "        }\n",
                il, tp->type_check, tp->type_check);
        if (v->iospec == 'i') {
            fprintf(fp, "        mat_in%d_ = args(%d).%s();\n",
                    il, il, tp->array_getter);
            fprintf(fp, "        in%d_ = (%s*) mat_in%d_.data();\n",
                    il, bt, il);
        } else {
            fprintf(fp, "        mat_in%d_ = args(%d).%s();\n",
                    il, il, tp->array_getter);
            fprintf(fp, "        in%d_ = (%s*) mat_in%d_.fortran_vec();\n",
                    il, bt, il);
        }
    } else {
        /* Unknown types: copy through double matrix */
        fprintf(fp, "        Matrix mat_in%d_ = args(%d).matrix_value();\n", il, il);
        fprintf(fp, "        octave_idx_type len_in%d_ = mat_in%d_.numel();\n", il, il);
        fprintf(fp, "        in%d_ = new %s[len_in%d_];\n", il, bt, il);
        fprintf(fp, "        const double* src_in%d_ = mat_in%d_.data();\n", il, il);
        fprintf(fp, "        for (octave_idx_type i_ = 0; i_ < len_in%d_; ++i_)\n", il);
        fprintf(fp, "            in%d_[i_] = (%s) src_in%d_[i_];\n", il, bt, il);
    }

    fprintf(fp,
            "    } else\n"
            "        in%d_ = NULL;\n", il);
    fprintf(fp, "\n");
}


static void unpack_input_string(FILE* fp, Var* v)
{
    int il = v->input_label;
    if (!v->qual || !v->qual->args) {
        fprintf(fp,
                "    in%d_ = mwOctGetString(args(%d), &mw_err_txt_);\n"
                "    if (mw_err_txt_)\n"
                "        goto mw_err_label;\n",
                il, il);
    } else {
        fprintf(fp, "    in%d_ = new char[", il);
        print_alloc_size_expr(fp, v->qual->args);
        fprintf(fp, "];\n");
        fprintf(fp, "    {\n");
        fprintf(fp, "        std::string s_ = args(%d).string_value();\n", il);
        fprintf(fp, "        strncpy(in%d_, s_.c_str(), ", il);
        print_alloc_size_expr(fp, v->qual->args);
        fprintf(fp, ");\n");
        fprintf(fp, "        in%d_[", il);
        print_alloc_size_expr(fp, v->qual->args);
        fprintf(fp, "-1] = '\\0';\n");
        fprintf(fp, "    }\n");
    }
    fprintf(fp, "\n");
}


static void unpack_inputs_var(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec == 'o')
            continue;
        if (is_obj(v->tinfo)) {
            cast_get_p(fp, v->basetype, v->input_label);
        } else if (is_array(v->tinfo)) {
            unpack_input_array(fp, v);
        } else if (v->tinfo == VT_scalar || v->tinfo == VT_r_scalar ||
                   v->tinfo == VT_p_scalar) {
            int il = v->input_label;
            const char* bt = v->basetype;
            if (strcmp(bt, "char") == 0)
                fprintf(fp, "    in%d_ = (%s) mwOctGetScalar_char(args(%d), &mw_err_txt_);\n",
                        il, bt, il);
            else if (strcmp(bt, "float") == 0)
                fprintf(fp, "    in%d_ = (%s) mwOctGetScalar_single(args(%d), &mw_err_txt_);\n",
                        il, bt, il);
            else
                fprintf(fp, "    in%d_ = (%s) mwOctGetScalar(args(%d), &mw_err_txt_);\n",
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
            if (strcmp(bt, "fcomplex") == 0)
                fprintf(fp, "    in%d_ = (%s) args(%d).float_complex_value();\n\n",
                        il, bt, il);
            else
                fprintf(fp, "    in%d_ = (%s) args(%d).complex_value();\n\n",
                        il, bt, il);
        } else if (v->tinfo == VT_string) {
            unpack_input_string(fp, v);
        } else if (v->tinfo == VT_mx) {
            fprintf(fp, "    in%d_ = args(%d);\n\n",
                    v->input_label, v->input_label);
        }
    }
}


static void unpack_inputs(FILE* fp, Func* f)
{
    if (f->thisv)
        cast_get_p(fp, f->classv, 0);
    unpack_inputs_var(fp, f->args);
}


/* -- Null-check objects/this -- */

static void check_inputs(FILE* fp, Var* args)
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


/* -- Allocate outputs (oct-file version) -- */

static void alloc_output(FILE* fp, Var* args)
{
    for (Var* v = args; v; v = v->next) {
        if (v->iospec == 'o') {
            if (v->nocopy && is_array(v->tinfo)) {
                /* Nocopy output: allocate backing Matrix, point into its data */
                ComplexMatrixInfo zinfo;
                const char* eff_mat_type;
                bool known = false;
                if (get_complex_matrix_info(v, &zinfo)) {
                    eff_mat_type = zinfo.matrix_type;
                    known = true;
                } else if (oct_is_known_type(v->basetype)) {
                    eff_mat_type = oct_type_props(v->basetype)->matrix_type;
                    known = true;
                }
                if (known) {
                    Expr* da = v->qual ? v->qual->args : NULL;
                    int ndims = 0;
                    for (Expr* e = da; e; e = e->next) ndims++;
                    if (ndims == 1) {
                        fprintf(fp, "    mat_out%d_ = %s(dim%d_, 1);\n",
                                v->output_label, eff_mat_type, da->input_label);
                    } else if (ndims == 2) {
                        fprintf(fp, "    mat_out%d_ = %s(dim%d_, dim%d_);\n",
                                v->output_label, eff_mat_type,
                                da->input_label, da->next->input_label);
                    } else {
                        fprintf(fp, "    mat_out%d_ = %s(", v->output_label, eff_mat_type);
                        print_alloc_size_expr(fp, da);
                        fprintf(fp, ", 1);\n");
                    }
                    fprintf(fp, "    out%d_ = (%s*) mat_out%d_.fortran_vec();\n",
                            v->output_label, v->basetype, v->output_label);
                } else {
                    /* Unknown type: fall back to new[] */
                    fprintf(fp, "    out%d_ = new %s[", v->output_label, v->basetype);
                    print_alloc_size_expr(fp, v->qual->args);
                    fprintf(fp, "];\n");
                }
            } else if (is_array(v->tinfo)) {
                fprintf(fp, "    out%d_ = new %s[", v->output_label, v->basetype);
                print_alloc_size_expr(fp, v->qual->args);
                fprintf(fp, "];\n");
            } else if (v->tinfo == VT_rarray) {
                fprintf(fp, "    out%d_ = (%s*) NULL;\n",
                        v->output_label, v->basetype);
            } else if (v->tinfo == VT_string) {
                fprintf(fp, "    out%d_ = new char[", v->output_label);
                print_alloc_size_expr(fp, v->qual->args);
                fprintf(fp, "];\n");
            }
        }
    }
}


static void alloc_outputs(FILE* fp, Func* f)
{
    if (!nullable_return(f))
        alloc_output(fp, f->ret);
    alloc_output(fp, f->args);
}


/* -- Make the call -- */

static void make_call_args(FILE* fp, Var* args, bool first)
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


static void make_call_expr(FILE* fp, Func* f)
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
    make_call_args(fp, f->args, true);
    fprintf(fp, ")");
}


static void make_stmt(FILE* fp, Func* f)
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
            make_call_expr(fp, f);
            fprintf(fp, ");\n");
        } else if (is_array(v->tinfo)) {
            fprintf(fp, "    out0_ = (%s*) ", v->basetype);
            make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_scalar || v->tinfo == VT_r_scalar ||
                   v->tinfo == VT_cscalar || v->tinfo == VT_r_cscalar ||
                   v->tinfo == VT_zscalar || v->tinfo == VT_r_zscalar) {
            fprintf(fp, "    out0_ = ");
            make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_string) {
            fprintf(fp, "    out0_ = (char*) ");
            make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_p_obj) {
            fprintf(fp, "    out0_ = ");
            make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_p_scalar || v->tinfo == VT_p_cscalar ||
                   v->tinfo == VT_p_zscalar) {
            fprintf(fp, "    out0_ = *");
            make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_mx) {
            fprintf(fp, "    retval(0) = ");
            make_call_expr(fp, f);
            fprintf(fp, ";\n");
        } else if (v->tinfo == VT_r_obj) {
            fprintf(fp, "    out0_ = &(");
            make_call_expr(fp, f);
            fprintf(fp, ");\n");
        }
    } else {
        fprintf(fp, "    ");
        make_call_expr(fp, f);
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


/* -- Marshal results (oct-file version) -- */

static void marshal_array(FILE* fp, Var* v)
{
    char nbuf[64];
    int il = v->input_label;
    int ol = v->output_label;
    const char* bt = v->basetype;
    const char* n = vname(v, nbuf);
    const OctTypeProps* tp = oct_type_props(bt);
    Expr* da = v->qual ? v->qual->args : NULL;

    /* Determine effective matrix type for marshalling */
    ComplexMatrixInfo zinfo;
    const char* eff_mat_type;
    bool known_type;
    if (get_complex_matrix_info(v, &zinfo)) {
        eff_mat_type = zinfo.matrix_type;
        known_type = true;
    } else if (oct_is_known_type(bt)) {
        eff_mat_type = tp->matrix_type;
        known_type = true;
    } else {
        eff_mat_type = "Matrix";
        known_type = false;
    }

    /* Nocopy output: Matrix was pre-allocated, just assign */
    if (v->nocopy && v->iospec == 'o' && is_array(v->tinfo) && known_type) {
        fprintf(fp, "    retval(%d) = mat_out%d_;\n", ol, ol);
        return;
    }


    const char* ws;
    if (v->tinfo == VT_rarray) {
        fprintf(fp, "    if (out%d_ == NULL) {\n", ol);
        fprintf(fp, "        retval(%d) = Matrix(0, 0);\n", ol);
        fprintf(fp, "    } else {\n");
        ws = "        ";
    } else {
        ws = "    ";
    }

    int ndims = 0;
    for (Expr* e = da; e; e = e->next)
        ndims++;

    if (ndims == 0) {
        /* No dims -- inout array: create matrix from original size */
        if (known_type) {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    %s mat_out%d_(args(%d).rows(), args(%d).columns());\n",
                    ws, eff_mat_type, ol, il, il);
            fprintf(fp, "%s    std::memcpy(mat_out%d_.fortran_vec(), in%d_, args(%d).numel()*sizeof(%s));\n",
                    ws, ol, il, il, bt);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    octave_idx_type n_ = args(%d).numel();\n", ws, il);
            fprintf(fp, "%s    Matrix mat_out%d_(args(%d).rows(), args(%d).columns());\n",
                    ws, ol, il, il);
            fprintf(fp, "%s    double* dst_ = mat_out%d_.fortran_vec();\n", ws, ol);
            fprintf(fp, "%s    for (octave_idx_type i_ = 0; i_ < n_; ++i_)\n", ws);
            fprintf(fp, "%s        dst_[i_] = (double) in%d_[i_];\n", ws, il);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        }
    } else if (ndims == 1) {
        /* 1D */
        if (known_type) {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    %s mat_out%d_(dim%d_, 1);\n",
                    ws, eff_mat_type, ol, da->input_label);
            fprintf(fp, "%s    std::memcpy(mat_out%d_.fortran_vec(), %s, dim%d_*sizeof(%s));\n",
                    ws, ol, n, da->input_label, bt);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    Matrix mat_out%d_(dim%d_, 1);\n",
                    ws, ol, da->input_label);
            fprintf(fp, "%s    double* dst_ = mat_out%d_.fortran_vec();\n", ws, ol);
            fprintf(fp, "%s    for (octave_idx_type i_ = 0; i_ < dim%d_; ++i_)\n",
                    ws, da->input_label);
            fprintf(fp, "%s        dst_[i_] = (double) %s[i_];\n", ws, n);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        }
    } else if (ndims == 2) {
        /* 2D */
        if (known_type) {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    %s mat_out%d_(dim%d_, dim%d_);\n",
                    ws, eff_mat_type, ol, da->input_label, da->next->input_label);
            fprintf(fp, "%s    std::memcpy(mat_out%d_.fortran_vec(), %s, dim%d_*dim%d_*sizeof(%s));\n",
                    ws, ol, n, da->input_label, da->next->input_label, bt);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    Matrix mat_out%d_(dim%d_, dim%d_);\n",
                    ws, ol, da->input_label, da->next->input_label);
            fprintf(fp, "%s    double* dst_ = mat_out%d_.fortran_vec();\n", ws, ol);
            fprintf(fp, "%s    for (octave_idx_type i_ = 0; i_ < dim%d_*dim%d_; ++i_)\n",
                    ws, da->input_label, da->next->input_label);
            fprintf(fp, "%s        dst_[i_] = (double) %s[i_];\n", ws, n);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        }
    } else {
        /* 3D+ -- flatten to 1D */
        if (known_type) {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    %s mat_out%d_(", ws, eff_mat_type, ol);
            print_alloc_size_expr(fp, da);
            fprintf(fp, ", 1);\n");
            fprintf(fp, "%s    std::memcpy(mat_out%d_.fortran_vec(), %s, (", ws, ol, n);
            print_alloc_size_expr(fp, da);
            fprintf(fp, ")*sizeof(%s));\n", bt);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        } else {
            fprintf(fp, "%s{\n", ws);
            fprintf(fp, "%s    Matrix mat_out%d_(", ws, ol);
            print_alloc_size_expr(fp, da);
            fprintf(fp, ", 1);\n");
            fprintf(fp, "%s    double* dst_ = mat_out%d_.fortran_vec();\n", ws, ol);
            fprintf(fp, "%s    for (octave_idx_type i_ = 0; i_ < ", ws);
            print_alloc_size_expr(fp, da);
            fprintf(fp, "; ++i_)\n");
            fprintf(fp, "%s        dst_[i_] = (double) %s[i_];\n", ws, n);
            fprintf(fp, "%s    retval(%d) = mat_out%d_;\n", ws, ol, ol);
            fprintf(fp, "%s}\n", ws);
        }
    }

    if (v->tinfo == VT_rarray)
        fprintf(fp, "    }\n");
}


static void marshal_result(FILE* fp, Var* v)
{
    char nbuf[64];
    int ol = v->output_label;
    const char* bt = v->basetype;
    const char* n = vname(v, nbuf);

    if (is_obj(v->tinfo)) {
        fprintf(fp, "    retval(%d) = mwOctCreateP(out%d_, \"%s:%%p\");\n",
                ol, ol, bt);
    } else if (is_array(v->tinfo) || v->tinfo == VT_rarray) {
        marshal_array(fp, v);
    } else if (v->tinfo == VT_scalar || v->tinfo == VT_r_scalar ||
               v->tinfo == VT_p_scalar) {
        fprintf(fp, "    retval(%d) = octave_value((double) %s);\n", ol, n);
    } else if (v->tinfo == VT_cscalar || v->tinfo == VT_zscalar ||
               v->tinfo == VT_r_cscalar || v->tinfo == VT_r_zscalar ||
               v->tinfo == VT_p_cscalar || v->tinfo == VT_p_zscalar) {
        if (strcmp(bt, "fcomplex") == 0)
            fprintf(fp, "    retval(%d) = octave_value(FloatComplex(real_%s(%s), imag_%s(%s)));\n",
                    ol, bt, n, bt, n);
        else
            fprintf(fp, "    retval(%d) = octave_value(Complex(real_%s(%s), imag_%s(%s)));\n",
                    ol, bt, n, bt, n);
    } else if (v->tinfo == VT_string) {
        fprintf(fp, "    retval(%d) = mwOctStrncpy(%s);\n", ol, n);
    } else if (v->tinfo == VT_mx) {
        if (v->iospec == 'o')
            fprintf(fp, "    retval(%d) = retval_mx%d_;\n", ol, ol);
    }
}


static void marshal_results_var(FILE* fp, Var* vars)
{
    for (Var* v = vars; v; v = v->next)
        if (v->iospec != 'i')
            marshal_result(fp, v);
}


static void marshal_results(FILE* fp, Func* f)
{
    if (!nullable_return(f))
        marshal_results_var(fp, f->ret);
    marshal_results_var(fp, f->args);
}


/* -- Dealloc (oct-file version -- simpler, no mxFree) -- */

static void dealloc_var(FILE* fp, Var* vars)
{
    for (Var* v = vars; v; v = v->next) {
        if (is_array(v->tinfo) || v->tinfo == VT_string) {
            if (v->nocopy && v->iospec == 'o' && is_array(v->tinfo)) {
                /* Nocopy output: memory owned by Matrix, no dealloc needed.
                 * Exception: unknown types that fell back to new[] */
                ComplexMatrixInfo zinfo;
                if (!oct_is_known_type(v->basetype) &&
                    !get_complex_matrix_info(v, &zinfo))
                    fprintf(fp, "    if (out%d_) delete[] out%d_;\n",
                            v->output_label, v->output_label);
            } else if (v->iospec == 'o') {
                fprintf(fp, "    if (out%d_) delete[] out%d_;\n",
                        v->output_label, v->output_label);
            } else if (v->iospec == 'b') {
                /* Inout arrays backed by known Octave types don't need dealloc */
                ComplexMatrixInfo zinfo;
                if (!oct_is_known_type(v->basetype) &&
                    !get_complex_matrix_info(v, &zinfo))
                    fprintf(fp, "    if (in%d_)  delete[] in%d_;\n",
                            v->input_label, v->input_label);
            } else if (v->iospec == 'i') {
                /* Input-only: known types point into Matrix, no dealloc needed */
                ComplexMatrixInfo zinfo;
                if (!oct_is_known_type(v->basetype) &&
                    !get_complex_matrix_info(v, &zinfo))
                    fprintf(fp, "    if (in%d_)  delete[] in%d_;\n",
                            v->input_label, v->input_label);
            }
        }
    }
}


static void dealloc(FILE* fp, Func* f)
{
    if (!nullable_return(f))
        dealloc_var(fp, f->ret);
    dealloc_var(fp, f->args);
}


/* -- Print a single oct-file stub -- */

static void print_c_comment(FILE* fp, Func* f)
{
    fprintf(fp, "/* ---- %s: %d ----\n * ", f->fname.c_str(), f->line);
    print(fp, f);
    for (Func* fsame = f->same_next; fsame; fsame = fsame->next)
        fprintf(fp, " * Also at %s: %d\n", fsame->fname.c_str(), fsame->line);
    fprintf(fp, " */\n");
}


static int count_outputs(Func* f)
{
    int nout = 0;
    if (f->ret && !nullable_return(f)) {
        for (Var* v = f->ret; v; v = v->next)
            if (v->output_label + 1 > nout)
                nout = v->output_label + 1;
    }
    for (Var* v = f->args; v; v = v->next)
        if ((v->iospec == 'o' || v->iospec == 'b') && v->output_label + 1 > nout)
            nout = v->output_label + 1;
    return nout;
}


static void print_oct_stub(FILE* fp, Func* f)
{
    print_c_comment(fp, f);
    string ids = id_string(f);
    fprintf(fp, "static const char* stubids%d_ = \"%s\";\n\n",
            f->id, ids.c_str());
    int nout = count_outputs(f);

    fprintf(fp,
            "static octave_value_list octStub%d(const octave_value_list& args, int nargout)\n"
            "{\n"
            "    octave_value_list retval;\n"
            "    const char* mw_err_txt_ = 0;\n",
            f->id);
    if (nout > 0)
        fprintf(fp, "    retval.resize(%d);\n", nout);
    declare_args(fp, f);
    unpack_dims(fp, f);
    check_dims(fp, f->args);
    unpack_inputs(fp, f);
    check_inputs(fp, f->args);
    alloc_outputs(fp, f);
    make_stmt(fp, f);
    marshal_results(fp, f);
    fprintf(fp, "\nmw_err_label:\n");
    dealloc(fp, f);
    fprintf(fp,
            "    if (mw_err_txt_)\n"
            "        error(\"%%s\", mw_err_txt_);\n"
            "    return retval;\n"
            "}\n\n");
}


/* -- Print all stubs, dispatch table, gateway -- */

static void print_oct_stubs(FILE* fp, Func* f)
{
    for (; f; f = f->next)
        print_oct_stub(fp, f);
}


static void print_oct_stub_table(FILE* fp, Func* f)
{
    /* Build map: id -> stub_id.  Functions on same_next chains share
     * the stub of the primary function in the next chain. */
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
            "typedef octave_value_list (*octStubFunc_t)(const octave_value_list&, int);\n\n"
            "static octStubFunc_t mwStubs_[] = {\n"
            "    NULL");
    for (int i = 1; i <= maxid; i++) {
        fprintf(fp, ",\n");
        map<int,int>::iterator it = id_to_stub.find(i);
        if (it != id_to_stub.end())
            fprintf(fp, "    octStub%d", it->second);
        else
            fprintf(fp, "    NULL");
    }
    fprintf(fp, "\n};\n\n");
    fprintf(fp, "static int mwNumStubs_ = %d;\n\n", maxid);
}


static void print_oct_else_cases(FILE* fp, Func* f)
{
    for (Func* fcall = f; fcall; fcall = fcall->next)
        fprintf(fp,
                "    else if (id == stubids%d_)\n"
                "        return octStub%d(sub_args, nargout);\n",
                fcall->id, fcall->id);
    fprintf(fp,
            "    else\n"
            "        error(\"Unknown identifier\");\n");
}


/* -- Top-level: print_oct_init + print_oct_file -- */

static const char* mwrap_oct_banner =
    "/* --------------------------------------------------- */\n"
    "/* Automatically generated by mwrap (oct-file backend) */\n"
    "/* --------------------------------------------------- */\n\n";


void print_oct_init(FILE* fp)
{
    fprintf(fp, "%s", mwrap_oct_banner);
    fprintf(fp, "%s", oct_header);
    fprintf(fp, "\n");
    /* Oct-files always use C++ complex */
    if (mw_use_c99_complex || mw_use_cpp_complex)
        oct_cpp_complex(fp);
}


void print_oct_file(FILE* fp, Func* f, const char* octfunc)
{
    if (mw_use_int32_t || mw_use_int64_t || mw_use_uint32_t || mw_use_uint64_t)
        fprintf(fp, "#include <stdint.h>\n\n");

    oct_casting_getters(fp);

    if (has_fortran(f)) {
        oct_define_fnames(fp, f);
        oct_fortran_decls(fp, f);
    }

    print_oct_stubs(fp, f);
    print_oct_stub_table(fp, f);

    /* Gateway function */
    fprintf(fp,
            "DEFUN_DLD(%s, args, nargout, \"MWrap generated oct-file gateway\")\n"
            "{\n"
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
            "            error(\"Unknown function ID %%d\", stub_id);\n"
            "        return octave_value_list();\n"
            "    }\n\n"
            "    /* Slow path: string dispatch */\n"
            "    if (args(0).is_string()) {\n"
            "        std::string id = args(0).string_value();\n"
            "        octave_value_list sub_args = args.slice(1, args.length()-1);\n"
            "        if (false)\n"
            "            ; /* placeholder for else-if chain */\n",
            octfunc);

    print_oct_else_cases(fp, f);

    fprintf(fp,
            "    }\n\n"
            "    error(\"First argument must be function ID (integer or string)\");\n"
            "    return octave_value_list();\n"
            "}\n\n");
}
