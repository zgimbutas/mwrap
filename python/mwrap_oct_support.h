/* Oct-file runtime support for mwrap-generated code.
 *
 * Copyright (c) 2007-2008  David Bindel
 * See the file COPYING for copying permissions
 *
 * Oct-file backend by Zydrunas Gimbutas (2026),
 * with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
 */

#include <octave/oct.h>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdint>

/* Extract a pointer from an octave_value string encoding */
static void* mwOctGetP(const octave_value& a, const char* fmt, const char** e)
{
    void* p = NULL;
    if (a.is_double_type() && a.numel() == 1 && a.double_value() == 0)
        return NULL;
    if (a.is_string()) {
        char pbuf[128];
        std::string s = a.string_value();
        strncpy(pbuf, s.c_str(), sizeof(pbuf)-1);
        pbuf[sizeof(pbuf)-1] = '\0';
        sscanf(pbuf, fmt, &p);
    }
    if (p == 0)
        *e = "Invalid pointer";
    return p;
}

/* Encode a pointer as an octave_value (string or zero) */
static octave_value mwOctCreateP(void* p, const char* fmt)
{
    if (p == 0) {
        return octave_value(0.0);
    } else {
        char pbuf[128];
        snprintf(pbuf, sizeof(pbuf), fmt, p);
        return octave_value(std::string(pbuf));
    }
}

/* Extract a C string from an octave_value; caller must delete[] result */
static char* mwOctGetString(const octave_value& a, const char** e)
{
    if (!a.is_string() && a.numel() > 0) {
        *e = "Invalid string argument";
        return NULL;
    }
    std::string s = a.string_value();
    size_t slen = s.size() + 1;
    char* cs = new char[slen];
    memcpy(cs, s.c_str(), slen);
    return cs;
}

/* Create an octave_value from a C string (NULL -> 0.0) */
static octave_value mwOctStrncpy(const char* s)
{
    if (s) {
        return octave_value(std::string(s));
    } else {
        return octave_value(0.0);
    }
}

/* Extract a double scalar with validation */
static double mwOctGetScalar(const octave_value& a, const char** e)
{
    if (!a.is_real_scalar()) {
        *e = "Invalid scalar argument";
        return 0;
    }
    return a.double_value();
}

/* Extract a float scalar with validation */
static float mwOctGetScalar_single(const octave_value& a, const char** e)
{
    if (!a.is_single_type() || a.numel() != 1) {
        *e = "Invalid scalar argument";
        return 0;
    }
    return a.float_value();
}

/* Extract a char scalar with validation */
static double mwOctGetScalar_char(const octave_value& a, const char** e)
{
    if (!a.is_string() || a.numel() != 1) {
        *e = "Invalid char argument";
        return 0;
    }
    std::string s = a.string_value();
    return (double)(char)s[0];
}
