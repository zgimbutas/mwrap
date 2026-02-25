function test_nocopy
% Test nocopy input/output/inout for double, float, dcomplex, fcomplex.

tol = 1e-14;
tols = 1e-6;

% --- double ---
a = [1 2 3 4 5];
r = nocopy_timestwo_double(a);
assert(max(abs(r(:) - 2*a(:))) < tol)

a = [1 2 3 4 5];
r = nocopy_inplace_double(a);
assert(max(abs(r(:) - 3*a(:))) < tol)

% --- float ---
a = single([1 2 3 4 5]);
r = nocopy_timestwo_float(a);
assert(max(abs(double(r(:)) - 2*double(a(:)))) < tols)

a = single([1 2 3 4 5]);
r = nocopy_inplace_float(a);
assert(max(abs(double(r(:)) - 3*double(a(:)))) < tols)

% --- dcomplex ---
a = complex([1 2 3 4 5], [6 7 8 9 10]);
r = nocopy_timestwo_dcomplex(a);
assert(max(abs(r(:) - 2*a(:))) < tol)

a = complex([1 2 3 4 5], [6 7 8 9 10]);
r = nocopy_inplace_dcomplex(a);
assert(max(abs(r(:) - 3*a(:))) < tol)

% --- fcomplex ---
a = complex(single([1 2 3 4 5]), single([6 7 8 9 10]));
r = nocopy_timestwo_fcomplex(a);
assert(max(abs(double(r(:)) - 2*double(a(:)))) < tols)

a = complex(single([1 2 3 4 5]), single([6 7 8 9 10]));
r = nocopy_inplace_fcomplex(a);
assert(max(abs(double(r(:)) - 3*double(a(:)))) < tols)
