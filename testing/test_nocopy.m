function test_nocopy
% pass-fail test of cinput/coutput/cinout (zero-copy) array passing.
% Tests double, float, dcomplex, fcomplex.
% Must do make test_nocopy first.

tol = 2e-16;
tols = 1e-7;

% cinput double[] + coutput double[] ..........................................
a = (1:7)';
b = nocopy_timestwo_double(a);
assert(norm(b - 2*a) < tol, 'nocopy double timestwo failed');
assert(strcmp(class(b), 'double'), 'nocopy double output class wrong');

% wrong class should error
try
  nocopy_timestwo_double(single(a));
  assert(false, 'nocopy double should reject single input');
catch ME
  assert(~isempty(strfind(ME.message, 'mxDOUBLE_CLASS expected')));
end

% cinout double[] ............................................................
c = (1:5)';
c_orig = c + 0;  % force copy (cinout bypasses copy-on-write)
d = nocopy_inplace_double(c);
assert(norm(d - 3*c_orig) < tol, 'nocopy inplace double failed');
assert(strcmp(class(d), 'double'), 'nocopy inplace output class wrong');

% cinput float[] + coutput float[] ............................................
af = single((1:7)');
bf = nocopy_timestwo_float(af);
assert(norm(double(bf) - 2*double(af)) < tols, 'nocopy float timestwo failed');
assert(strcmp(class(bf), 'single'), 'nocopy float output class wrong');

% wrong class should error
try
  nocopy_timestwo_float(double(af));
  assert(false, 'nocopy float should reject double input');
catch ME
  assert(~isempty(strfind(ME.message, 'mxSINGLE_CLASS expected')));
end

% cinput dcomplex[] + coutput dcomplex[] ......................................
% NOTE: nocopy complex requires MX_HAS_INTERLEAVED_COMPLEX; on split-complex
% systems the mex function returns an error, which we accept as passing.
az = complex((1:7)', (7:-1:1)');
try
  bz = nocopy_timestwo_dcomplex(az);
  assert(norm(bz - 2*az) < tol, 'nocopy dcomplex timestwo failed');
  assert(strcmp(class(bz), 'double'), 'nocopy dcomplex output class wrong');
  assert(~isreal(bz), 'nocopy dcomplex output should be complex');

  % wrong class should error
  try
    nocopy_timestwo_dcomplex(single(az));
    assert(false, 'nocopy dcomplex should reject single input');
  catch ME
    assert(~isempty(strfind(ME.message, 'mxDOUBLE_CLASS expected')));
  end
catch ME
  if isempty(strfind(ME.message, 'interleaved complex'))
    rethrow(ME);
  end
  fprintf('  (dcomplex skipped: split complex)\n');
end

% cinput fcomplex[] + coutput fcomplex[] ......................................
azf = single(complex((1:7)', (7:-1:1)'));
try
  bzf = nocopy_timestwo_fcomplex(azf);
  assert(norm(double(bzf) - 2*double(azf)) < tols, 'nocopy fcomplex timestwo failed');
  assert(strcmp(class(bzf), 'single'), 'nocopy fcomplex output class wrong');
  assert(~isreal(bzf), 'nocopy fcomplex output should be complex');

  % wrong class should error
  try
    nocopy_timestwo_fcomplex(double(azf));
    assert(false, 'nocopy fcomplex should reject double input');
  catch ME
    assert(~isempty(strfind(ME.message, 'mxSINGLE_CLASS expected')));
  end
catch ME
  if isempty(strfind(ME.message, 'interleaved complex'))
    rethrow(ME);
  end
  fprintf('  (fcomplex skipped: split complex)\n');
end

fprintf('test_nocopy: PASSED\n');
