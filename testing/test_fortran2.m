function test_fortran2


mex_id_ = 'foo(c o int*, c i int, c i int)';
[a] = test_fortran2mex(mex_id_, 1, 2);
tassert(a == 3, 'FORTRAN bindings');

function tassert(pred, msg)
if ~pred, fprintf('Failure: %s\n', msg); end
