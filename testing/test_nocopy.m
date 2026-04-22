function test_nocopy
% Test nocopy input/output/inout for double, float, dcomplex, fcomplex.
%
% Note: nocopy inout was disabled (see NEWS) because modifying prhs
% in place is unsafe under MATLAB's copy-on-write semantics. Codegen
% falls back to the copy path, so the caller's array must be left
% untouched even when the wrapper is declared `nocopy inout`.

tol = 1e-14;
tols = 1e-6;

% --- double ---
a = [1 2 3 4 5];
r = nocopy_timestwo_double(a);
assert(max(abs(r(:) - 2*a(:))) < tol)

a0 = [1 2 3 4 5];
a = a0;
r = nocopy_inplace_double(a);
assert(max(abs(r(:) - 3*a0(:))) < tol)
assert(isequal(a, a0))  % caller's input must not be mutated

% --- float ---
a = single([1 2 3 4 5]);
r = nocopy_timestwo_float(a);
assert(max(abs(double(r(:)) - 2*double(a(:)))) < tols)

a0 = single([1 2 3 4 5]);
a = a0;
r = nocopy_inplace_float(a);
assert(max(abs(double(r(:)) - 3*double(a0(:)))) < tols)
assert(isequal(a, a0))

% --- dcomplex ---
a = complex([1 2 3 4 5], [6 7 8 9 10]);
r = nocopy_timestwo_dcomplex(a);
assert(max(abs(r(:) - 2*a(:))) < tol)

a0 = complex([1 2 3 4 5], [6 7 8 9 10]);
a = a0;
r = nocopy_inplace_dcomplex(a);
assert(max(abs(r(:) - 3*a0(:))) < tol)
assert(isequal(a, a0))

% --- fcomplex ---
a = complex(single([1 2 3 4 5]), single([6 7 8 9 10]));
r = nocopy_timestwo_fcomplex(a);
assert(max(abs(double(r(:)) - 2*double(a(:)))) < tols)

a0 = complex(single([1 2 3 4 5]), single([6 7 8 9 10]));
a = a0;
r = nocopy_inplace_fcomplex(a);
assert(max(abs(double(r(:)) - 3*double(a0(:)))) < tols)
assert(isequal(a, a0))
