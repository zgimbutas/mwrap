function test_c99_complex;


zarray = rand(10,1) + 1i*rand(10,1);
n = length(zarray);
mex_id_ = 'c o dcomplex = zsum(c i dcomplex[], c i int)';
[result] = test_c99_complexmex(mex_id_, zarray, n);
tassert(abs(result-sum(zarray)) < 1e-10*norm(zarray), 'C++ complex support');
mex_id_ = 'c o dcomplex = conj(c i dcomplex)';
[cresult] = test_c99_complexmex(mex_id_, result);
tassert(conj(result) == cresult, 'C++ complex support (2)');

% Real (non-complex) scalar into a dcomplex argument must be accepted
rscalar = 3.25;
mex_id_ = 'c o dcomplex = conj(c i dcomplex)';
[rresult] = test_c99_complexmex(mex_id_, rscalar);
tassert(rresult == 3.25, 'real scalar into dcomplex argument');

% Empty array into a dcomplex argument must raise an error, not crash
empty_arg = [];
caught = false;
try
  mex_id_ = 'c o dcomplex = conj(c i dcomplex)';
[eresult] = test_c99_complexmex(mex_id_, empty_arg);
catch
  caught = true;
end
tassert(caught, 'empty array into dcomplex argument');


function tassert(pred, msg)
if ~pred, fprintf('Failure: %s\n', msg); end
