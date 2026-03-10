/*
 * mwrap-fmexgen.cc
 *   Generate Fortran MEX gateway code (free-form F90) from MWrap AST.
 *
 * Generates free-form Fortran 90 (.f90) MEX gateway files using
 * iso_c_binding and bind(C) for direct C interop with the MEX API.
 * No C bridge file, no name mangling, no preprocessor.
 *
 * Copyright (c) 2007-2008  David Bindel
 * See the file COPYING for copying permissions
 *
 * Fortran MEX backend by Zydrunas Gimbutas (2026),
 * with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <ctype.h>
#include <cassert>
#include <map>

#include "mwrap-ast.h"
#include "mwrap-fmex-support.h"

using std::map;


/* ===================================================================
 * Type mapping: mwrap base types -> Fortran iso_c_binding types
 * =================================================================== */

struct FmexTypeProps {
    const char* fort_type;   /* Fortran type string */
    bool is_complex;         /* true for dcomplex, fcomplex */
    bool is_native;          /* true if mxArray data is usable directly */
};

static const FmexTypeProps fmex_default_props =
    {"real(c_double)", false, true};

struct FmexTypeEntry {
    const char* name;
    FmexTypeProps props;
    FmexTypeProps props_i8;  /* with -i8 promotion */
};

static const FmexTypeEntry fmex_type_table[] = {
    {"double",   {"real(c_double)",            false, true},
                 {"real(c_double)",            false, true}},
    {"float",    {"real(c_float)",             false, false},
                 {"real(c_float)",             false, false}},
    {"int",      {"integer(c_int)",            false, false},
                 {"integer(8)",               false, false}},
    {"int32_t",  {"integer(c_int32_t)",        false, false},
                 {"integer(8)",               false, false}},
    {"int64_t",  {"integer(c_int64_t)",        false, false},
                 {"integer(8)",               false, false}},
    {"dcomplex", {"complex(c_double_complex)", true,  true},
                 {"complex(c_double_complex)", true,  true}},
    {"fcomplex", {"complex(c_float_complex)",  true,  false},
                 {"complex(c_float_complex)",  true,  false}},
    {NULL,       {NULL, false, false},
                 {NULL, false, false}}
};


static const FmexTypeProps* fmex_type_props(const char* name, bool i8_mode)
{
    for (const FmexTypeEntry* e = fmex_type_table; e->name; ++e)
        if (strcmp(e->name, name) == 0)
            return i8_mode ? &e->props_i8 : &e->props;
    return &fmex_default_props;
}


static const char* fmex_int_kind(bool i8_mode)
{
    return i8_mode ? "8" : "c_int";
}


static bool fmex_needs_conversion(const char* basetype)
{
    return strcmp(basetype, "double") != 0 && strcmp(basetype, "dcomplex") != 0;
}


/* ===================================================================
 * Variable naming
 * =================================================================== */

static void fmex_vname(char* buf, size_t bufsz, Var* v)
{
    if (v->iospec == 'o')
        snprintf(buf, bufsz, "out%d_", v->output_label);
    else
        snprintf(buf, bufsz, "in%d_", v->input_label);
}


/* ===================================================================
 * Classify variables for code generation
 * =================================================================== */

/* True if v is an array with all-literal dimensions whose product == 1 */
static bool fmex_is_scalar_array(Var* v)
{
    if (!v->qual || !v->qual->args)
        return false;
    int prod = 1;
    for (Expr* e = v->qual->args; e; e = e->next) {
        /* Check all characters are digits */
        for (const char* p = e->value; *p; ++p)
            if (!isdigit((unsigned char)*p))
                return false;
        prod *= atoi(e->value);
    }
    return prod == 1;
}


/* Product of literal dimension values, or -1 if not all-literal */
static int fmex_dim_product(Var* v)
{
    if (!v->qual || !v->qual->args)
        return -1;
    int prod = 1;
    for (Expr* e = v->qual->args; e; e = e->next) {
        for (const char* p = e->value; *p; ++p)
            if (!isdigit((unsigned char)*p))
                return -1;
        prod *= atoi(e->value);
    }
    return prod;
}


/* ===================================================================
 * Helper: dimension expression in Fortran
 * =================================================================== */

/* Print "dim1_ * dim2_ * ..." alloc size expression */
static void fmex_print_alloc_size(FILE* fp, Expr* args)
{
    if (!args) {
        fprintf(fp, "1");
        return;
    }
    bool first = true;
    for (Expr* e = args; e; e = e->next) {
        if (!first)
            fprintf(fp, " * ");
        fprintf(fp, "dim%d_", e->input_label);
        first = false;
    }
}


