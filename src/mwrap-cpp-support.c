/* C++ MEX API runtime support for mwrap-generated code.
 *
 * Copyright (c) 2007-2008  David Bindel
 * See the file COPYING for copying permissions
 *
 * C++ MEX API backend by Zydrunas Gimbutas (2026),
 * with assistance from Claude Code / Claude Opus 4.6 (Anthropic).
 */

#include "mex.hpp"
#include "mexAdapter.hpp"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdint>
#include <string>
#include <vector>
#include <complex>
#include <stdexcept>

using namespace matlab::data;

/* Extract a pointer from an Array string encoding */
static void* mwCppGetP(const Array& a, const char* fmt, const char** e)
{
    void* p = NULL;
    if (a.getType() == ArrayType::DOUBLE && a.getNumberOfElements() == 1) {
        TypedArray<double> ta = a;
        if (ta[0] == 0)
            return NULL;
    }
    if (a.getType() == ArrayType::CHAR) {
        char pbuf[128];
        CharArray ca = a;
        std::string s = ca.toAscii();
        strncpy(pbuf, s.c_str(), sizeof(pbuf)-1);
        pbuf[sizeof(pbuf)-1] = '\0';
        sscanf(pbuf, fmt, &p);
    }
    if (p == 0)
        *e = "Invalid pointer";
    return p;
}

/* Encode a pointer as an Array (string or zero) */
static Array mwCppCreateP(ArrayFactory& factory, void* p, const char* fmt)
{
    if (p == 0) {
        return factory.createScalar<double>(0.0);
    } else {
        char pbuf[128];
        snprintf(pbuf, sizeof(pbuf), fmt, p);
        return factory.createCharArray(std::string(pbuf));
    }
}

/* Extract a C string from an Array; caller must delete[] result */
static char* mwCppGetString(const Array& a, const char** e)
{
    if (a.getType() != ArrayType::CHAR && a.getNumberOfElements() > 0) {
        *e = "Invalid string argument";
        return NULL;
    }
    CharArray ca = a;
    std::string s = ca.toAscii();
    size_t slen = s.size() + 1;
    char* cs = new char[slen];
    memcpy(cs, s.c_str(), slen);
    return cs;
}

/* Create an Array from a C string (NULL -> 0.0) */
static Array mwCppStrncpy(ArrayFactory& factory, const char* s)
{
    if (s) {
        return factory.createCharArray(std::string(s));
    } else {
        return factory.createScalar<double>(0.0);
    }
}

/* Extract a double scalar with validation */
static double mwCppGetScalar(const Array& a, const char** e)
{
    if (a.getNumberOfElements() != 1 ||
        (a.getType() != ArrayType::DOUBLE &&
         a.getType() != ArrayType::SINGLE &&
         a.getType() != ArrayType::INT32 &&
         a.getType() != ArrayType::INT64 &&
         a.getType() != ArrayType::UINT32 &&
         a.getType() != ArrayType::UINT64)) {
        *e = "Invalid scalar argument";
        return 0;
    }
    TypedArray<double> ta = a;
    return ta[0];
}

/* Extract a float scalar with validation */
static float mwCppGetScalar_single(const Array& a, const char** e)
{
    if (a.getType() != ArrayType::SINGLE || a.getNumberOfElements() != 1) {
        *e = "Invalid scalar argument";
        return 0;
    }
    TypedArray<float> ta = a;
    return ta[0];
}

/* Extract a char scalar with validation */
static double mwCppGetScalar_char(const Array& a, const char** e)
{
    if (a.getType() != ArrayType::CHAR || a.getNumberOfElements() != 1) {
        *e = "Invalid char argument";
        return 0;
    }
    CharArray ca = a;
    std::string s = ca.toAscii();
    return (double)(char)s[0];
}