/* Write alloc size to a buffer */
static void fmex_alloc_size_str(char* buf, size_t bufsz, Expr* args)
{
    if (!args) {
        snprintf(buf, bufsz, "1");
        return;
    }
    buf[0] = '\0';
    bool first = true;
    for (Expr* e = args; e; e = e->next) {
        char tmp[64];
        snprintf(tmp, sizeof(tmp), "%sdim%d_", first ? "" : " * ", e->input_label);
        strncat(buf, tmp, bufsz - strlen(buf) - 1);
        first = false;
    }
}


/* ===================================================================
 * Write helpers (free-form Fortran, no column limit concern)
 * =================================================================== */

static void fmex_w(FILE* fp, int indent, const char* fmt, ...)
    __attribute__((format(printf, 3, 4)));

static void fmex_w(FILE* fp, int indent, const char* fmt, ...)
{
    for (int i = 0; i < indent; i++)
        fputc(' ', fp);
    va_list ap;
    va_start(ap, fmt);
    vfprintf(fp, fmt, ap);
    va_end(ap);
    fputc('\n', fp);
}


static void fmex_wc(FILE* fp, int indent, const char* text)
{
    for (int i = 0; i < indent; i++)
        fputc(' ', fp);
    fprintf(fp, "! %s\n", text);
}


/* ===================================================================
 * Per-stub: declare local variables
 * =================================================================== */

static void fmex_print_declarations(FILE* fp, Func* f, bool i8_mode)
{
    /* Dimension variables (from ret + args) */
    for (Var* v = f->ret; v; v = v->next) {
        if (v->qual && v->qual->args)
            for (Expr* e = v->qual->args; e; e = e->next)
                fmex_w(fp, 4, "integer(c_size_t) :: dim%d_", e->input_label);
    }
    for (Var* v = f->args; v; v = v->next) {
        if (v->qual && v->qual->args)
            for (Expr* e = v->qual->args; e; e = e->next)
                fmex_w(fp, 4, "integer(c_size_t) :: dim%d_", e->input_label);
    }

    /* Input variables */
    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec == 'o' || v->tinfo == VT_const)
            continue;

        int il = v->input_label;
        const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);

        if (is_array(v->tinfo)) {
            if (fmex_is_scalar_array(v) && fmex_dim_product(v) == 1) {
                /* Scalar-by-reference: local variable, passed by ref */
                fmex_w(fp, 4, "%s :: in%d_", tp->fort_type, il);
            } else if (tp->is_native) {
                /* Native type: use c_f_pointer directly */
                fmex_w(fp, 4, "%s, pointer :: in%d_(:)", tp->fort_type, il);
            } else {
                /* Needs conversion from double */
                fmex_w(fp, 4, "%s, allocatable :: in%d_(:)", tp->fort_type, il);
                fmex_w(fp, 4, "real(c_double), pointer :: in%d_dbl_(:)", il);
            }
        } else if (v->tinfo == VT_p_scalar || v->tinfo == VT_p_cscalar ||
                   v->tinfo == VT_p_zscalar) {
            fmex_w(fp, 4, "%s :: in%d_", tp->fort_type, il);
        } else if (v->tinfo == VT_string) {
            fmex_w(fp, 4, "character(len=1024) :: in%d_", il);
            fmex_w(fp, 4, "integer(c_int) :: in%d_stat_", il);
        }
    }

    /* Output variables (from ret + args) */
    for (Var* v = f->ret; v; v = v->next) {
        if (v->iospec != 'o')
            continue;
        int ol = v->output_label;
        const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);

        if (is_array(v->tinfo)) {
            if (tp->is_native)
                fmex_w(fp, 4, "%s, pointer :: out%d_(:)", tp->fort_type, ol);
            else {
                fmex_w(fp, 4, "%s, allocatable :: out%d_(:)", tp->fort_type, ol);
                fmex_w(fp, 4, "real(c_double), pointer :: out%d_dbl_(:)", ol);
            }
        } else if (v->tinfo == VT_scalar || v->tinfo == VT_p_scalar) {
            fmex_w(fp, 4, "%s :: out%d_", tp->fort_type, ol);
            fmex_w(fp, 4, "real(c_double), pointer :: out%d_dbl_(:)", ol);
        } else if (v->tinfo == VT_p_cscalar || v->tinfo == VT_p_zscalar) {
            fmex_w(fp, 4, "%s :: out%d_", tp->fort_type, ol);
        }
    }
    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec != 'o')
            continue;
        int ol = v->output_label;
        const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);

        if (is_array(v->tinfo)) {
            if (tp->is_native)
                fmex_w(fp, 4, "%s, pointer :: out%d_(:)", tp->fort_type, ol);
            else {
                fmex_w(fp, 4, "%s, allocatable :: out%d_(:)", tp->fort_type, ol);
                fmex_w(fp, 4, "real(c_double), pointer :: out%d_dbl_(:)", ol);
            }
        } else if (v->tinfo == VT_scalar || v->tinfo == VT_p_scalar) {
            fmex_w(fp, 4, "%s :: out%d_", tp->fort_type, ol);
            fmex_w(fp, 4, "real(c_double), pointer :: out%d_dbl_(:)", ol);
        } else if (v->tinfo == VT_p_cscalar || v->tinfo == VT_p_zscalar) {
            fmex_w(fp, 4, "%s :: out%d_", tp->fort_type, ol);
        }
    }

    /* Inout arrays: need pointers for input copy and marshal temps */
    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec != 'b')
            continue;
        int il = v->input_label;
        const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);

        if (is_array(v->tinfo)) {
            if (fmex_is_scalar_array(v) && fmex_dim_product(v) == 1) {
                /* Scalar inout: need a double pointer for marshalling output */
                int ol = v->output_label;
                fmex_w(fp, 4, "real(c_double), pointer :: out%d_dbl_(:)", ol);
            } else if (tp->is_native) {
                /* Need a pointer for output + pointer for input copy */
                fmex_w(fp, 4, "%s, pointer :: inout%d_src_(:)", tp->fort_type, il);
            } else {
                fmex_w(fp, 4, "real(c_double), pointer :: inout%d_src_dbl_(:)", il);
            }
            /* Dimension vars for inout arrays without explicit dims */
            if (!v->qual || !v->qual->args) {
                fmex_w(fp, 4, "integer(c_size_t) :: inout%d_m_, inout%d_n_", il, il);
            }
        }
    }

    /* Return value */
    if (f->ret) {
        Var* v = f->ret;
        if (v->tinfo == VT_scalar) {
            const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);
            fmex_w(fp, 4, "%s :: out0_", tp->fort_type);
            fmex_w(fp, 4, "real(c_double), pointer :: ret_dbl_(:)");
        }
    }

    /* Temp integer for loop index (if needed for conversion) */
    bool needs_loop = false;
    for (Var* v = f->ret; v && !needs_loop; v = v->next) {
        if (is_array(v->tinfo) && fmex_needs_conversion(v->basetype))
            if (!(fmex_is_scalar_array(v) && fmex_dim_product(v) == 1))
                needs_loop = true;
    }
    for (Var* v = f->args; v && !needs_loop; v = v->next) {
        if (is_array(v->tinfo) && fmex_needs_conversion(v->basetype))
            if (!(fmex_is_scalar_array(v) && fmex_dim_product(v) == 1))
                needs_loop = true;
    }
    if (needs_loop)
        fmex_w(fp, 4, "integer(c_size_t) :: mwf_i_");

    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: unpack dimensions
 * =================================================================== */

static void fmex_print_unpack_dims(FILE* fp, Func* f, bool i8_mode)
{
    bool has_dims = false;
    for (Var* v = f->ret; v && !has_dims; v = v->next)
        if (v->qual && v->qual->args)
            has_dims = true;
    for (Var* v = f->args; v && !has_dims; v = v->next)
        if (v->qual && v->qual->args)
            has_dims = true;
    if (!has_dims)
        return;

    fmex_wc(fp, 4, "unpack dimensions");
    for (Var* v = f->ret; v; v = v->next) {
        if (v->qual && v->qual->args) {
            for (Expr* e = v->qual->args; e; e = e->next) {
                int idx = e->input_label + 1;
                fmex_w(fp, 4, "dim%d_ = int(mxGetScalar(prhs(%d)), c_size_t)",
                        e->input_label, idx);
            }
        }
    }
    for (Var* v = f->args; v; v = v->next) {
        if (v->qual && v->qual->args) {
            for (Expr* e = v->qual->args; e; e = e->next) {
                int idx = e->input_label + 1;
                fmex_w(fp, 4, "dim%d_ = int(mxGetScalar(prhs(%d)), c_size_t)",
                        e->input_label, idx);
            }
        }
    }
    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: unpack inputs
 * =================================================================== */

static void fmex_print_unpack_inputs(FILE* fp, Func* f, bool i8_mode)
{
    bool has_inputs = false;
    for (Var* v = f->args; v && !has_inputs; v = v->next)
        if (v->iospec != 'o' && v->tinfo != VT_const)
            has_inputs = true;
    if (!has_inputs)
        return;

    fmex_wc(fp, 4, "unpack inputs");

    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec == 'o' || v->tinfo == VT_const)
            continue;

        int il = v->input_label;
        int idx = il + 1;
        const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);
        Expr* da = (v->qual) ? v->qual->args : NULL;

        if (is_array(v->tinfo)) {
            if (fmex_is_scalar_array(v) && fmex_dim_product(v) == 1) {
                /* Scalar-by-reference: extract via mxGetScalar */
                if (strcmp(v->basetype, "int") == 0 ||
                    strcmp(v->basetype, "int32_t") == 0) {
                    fmex_w(fp, 4, "in%d_ = int(mxGetScalar(prhs(%d)), %s)",
                            il, idx, fmex_int_kind(i8_mode));
                } else if (strcmp(v->basetype, "int64_t") == 0) {
                    fmex_w(fp, 4, "in%d_ = int(mxGetScalar(prhs(%d)), c_int64_t)",
                            il, idx);
                } else {
                    fmex_w(fp, 4, "in%d_ = mxGetScalar(prhs(%d))", il, idx);
                }
            } else if (tp->is_native) {
                /* Native type: use c_f_pointer */
                char sz[256];
                if (da)
                    fmex_alloc_size_str(sz, sizeof(sz), da);
                else
                    snprintf(sz, sizeof(sz),
                             "int(mxGetM(prhs(%d)) * mxGetN(prhs(%d)), c_size_t)",
                             idx, idx);
                fmex_w(fp, 4, "call c_f_pointer(mxGetPr(prhs(%d)), in%d_, [%s])",
                        idx, il, sz);
            } else {
                /* Needs conversion from double */
                char sz[256];
                if (da)
                    fmex_alloc_size_str(sz, sizeof(sz), da);
                else
                    snprintf(sz, sizeof(sz),
                             "int(mxGetM(prhs(%d)) * mxGetN(prhs(%d)), c_size_t)",
                             idx, idx);
                fmex_w(fp, 4, "call c_f_pointer(mxGetPr(prhs(%d)), in%d_dbl_, [%s])",
                        idx, il, sz);
                fmex_w(fp, 4, "allocate(in%d_(%s))", il, sz);
                fmex_w(fp, 4, "do mwf_i_ = 1, %s", sz);
                fmex_w(fp, 6, "  in%d_(mwf_i_) = int(in%d_dbl_(mwf_i_), %s)",
                        il, il, fmex_int_kind(i8_mode));
                fmex_w(fp, 4, "end do");
            }
        } else if (v->tinfo == VT_p_scalar || v->tinfo == VT_p_cscalar ||
                   v->tinfo == VT_p_zscalar) {
            if (strcmp(v->basetype, "int") == 0 ||
                strcmp(v->basetype, "int32_t") == 0) {
                fmex_w(fp, 4, "in%d_ = int(mxGetScalar(prhs(%d)), %s)",
                        il, idx, fmex_int_kind(i8_mode));
            } else if (strcmp(v->basetype, "int64_t") == 0) {
                fmex_w(fp, 4, "in%d_ = int(mxGetScalar(prhs(%d)), c_int64_t)",
                        il, idx);
            } else {
                fmex_w(fp, 4, "in%d_ = mxGetScalar(prhs(%d))", il, idx);
            }
        } else if (v->tinfo == VT_string) {
            fmex_w(fp, 4, "in%d_stat_ = mxGetString(prhs(%d), in%d_, 1024_c_int)",
                    il, idx, il);
        }
    }
    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: handle inout arrays
 * =================================================================== */

static void fmex_print_handle_inout(FILE* fp, Func* f, bool i8_mode)
{
    bool has_inout = false;
    for (Var* v = f->args; v && !has_inout; v = v->next)
        if (v->iospec == 'b' && is_array(v->tinfo))
            has_inout = true;
    if (!has_inout)
        return;

    fmex_wc(fp, 4, "handle inout arrays: create output, copy input");

    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec != 'b' || !is_array(v->tinfo))
            continue;

        int il = v->input_label;
        int ol = v->output_label;
        int idx_in = il + 1;
        int idx_out = ol + 1;
        const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);
        Expr* da = (v->qual) ? v->qual->args : NULL;

        if (fmex_is_scalar_array(v) && fmex_dim_product(v) == 1) {
            /* Scalar inout: already handled in unpack_inputs.
             * Will marshal after the call. */
            continue;
        }

        /* Get dimensions */
        char dim_m[256], dim_n[256], sz[256];
        if (da) {
            /* Count dimension args */
            int ndims = 0;
            Expr* dim2 = NULL;
            for (Expr* e = da; e; e = e->next) {
                ndims++;
                if (ndims == 2) dim2 = e;
            }
            if (ndims == 1) {
                snprintf(dim_m, sizeof(dim_m), "dim%d_", da->input_label);
                snprintf(dim_n, sizeof(dim_n), "1_c_size_t");
            } else if (ndims == 2) {
                snprintf(dim_m, sizeof(dim_m), "dim%d_", da->input_label);
                snprintf(dim_n, sizeof(dim_n), "dim%d_", dim2->input_label);
            } else {
                fmex_alloc_size_str(dim_m, sizeof(dim_m), da);
                snprintf(dim_n, sizeof(dim_n), "1_c_size_t");
            }
            fmex_alloc_size_str(sz, sizeof(sz), da);
        } else {
            /* No explicit dims: use input array size */
            fmex_w(fp, 4, "inout%d_m_ = mxGetM(prhs(%d))", il, idx_in);
            fmex_w(fp, 4, "inout%d_n_ = mxGetN(prhs(%d))", il, idx_in);
            snprintf(dim_m, sizeof(dim_m), "inout%d_m_", il);
            snprintf(dim_n, sizeof(dim_n), "inout%d_n_", il);
            snprintf(sz, sizeof(sz), "inout%d_m_ * inout%d_n_", il, il);
        }

        /* Create output mxArray */
        const char* cflag = tp->is_complex ? "1" : "0";
        fmex_w(fp, 4, "plhs(%d) = mxCreateDoubleMatrix(%s, %s, %s)",
                idx_out, dim_m, dim_n, cflag);

        if (tp->is_native) {
            /* Copy input data to output, point in{il}_ at output */
            fmex_w(fp, 4, "call c_f_pointer(mxGetPr(prhs(%d)), inout%d_src_, [%s])",
                    idx_in, il, sz);
            fmex_w(fp, 4, "call c_f_pointer(mxGetPr(plhs(%d)), in%d_, [%s])",
                    idx_out, il, sz);
            fmex_w(fp, 4, "in%d_(1:%s) = inout%d_src_(1:%s)", il, sz, il, sz);
        } else {
            /* Need to convert from double, write back after call */
            fmex_w(fp, 4, "call c_f_pointer(mxGetPr(prhs(%d)), inout%d_src_dbl_, [%s])",
                    idx_in, il, sz);
            fmex_w(fp, 4, "allocate(in%d_(%s))", il, sz);
            fmex_w(fp, 4, "do mwf_i_ = 1, %s", sz);
            fmex_w(fp, 6, "  in%d_(mwf_i_) = int(inout%d_src_dbl_(mwf_i_), %s)",
                    il, il, fmex_int_kind(i8_mode));
            fmex_w(fp, 4, "end do");
        }
    }
    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: allocate pure output arrays
 * =================================================================== */

static void fmex_print_alloc_outputs(FILE* fp, Func* f, bool i8_mode)
{
    bool has_out = false;
    for (Var* v = f->ret; v && !has_out; v = v->next)
        if (v->iospec == 'o' && is_array(v->tinfo))
            has_out = true;
    for (Var* v = f->args; v && !has_out; v = v->next)
        if (v->iospec == 'o' && is_array(v->tinfo))
            has_out = true;
    if (!has_out)
        return;

    fmex_wc(fp, 4, "allocate output arrays");

    /* Process ret then args */
    for (int pass = 0; pass < 2; pass++) {
        Var* vlist = (pass == 0) ? f->ret : f->args;
        for (Var* v = vlist; v; v = v->next) {
            if (v->iospec != 'o' || !is_array(v->tinfo))
                continue;
            int ol = v->output_label;
            int idx = ol + 1;
            const FmexTypeProps* tp = fmex_type_props(v->basetype, i8_mode);
            Expr* da = (v->qual) ? v->qual->args : NULL;

            /* Compute dimensions */
            char dim_m[256], dim_n[256], sz[256];
            int ndims = 0;
            Expr* dim2 = NULL;
            for (Expr* e = da; e; e = e->next) {
                ndims++;
                if (ndims == 2) dim2 = e;
            }
            if (ndims == 1) {
                snprintf(dim_m, sizeof(dim_m), "dim%d_", da->input_label);
                snprintf(dim_n, sizeof(dim_n), "1_c_size_t");
            } else if (ndims == 2) {
                snprintf(dim_m, sizeof(dim_m), "dim%d_", da->input_label);
                snprintf(dim_n, sizeof(dim_n), "dim%d_", dim2->input_label);
            } else {
                fmex_alloc_size_str(dim_m, sizeof(dim_m), da);
                snprintf(dim_n, sizeof(dim_n), "1_c_size_t");
            }
            fmex_alloc_size_str(sz, sizeof(sz), da);

            const char* cflag = tp->is_complex ? "1" : "0";
            fmex_w(fp, 4, "plhs(%d) = mxCreateDoubleMatrix(%s, %s, %s)",
                    idx, dim_m, dim_n, cflag);

            if (tp->is_native)
                fmex_w(fp, 4, "call c_f_pointer(mxGetPr(plhs(%d)), out%d_, [%s])",
                        idx, ol, sz);
            else
                fmex_w(fp, 4, "allocate(out%d_(%s))", ol, sz);
        }
    }
    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: make the call
 * =================================================================== */

static void fmex_print_make_call(FILE* fp, Func* f, bool i8_mode)
{
    fmex_wc(fp, 4, "make the call");

    /* Build argument list */
    int nargs = 0;
    for (Var* v = f->args; v; v = v->next)
        nargs++;

    /* Collect argument strings */
    char** arg_strs = NULL;
    if (nargs > 0) {
        arg_strs = (char**) malloc(nargs * sizeof(char*));
        int i = 0;
        for (Var* v = f->args; v; v = v->next, i++) {
            arg_strs[i] = (char*) malloc(128);
            if (v->tinfo == VT_const) {
                snprintf(arg_strs[i], 128, "%s", v->name);
            } else {
                char nm[64];
                fmex_vname(nm, sizeof(nm), v);
                snprintf(arg_strs[i], 128, "%s", nm);
            }
        }
    }

    /* Print the call */
    if (f->ret && f->ret->tinfo == VT_scalar) {
        fprintf(fp, "    out0_ = %s(", f->funcv);
    } else {
        fprintf(fp, "    call %s(", f->funcv);
    }

    for (int i = 0; i < nargs; i++) {
        if (i > 0) {
            if (nargs > 4)
                fprintf(fp, ", &\n        ");
            else
                fprintf(fp, ", ");
        }
        fprintf(fp, "%s", arg_strs[i]);
    }
    fprintf(fp, ")\n");

    /* Free argument strings */
    if (arg_strs) {
        for (int i = 0; i < nargs; i++)
            free(arg_strs[i]);
        free(arg_strs);
    }

    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: marshal results
 * =================================================================== */

static void fmex_print_marshal_results(FILE* fp, Func* f, bool i8_mode)
{
    bool has_marshal = false;

    /* Return value */
    if (f->ret && f->ret->tinfo == VT_scalar)
        has_marshal = true;

    /* Inout scalar arrays (int[1]) */
    for (Var* v = f->args; v; v = v->next)
        if (v->iospec == 'b' && is_array(v->tinfo) &&
            fmex_is_scalar_array(v) && fmex_dim_product(v) == 1)
            has_marshal = true;

    /* Output scalar args (ret + args) */
    for (Var* v = f->ret; v; v = v->next)
        if (v->iospec == 'o' && (v->tinfo == VT_scalar || v->tinfo == VT_p_scalar))
            has_marshal = true;
    for (Var* v = f->args; v; v = v->next)
        if (v->iospec == 'o' && (v->tinfo == VT_scalar || v->tinfo == VT_p_scalar))
            has_marshal = true;

    /* Inout non-native arrays (need to convert back) */
    for (Var* v = f->args; v; v = v->next)
        if (v->iospec == 'b' && is_array(v->tinfo) &&
            fmex_needs_conversion(v->basetype) &&
            !(fmex_is_scalar_array(v) && fmex_dim_product(v) == 1))
            has_marshal = true;

    if (!has_marshal)
        return;

    fmex_wc(fp, 4, "marshal outputs");

    /* Return value (scalar) */
    if (f->ret) {
        Var* v = f->ret;
        if (v->tinfo == VT_scalar) {
            fmex_w(fp, 4, "plhs(1) = mxCreateDoubleMatrix(1_c_size_t, 1_c_size_t, 0)");
            fmex_w(fp, 4, "call c_f_pointer(mxGetPr(plhs(1)), ret_dbl_, [1])");
            fmex_w(fp, 4, "ret_dbl_(1) = dble(out0_)");
        }
    }

    /* Inout scalar arrays (e.g. inout int[1] ier) */
    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec != 'b' || !is_array(v->tinfo))
            continue;
        if (!(fmex_is_scalar_array(v) && fmex_dim_product(v) == 1))
            continue;
        int il = v->input_label;
        int ol = v->output_label;
        int idx = ol + 1;
        fmex_w(fp, 4, "plhs(%d) = mxCreateDoubleMatrix(1_c_size_t, 1_c_size_t, 0)",
                idx);
        fmex_w(fp, 4, "call c_f_pointer(mxGetPr(plhs(%d)), out%d_dbl_, [1])",
                idx, ol);
        fmex_w(fp, 4, "out%d_dbl_(1) = dble(in%d_)", ol, il);
    }

    /* Output-only scalars (ret + args) */
    for (int pass = 0; pass < 2; pass++) {
        Var* vlist = (pass == 0) ? f->ret : f->args;
        for (Var* v = vlist; v; v = v->next) {
            if (v->iospec != 'o')
                continue;
            if (v->tinfo == VT_scalar || v->tinfo == VT_p_scalar) {
                int ol = v->output_label;
                int idx = ol + 1;
                fmex_w(fp, 4,
                        "plhs(%d) = mxCreateDoubleMatrix(1_c_size_t, 1_c_size_t, 0)",
                        idx);
                fmex_w(fp, 4,
                        "call c_f_pointer(mxGetPr(plhs(%d)), out%d_dbl_, [1])",
                        idx, ol);
                fmex_w(fp, 4, "out%d_dbl_(1) = dble(out%d_)", ol, ol);
            }
        }
    }

    /* Inout non-native arrays: convert back to double and write to output */
    for (Var* v = f->args; v; v = v->next) {
        if (v->iospec != 'b' || !is_array(v->tinfo))
            continue;
        if (fmex_is_scalar_array(v) && fmex_dim_product(v) == 1)
            continue;
        if (!fmex_needs_conversion(v->basetype))
            continue;
        int il = v->input_label;
        int ol = v->output_label;
        int idx = ol + 1;
        Expr* da = (v->qual) ? v->qual->args : NULL;
        char sz[256];
        if (da)
            fmex_alloc_size_str(sz, sizeof(sz), da);
        else
            snprintf(sz, sizeof(sz), "inout%d_m_ * inout%d_n_", il, il);
        fmex_w(fp, 4, "call c_f_pointer(mxGetPr(plhs(%d)), out%d_dbl_, [%s])",
                idx, ol, sz);
        fmex_w(fp, 4, "do mwf_i_ = 1, %s", sz);
        fmex_w(fp, 6, "  out%d_dbl_(mwf_i_) = dble(in%d_(mwf_i_))", ol, il);
        fmex_w(fp, 4, "end do");
    }

    fprintf(fp, "\n");
}


/* ===================================================================
 * Per-stub: cleanup allocatables
 * =================================================================== */

static void fmex_print_cleanup(FILE* fp, Func* f, bool i8_mode)
{
    bool has_cleanup = false;
    for (Var* v = f->args; v; v = v->next) {
        if (is_array(v->tinfo) && fmex_needs_conversion(v->basetype))
            if (!(fmex_is_scalar_array(v) && fmex_dim_product(v) == 1))
                has_cleanup = true;
    }
    if (!has_cleanup)
        return;

    fmex_wc(fp, 4, "cleanup");
    for (Var* v = f->args; v; v = v->next) {
        if (!is_array(v->tinfo) || !fmex_needs_conversion(v->basetype))
            continue;
        if (fmex_is_scalar_array(v) && fmex_dim_product(v) == 1)
            continue;
        char nm[64];
        fmex_vname(nm, sizeof(nm), v);
        fmex_w(fp, 4, "if (allocated(%s)) deallocate(%s)", nm, nm);
    }
    fprintf(fp, "\n");
}


/* ===================================================================
 * Print a single stub
 * =================================================================== */

static void fmex_print_stub_comment(FILE* fp, Func* f)
{
    fprintf(fp, "\n! ---- %s: %d ----\n! ", f->fname.c_str(), f->line);
    print(fp, f);
    for (Func* fsame = f->same_next; fsame; fsame = fsame->same_next)
        fprintf(fp, "! Also at %s: %d\n", fsame->fname.c_str(), fsame->line);
}


static void fmex_print_stub(FILE* fp, Func* f, bool i8_mode)
{
    fmex_print_stub_comment(fp, f);

    fprintf(fp, "\nsubroutine mwfStub%d(nlhs, plhs, nrhs, prhs)\n", f->id);
    fmex_w(fp, 2, "use iso_c_binding");
    fmex_w(fp, 2, "use mwrap_mex");
    fmex_w(fp, 2, "implicit none");
    fmex_w(fp, 2, "integer(c_int), intent(in) :: nlhs, nrhs");
    fmex_w(fp, 2, "type(c_ptr), intent(inout) :: plhs(*)");
    fmex_w(fp, 2, "type(c_ptr), intent(in) :: prhs(*)");
    fprintf(fp, "\n");

    fmex_print_declarations(fp, f, i8_mode);
    fmex_print_unpack_dims(fp, f, i8_mode);
    fmex_print_unpack_inputs(fp, f, i8_mode);
    fmex_print_handle_inout(fp, f, i8_mode);
    fmex_print_alloc_outputs(fp, f, i8_mode);
    fmex_print_make_call(fp, f, i8_mode);
    fmex_print_marshal_results(fp, f, i8_mode);
    fmex_print_cleanup(fp, f, i8_mode);

    fprintf(fp, "end subroutine mwfStub%d\n", f->id);
}


/* ===================================================================
 * Print all stubs
 * =================================================================== */

static void fmex_print_stubs(FILE* fp, Func* funcs, bool i8_mode)
{
    for (Func* f = funcs; f; f = f->next)
        fmex_print_stub(fp, f, i8_mode);
}


/* ===================================================================
 * Print gateway
 * =================================================================== */

static void fmex_print_gateway(FILE* fp, Func* funcs, const char* mexfunc,
                                bool i8_mode)
{
    fprintf(fp, "\n");
    fprintf(fp, "! =================================================================\n");
    fprintf(fp, "! Gateway: mexFunction\n");
    fprintf(fp, "! =================================================================\n");

    fprintf(fp, "\nsubroutine mexFunction(nlhs, plhs, nrhs, prhs) &\n");
    fprintf(fp, "    bind(C, name=\"mexFunction\")\n");
    fmex_w(fp, 2, "use iso_c_binding");
    fmex_w(fp, 2, "use mwrap_mex");
    fmex_w(fp, 2, "implicit none");
    fmex_w(fp, 2, "integer(c_int), value :: nlhs, nrhs");
    fmex_w(fp, 2, "type(c_ptr) :: plhs(*)");
    fmex_w(fp, 2, "type(c_ptr) :: prhs(*)");
    fmex_w(fp, 2, "integer(c_int) :: stub_id_");
    fprintf(fp, "\n");
    fmex_w(fp, 2, "stub_id_ = int(mxGetScalar(prhs(1)), c_int)");
    fprintf(fp, "\n");

    /* Build dispatch: map id -> primary stub id */
    map<int, int> id_to_primary;
    for (Func* f = funcs; f; f = f->next) {
        id_to_primary[f->id] = f->id;
        for (Func* fsame = f->same_next; fsame; fsame = fsame->same_next)
            id_to_primary[fsame->id] = f->id;
    }

    if (id_to_primary.empty()) {
        fmex_w(fp, 2, "call mexErrMsgTxt('No functions registered' // c_null_char)");
    } else {
        bool first = true;
        for (map<int,int>::iterator it = id_to_primary.begin();
             it != id_to_primary.end(); ++it) {
            int sid = it->first;
            int pid = it->second;
            if (first) {
                fmex_w(fp, 2, "if (stub_id_ == %d) then", sid);
                first = false;
            } else {
                fmex_w(fp, 2, "else if (stub_id_ == %d) then", sid);
            }
            fmex_w(fp, 2, "  call mwfStub%d(nlhs, plhs, nrhs - 1, prhs(2))", pid);
        }
        fmex_w(fp, 2, "else");
        fmex_w(fp, 2, "  call mexErrMsgTxt('Unknown function ID' // c_null_char)");
        fmex_w(fp, 2, "end if");
    }

    fprintf(fp, "\nend subroutine mexFunction\n");
}


/* ===================================================================
 * Banner
 * =================================================================== */

static const char* mwrap_fmex_banner =
    "! ---------------------------------------------------------------------\n"
    "! Automatically generated by MWrap (Fortran MEX backend)\n"
    "! MWrap version 1.4\n"
    "!\n"
    "! Copyright (c) 2007-2008 David Bindel\n"
    "! MIT License -- see COPYING for details.\n"
    "! You may distribute mwrap-generated source under any license.\n"
    "! ---------------------------------------------------------------------\n";


/* ===================================================================
 * Top-level: print_fmex_init + print_fmex_file
 * =================================================================== */

void print_fmex_init(FILE* fp)
{
    fprintf(fp, "%s", mwrap_fmex_banner);
    fprintf(fp, "\n");
    fprintf(fp, "%s", fmex_header);
    fprintf(fp, "\n");
}


void print_fmex_file(FILE* fp, Func* funcs, const char* mexfunc)
{
    bool i8_mode = (mw_promote_int == 4);

    /* Validate: all functions must be Fortran in -fmex mode */
    for (Func* f = funcs; f; f = f->next) {
        if (!f->fort) {
            fprintf(stderr,
                    "Error (%s:%d): Function '%s' is not declared as FORTRAN. "
                    "All functions must use FORTRAN in -fmex mode.\n",
                    f->fname.c_str(), f->line, f->funcv);
            return;
        }
    }

    /* Print stubs */
    fmex_print_stubs(fp, funcs, i8_mode);

    /* Print gateway */
    fmex_print_gateway(fp, funcs, mexfunc, i8_mode);
}
